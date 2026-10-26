"""Presentation hooks around the unchanged phase-5 runtime and game."""
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'phase5'))
from runtime import SimulationRuntime
from game import Match,Phase

class StepBoundary:
    def __init__(self,base,presenter):self.base,self.presenter=base,presenter;self.step_wall_s=0.;self.steps=0
    def __getattr__(self,name):return getattr(self.base,name)
    def mj_step(self,model,data,*args,**kwargs):
        start=time.perf_counter();result=self.base.mj_step(model,data,*args,**kwargs)
        self.step_wall_s+=time.perf_counter()-start;self.steps+=1
        self.presenter.after_step()
        return result

class VisualRuntime(SimulationRuntime):
    def attach(self,presenter):
        self.presenter=presenter;self.boundary=None
        if presenter.config.enabled:
            self.boundary=StepBoundary(self.engine.mujoco,presenter)
            self.engine.mujoco=self.boundary
            original=self.engine.LateralControl
            class ObservedControl(original):
                def select(control,position):
                    result=super().select(position);presenter.goal_q=control.goal;return result
            self.engine.LateralControl=ObservedControl

    def execute(self,distance,opponent,output,on_prepared,on_shooting):
        def prepare(observation):
            action=on_prepared(observation)
            self.presenter.status['action']=action
            self.presenter.capture()
            self.presenter.pause('before_shot',self.presenter.config.before_shot_s)
            return action
        def shooting():
            on_shooting();self.presenter.begin_episode()
        return super().execute(distance,opponent,output,prepare,shooting)

class VisualMatch(Match):
    def __init__(self,*args,presenter,**kwargs):
        self.presenter=presenter
        kwargs.setdefault('printer',self.console_print)
        super().__init__(*args,**kwargs)
        self.publish()
    def console_print(self,*args,**kwargs):
        if args and isinstance(args[0],str):args=(args[0].replace('| SHOOTING','| preset seleccionado'),*args[1:])
        print(*args,**kwargs)
    def publish(self):
        last=self.score.history[-1]['outcome'] if self.score.history else None
        self.presenter.set_status({'penalty':self.current.number if self.current else 0,
            'total':self.config.penalties,'goals':self.score.goals,'saves':self.score.saves,'misses':self.score.misses,
            'phase':self.phase.value,'action':self.current.action if self.current else None,'last_result':last})
    def transition(self,phase):
        if phase==Phase.PREPARING:
            self.episode_wall_start=time.perf_counter();self.pause_start=len(self.presenter.pauses)
            self.pacing_start=self.presenter.pacing_sleep_s
        if self.phase==Phase.RESOLVING and phase in (Phase.READY,Phase.FINISHED):
            self.publish()
            self.presenter.pause('after_result',self.presenter.config.after_result_s)
            if phase==Phase.READY:self.presenter.pause('before_reset',self.presenter.config.before_reset_s)
            self.presenter.episodes.append({'penalty':self.current.number,
                'wall_through_result_and_transition_s':time.perf_counter()-self.episode_wall_start,
                'presentation_pause_wall_s':sum(p['wall_s'] for p in self.presenter.pauses[self.pause_start:]),
                'pacing_sleep_wall_s':self.presenter.pacing_sleep_s-self.pacing_start,
                'simulated_s':float(self.runtime.data.time)})
        super().transition(phase);self.publish()
