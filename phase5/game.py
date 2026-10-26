"""Game state, penalties and scoreboard; no physics/controller implementation."""
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'phase4b'))
from striker_agent import StrikerAgent
from catalog import load_calibration

class Phase(str,Enum):
    READY='READY'
    PREPARING='PREPARING'
    SHOOTING='SHOOTING'
    RESOLVING='RESOLVING'
    FINISHED='FINISHED'

@dataclass(frozen=True)
class Config:
    penalties:int=5
    seed:int=2026
    keeper:str='agent'
    striker:str='utility'
    distance:str='long'
    fixed_action:str='center'

    def __post_init__(self):
        if self.penalties<1: raise ValueError('At least one penalty required')
        if self.keeper not in ('fixed','agent') or self.striker not in ('fixed','random','utility'):
            raise ValueError('Invalid agent configuration')
        if self.distance not in ('original','long') or self.fixed_action not in ('center','left','right'):
            raise ValueError('Invalid initial scenario/action')

@dataclass
class Scoreboard:
    goals:int=0
    saves:int=0
    misses:int=0
    history:list=field(default_factory=list)

    def record(self,record):
        if record['outcome'] not in ('goal','save','miss'): raise ValueError('Unresolved result cannot alter score')
        if any(r['penalty']==record['penalty'] for r in self.history): raise ValueError('Penalty already scored')
        field_name={'goal':'goals','save':'saves','miss':'misses'}[record['outcome']]
        setattr(self,field_name,getattr(self,field_name)+1)
        self.history.append(record)
        assert self.goals+self.saves+self.misses==len(self.history)

@dataclass
class PenaltyState:
    number:int
    phase:Phase=Phase.READY
    action:str|None=None
    outcome:str|None=None

class Match:
    ALLOWED={Phase.READY:{Phase.PREPARING},Phase.PREPARING:{Phase.SHOOTING},
             Phase.SHOOTING:{Phase.RESOLVING},Phase.RESOLVING:{Phase.READY,Phase.FINISHED},Phase.FINISHED:set()}

    def __init__(self,config,runtime,output,selector=None,calibration=None,printer=print):
        self.config,self.runtime,self.output=config,runtime,Path(output)
        self.selector=selector or StrikerAgent()
        self.calibration=calibration if calibration is not None else load_calibration(config.distance)
        self.print=printer
        self.phase=Phase.READY; self.current=None
        self.score=Scoreboard(); self.transitions=[]

    def transition(self,phase):
        if phase not in self.ALLOWED[self.phase]: raise RuntimeError(f'Invalid game transition: {self.phase}->{phase}')
        self.phase=phase
        if self.current:self.current.phase=phase
        self.transitions.append({'penalty':self.current.number if self.current else None,
                                 'phase':phase.value,'monotonic_ns':time.monotonic_ns()})

    def save(self,path,value):
        with path.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2)

    def play(self):
        if self.current is not None or self.phase!=Phase.READY: raise RuntimeError('Match already started')
        start=time.perf_counter()
        for number in range(1,self.config.penalties+1):
            self.current=PenaltyState(number)
            directory=self.output/f'penalty_{number:02d}'; directory.mkdir()
            episode_start=time.perf_counter()
            self.transition(Phase.PREPARING)
            self.print(f'Penal {number}/{self.config.penalties} | PREPARING',flush=True)
            selection={}
            def choose(observation):
                before=self.selector.snapshot()
                decision=self.selector.choose(observation,self.calibration,f'penalty_{number:02d}',
                    self.config.striker,self.config.seed,self.config.fixed_action)
                self.current.action=decision['action']
                selection.update(decision)
                self.save(directory/'decision_before_shot.json',{'decision':decision,'statistics_before':before})
                self.save(directory/'state_pending.json',self.selector.snapshot())
                self.print(f'  Tiro: {decision["action"]} | arquero y={observation.keeper_y_w:+.3f} m | SHOOTING',flush=True)
                return decision['action']
            physical,execution,physical_wall=self.runtime.execute(self.config.distance,self.config.keeper,
                directory/'physical.json',choose,lambda:self.transition(Phase.SHOOTING))
            self.transition(Phase.RESOLVING)
            outcome,prefix_error=self.runtime.evaluate(physical,self.config.distance,execution['action'])
            update=self.selector.observe(f'penalty_{number:02d}',outcome)
            self.current.outcome=outcome
            wall=time.perf_counter()-episode_start
            observation=selection['observation']
            record={'penalty':number,'action':execution['action'],'scenario':execution['scenario'],
                'outcome':outcome,'keeper_initial_y_w_m':observation['keeper_y_w'],
                'keeper_final_q_m':physical['rail']['final_q_m'],
                'simulated_s':physical['simulated_s'],'wall_s':wall,'physics_call_wall_s':physical_wall,
                'initial_state_sha256':physical['initial_state_sha256'],
                'ball_prefix_error_vs_historical_probe':prefix_error,
                'first_foot_ball':physical['evaluation']['first_foot_ball'],
                'first_keeper_ball':physical['evaluation']['first_keeper_ball']}
            self.score.record(record)
            self.save(directory/'feedback_after_shot.json',{'record':record,'update':update,
                'feedback_time_sim_s':physical['simulated_s'],'statistics_after':self.selector.snapshot()})
            self.print(f'  {outcome.upper()} | Goles {self.score.goals} / Atajadas {self.score.saves} / Errados {self.score.misses} | sim {record["simulated_s"]:.1f}s / real {wall:.3f}s',flush=True)
            self.transition(Phase.FINISHED if number==self.config.penalties else Phase.READY)
        result={'config':asdict(self.config),'phase':self.phase.value,'scoreboard':asdict(self.score),
                'transitions':self.transitions,'play_wall_s':time.perf_counter()-start,
                'total_simulated_s':sum(x['simulated_s'] for x in self.score.history),
                'striker_statistics':self.selector.snapshot(),'runtime':self.runtime.summary()}
        self.save(self.output/'match.json',result)
        return result
