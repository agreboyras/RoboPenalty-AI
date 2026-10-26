"""Only this selector routes human input. Keeper receives no router or bus."""
from dataclasses import asdict
import copy
import threading
import time
from session import BoundaryEnd

class SelectionRouter:
    def __init__(self,automatic,service):
        self.automatic,self.service=automatic,service;self.manual_history=[];self.pending=None;self.waits=[]
    def snapshot(self):return self.automatic.snapshot()
    def choose(self,observation,calibration,episode_id,strategy='utility',seed=2026,fixed_action='center'):
        c=self.service.control;c.assert_owner()
        if self.pending is not None:raise RuntimeError('Previous manual feedback pending')
        self.service.checkpoint()
        if c.stop_requested or c.reset_requested:self.service.match.cancel_selection()
        if c.mode=='auto':return self.automatic.choose(observation,calibration,episode_id,strategy,seed,fixed_action)
        if observation.time_sim_s!=0:raise RuntimeError('Directed selection requires initialized episode at t=0')
        runtime=self.service.runtime;before=runtime.integration_state(runtime.data).copy();ticket=c.open_selection()
        c.emit(f'READY PARA ELEGIR | Modo DIRIGIDO | Esperando instruccion para penal {c.penalty} | fisica PREPARING t=0 | Izquierda disponible: centro-izquierda',flush=True)
        if c.voice and getattr(self.service,'voice_on_wait',False):
            ok,reason=c.voice.request(ticket);c.emit(f'[microfono] {reason}',flush=True)
        try:
            while c.pending_shot is None and c.mode=='directed' and not c.stop_requested and not c.reset_requested:
                self.service.idle()
            c.close_selection()
            if c.voice:
                # Cancel capture before any physics. ASR may finish later, but its ticket is invalid.
                while not c.voice.capture_closed.wait(.02):self.service.idle()
            unchanged=bool(runtime.engine.np.array_equal(before,runtime.integration_state(runtime.data)))
            self.waits.append(dict(episode_id=episode_id,ticket=ticket,full_physics_unchanged=unchanged,
                processing_thread=threading.get_ident(),source='selection_wait'))
            if not unchanged:raise RuntimeError('Input wait modified authoritative physics')
            if c.stop_requested or c.reset_requested:self.service.match.cancel_selection()
            if c.mode=='auto':return self.automatic.choose(observation,calibration,episode_id,strategy,seed,fixed_action)
            selected=c.pending_shot;c.pending_shot=None
            if selected is None:raise RuntimeError('No valid directed action; no fallback allowed')
            if selected['action'] not in calibration:raise ValueError('Action lacks 8C calibration')
            self.pending=dict(episode_id=episode_id,**selected)
            return dict(episode_id=episode_id,action=selected['action'],observation=asdict(observation),
                strategy='directed',reason='explicit_user_command',input=copy.deepcopy(selected),
                automatic_learning_updated=False,candidates={})
        finally:c.close_selection()
    def observe(self,episode_id,outcome):
        if self.pending is None:return self.automatic.observe(episode_id,outcome)
        if self.pending['episode_id']!=episode_id or outcome not in ('goal','save','miss'):raise RuntimeError('Invalid manual feedback')
        event={**self.pending,'outcome':outcome,'learning_phase':'manual_no_update','automatic_learning_updated':False}
        self.manual_history.append(event);self.pending=None;return copy.deepcopy(event)
