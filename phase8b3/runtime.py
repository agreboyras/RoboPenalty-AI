"""One checked expression hook in a private runner; no historical source edits."""
import inspect
import json
from pathlib import Path
from phase8b2.runtime import components as base_components
from phase8b1.runtime_adapter import install as install_B
from phase8b3.posture import PosturePD

def components(catalog,mode='dynamic',perturbation=0.):
    Base,Selector=base_components(catalog)
    class Runtime(Base):
        def __init__(self):
            super().__init__();self.posture=None
            install_B(self,'B')
            factory=self.engine.GoalkeeperAgent
            def agent(limits):
                original=factory(limits)
                class Observer:
                    def __getattr__(self,key):return getattr(original,key)
                    def step(_,o):
                        decision=original.step(o);self.posture.notify(decision,o);return decision
                return Observer()
            self.engine.GoalkeeperAgent=agent
            source=inspect.getsource(self.engine.run)
            expression='np.clip(70*(posture-data.qpos[keeper.qpos])-5*data.qvel[keeper.dofs], -torque_limits, torque_limits)'
            if source.count(expression)!=1 or source.count('data.ctrl[keeper.actuators]')!=1:
                raise RuntimeError('Historical single-owner PD hook changed; refusing integration')
            source=source.replace(expression,'body_pd.command(data, posture, torque_limits)')
            exec(compile(source,str(Path(__file__).resolve())+'::<private_PD_reference_hook>','exec'),self.engine.__dict__)
            original_initialize=self.original_initialize
            def initialize(config,m,d,kick,rail,probe):
                original_initialize(config,m,d,kick,rail,probe)
                if perturbation:
                    ball=m.body('ball').id;j=int(m.body_jntadr[ball]);q=int(m.jnt_qposadr[j])
                    d.qpos[q+1]+=perturbation  # Initial condition only, before simulation.
            self.original_initialize=initialize
            measured=self.execute
            def execute(distance,opponent,output,on_prepared,on_shooting):
                self.posture=PosturePD(self.model,self.keeper,self.rail,mode)
                self.engine.body_pd=self.posture
                try:result,selection,wall=measured(distance,opponent,output,on_prepared,on_shooting)
                finally:
                    report=self.posture.summary();report['initial_ball_delta_y_m']=perturbation
                    report['actuator_ownership']='Exactly one assignment to data.ctrl[keeper.actuators] in private run(); replacement changes only PD references'
                    Path(output).parent.joinpath('posture.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                if not report['passed']:raise RuntimeError(f'Posture rejected: {report["failures"]}')
                return result,selection,wall
            self.execute=execute
        def evaluate(self,result,distance,action):
            if perturbation:raise RuntimeError('Perturbed shots require their own counterfactual, never nominal calibration scoring')
            return super().evaluate(result,distance,action)
    return Runtime,Selector
