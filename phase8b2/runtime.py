"""Private module bindings extend the catalog, never mutate historical modules."""
import importlib.util
import json
from pathlib import Path
import sys
from phase8b2.experiment import BallRecorder
PROJECT=Path(__file__).resolve().parents[1]

def private_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

def components(catalog):
    # This is our existing utility algorithm, evaluated in an isolated namespace.
    # Action vocabulary is the sole extension; priors, weights and updates stay identical.
    agent=private_module('phase8b2_owned_selector',PROJECT/'phase4b/striker_agent.py')
    agent.ACTIONS=catalog.actions
    module=private_module('phase8b2_owned_runtime',PROJECT/'phase5/runtime.py')
    module.CATALOG={'long':catalog.mapping}
    module.InitialObservation=lambda *a,**k:agent.InitialObservation(*a,available_actions=catalog.actions,**k)

    class Selector(agent.StrikerAgent):
        def __init__(self,state=None):
            if state is not None and state.get('catalog_sha256')!=catalog.id:
                raise ValueError('Historical/different-catalog statistics cannot be reused')
            super().__init__(state);self.state['catalog_sha256']=catalog.id

    class Runtime(module.SimulationRuntime):
        def __init__(self):
            super().__init__()
            for _,(scenario,bias) in catalog.mapping.items():
                self.original_scenarios[scenario]={'translate_x':-2.,'target_bias':bias}
            self.recorder=BallRecorder(self.engine.mujoco,self);self.engine.mujoco=self.recorder

        def attach(self,presenter):
            from phase6a.integration import VisualRuntime
            VisualRuntime.attach(self,presenter)

        def execute(self,distance,opponent,output,on_prepared,on_shooting):
            from phase7c.integrity import model_signature
            signature=model_signature(self.model)
            self.recorder.rows=[];self.recorder.impacts=[]
            if hasattr(self,'presenter'):
                old_prepared=on_prepared;old_shooting=on_shooting
                def on_prepared(observation):
                    action=old_prepared(observation);self.presenter.status['action']=action
                    self.presenter.capture();self.presenter.pause('before_shot',self.presenter.config.before_shot_s)
                    return action
                def on_shooting():old_shooting();self.presenter.begin_episode()
            result,selection,wall=super().execute(distance,opponent,output,on_prepared,on_shooting)
            if signature!=model_signature(self.model):raise AssertionError('Compiled physical model changed')
            result['phase8b2']={'catalog_sha256':catalog.id,'trajectory_columns':['t','x','y','z','vx','vy','vz','foot_normal_force_n'],
                'trajectory':self.recorder.rows,'positive_foot_contacts':self.recorder.impacts,
                'physical_model_unchanged':True,'bias':catalog.mapping[selection['action']][1]}
            Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
            return result,selection,wall

        def evaluate(self,result,distance,action):return catalog.evaluate(result,distance,action)
    return Runtime,Selector
