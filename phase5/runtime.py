"""Reusable in-process physics adapter; all earlier controllers remain unchanged."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import pickle
import sys
import time

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT/'phase4b'))
from catalog import CATALOG, classify_after_episode
from striker_agent import InitialObservation


class SimulationRuntime:
    def __init__(self):
        start=time.perf_counter()
        sys.path.insert(0,str(PROJECT/'phase4a'))
        spec=importlib.util.spec_from_file_location('phase5_existing_physics',PROJECT/'phase4a/experiment.py')
        self.engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.engine)
        e=self.engine
        self.original_initialize=e.initialize
        self.original_scenarios={k:dict(v) for k,v in e.SCENARIOS.items()}
        self.scene=e.build_scene(PROJECT.parent/'RoboNaldo_Deploy',PROJECT.parent/'unitree_mujoco',e.Limits())
        self.model,self.data,self.shooter,self.keeper,self.rail=self.scene
        self.kick=e.FreeKickAdapter(PROJECT.parent/'RoboNaldo_Deploy',self.model,self.shooter)
        self.session=self.kick.fsm.freekick_policy.ort_session
        self.template=self.clone(self.kick)
        self.pristine_digest=self.temporal_digest(self.template)
        self.initial_model_body_pos=self.model.body_pos.copy()
        # A genuinely fresh MjData supplies the clean integration-state reference.
        fresh=e.mujoco.MjData(self.model)
        e.mujoco.mj_forward(self.model,fresh)
        self.integration_spec=e.mujoco.mjtState.mjSTATE_INTEGRATION
        self.fresh_state=self.integration_state(fresh)
        self.fresh_contacts=self.contacts(fresh)
        self.model_builds=self.policy_loads=1
        self.resets=[]
        self.console=sys.stdout
        e.build_scene=lambda *args:self.reset_scene()
        e.FreeKickAdapter=lambda *args:self.reset_adapter()
        self.setup_wall_s=time.perf_counter()-start

    def clone(self,value):
        # Preserve the non-pickleable, feed-forward ONNX session. Every Python
        # array, buffer and FSM object is restored from the pristine object graph.
        return copy.deepcopy(value,{id(self.session):self.session})

    def temporal_digest(self,value):
        plain=copy.deepcopy(value,{id(self.session):'RETAINED_ONNX_SESSION'})
        return hashlib.sha256(pickle.dumps(plain,protocol=5)).hexdigest()

    def integration_state(self,data):
        m=self.engine.mujoco
        result=self.engine.np.empty(m.mj_stateSize(self.model,self.integration_spec))
        m.mj_getState(self.model,data,result,self.integration_spec)
        return result

    def contacts(self,data):
        return [(int(c.geom1),int(c.geom2),float(c.dist)) for c in data.contact[:data.ncon]]

    def reset_scene(self):
        e=self.engine
        if not e.np.array_equal(self.model.body_pos,self.initial_model_body_pos):
            raise RuntimeError('Persistent model geometry was altered')
        e.mujoco.mj_resetData(self.model,self.data)
        e.mujoco.mj_forward(self.model,self.data)
        current=self.integration_state(self.data)
        equal=bool(e.np.array_equal(current,self.fresh_state))
        contacts_equal=self.contacts(self.data)==self.fresh_contacts
        if not equal or not contacts_equal:
            raise RuntimeError('Reset differs from a fresh MjData')
        check={'episode_number':len(self.resets)+1,'time_sim_s':float(self.data.time),
               'full_integration_state_equal_to_fresh':equal,'contacts_equal_to_fresh':contacts_equal,
               'initial_contact_count':int(self.data.ncon),'max_abs_velocity':float(abs(self.data.qvel).max()),
               'max_abs_control':float(abs(self.data.ctrl).max()),
               'integration_state_sha256':hashlib.sha256(current.tobytes()).hexdigest()}
        self.resets.append(check)
        return self.scene

    def reset_adapter(self):
        restored=self.clone(self.template)
        self.kick.__dict__.clear(); self.kick.__dict__.update(restored.__dict__)
        equal=self.temporal_digest(self.kick)==self.pristine_digest
        same_session=self.kick.fsm.freekick_policy.ort_session is self.session
        if not equal or not same_session: raise RuntimeError('FreeKick reset is not pristine')
        self.resets[-1].update(freekick_state_equal_to_pristine=equal,
            onnx_session_identity_preserved=same_session,freekick_sensor_updates=self.kick.sensor_updates,
            freekick_time_step=self.kick.fsm.freekick_policy.time_step,
            passive_at_reset=self.kick.fsm.cur_policy is self.kick.fsm.passive_mode)
        return self.kick

    def observe_initial(self,distance,opponent):
        e=self.engine; m,d=self.model,self.data
        reader=e.ObservationReader(m,self.rail)
        o=reader.read(d)
        radius=float(m.geom_size[m.geom('ball_geom').id,0])
        y=float(d.xpos[self.keeper.pelvis,1]); span=0.
        ball=m.geom('ball_geom').id
        for g in self.keeper.geoms:
            if not (int(m.geom_contype[g]) & int(m.geom_conaffinity[ball]) or int(m.geom_contype[ball]) & int(m.geom_conaffinity[g])): continue
            rotation=d.geom_xmat[g].reshape(3,3)
            center=d.geom_xpos[g]+rotation@m.geom_aabb[g,:3]
            extent=abs(rotation)@m.geom_aabb[g,3:]
            if abs(center[0]-reader.plane_x)<=extent[0]+radius and abs(center[2]-radius)<=extent[2]+radius:
                span=max(span,abs(float(center[1]-y))+float(extent[1]))
        return InitialObservation(distance,opponent,y,o.keeper_q,o.keeper_v,span,radius,
            o.ball_position_w,tuple(float(x) for x in d.qpos[self.kick.root_q:self.kick.root_q+3]),time_sim_s=float(d.time))

    def execute(self,distance,opponent,output,on_prepared,on_shooting):
        """The phase-4A loop recreates goalkeeper, reference and trace per call."""
        from argparse import Namespace
        e=self.engine
        e.SCENARIOS={k:dict(v) for k,v in self.original_scenarios.items()}
        args=Namespace(output=str(output),mode=opponent,scenario=CATALOG[distance]['center'][0],duration=14.)
        selection={}
        def initialize(config,model,data,kick,rail,probe):
            self.original_initialize(config,model,data,kick,rail,False)
            e.mujoco.mj_forward(model,data)
            observation=self.observe_initial(distance,opponent)
            with contextlib.redirect_stdout(self.console):
                action=on_prepared(observation)
            scenario,bias=CATALOG[distance][action]
            chosen=dict(self.original_scenarios[scenario])
            if {k:v for k,v in chosen.items() if k!='target_bias'}!={k:v for k,v in config.items() if k!='target_bias'}:
                raise RuntimeError('Preset unexpectedly changes initial geometry')
            config.clear(); config.update(chosen)
            args.scenario=scenario; kick.state.target_y_bias=bias
            selection.update(action=action,scenario=scenario)
            on_shooting()
        e.initialize=initialize
        start=time.perf_counter()
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream): status=e.run(args)
        elapsed=time.perf_counter()-start
        result=json.loads(Path(output).read_text(encoding='utf-8'))
        if status or not result['passed']: raise RuntimeError('Physical episode failed; score unchanged')
        # The reused runner's timer labels described constructors. These calls now
        # reset cached objects, so expose their actual meaning explicitly.
        t=result['timing']
        t['scene_reset_s']=t.pop('scene_build_s')
        t['adapter_reset_s']=t.pop('policy_load_s')
        t['runner_elapsed_since_module_import_s']=t.pop('script_wall_s')
        final=self.integration_state(self.data)
        result['phase5_state']={'final_integration_state':final.tolist(),
            'final_integration_sha256':hashlib.sha256(final.tobytes()).hexdigest(),
            'model_object_id':id(self.model),'data_object_id':id(self.data),'onnx_session_object_id':id(self.session)}
        Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result,selection,elapsed

    @staticmethod
    def evaluate(result,distance,action):
        label,error=classify_after_episode(result,distance,action)
        if label not in ('goal','save','miss'): raise RuntimeError(f'Unresolved physical result: {label}')
        return label,error

    def summary(self):
        return {'model_builds':self.model_builds,'policy_loads':self.policy_loads,
                'setup_wall_s':self.setup_wall_s,'resets':self.resets,
                'onnx_inputs':[(v.name,v.shape) for v in self.session.get_inputs()],
                'onnx_outputs':[(v.name,v.shape) for v in self.session.get_outputs()]}
