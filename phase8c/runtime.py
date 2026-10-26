"""Reuse 8B.3 body PD, 8B.2 utility/runtime, unchanged B with a DONE-only wrapper."""
import json
import numpy as np
from pathlib import Path
from phase8b3.runtime import components as previous
from phase8c.return_control import ReturnControl

def components(catalog,posture='dynamic',delta=0.,correct_return=True):
    Base,Selector=previous(catalog,posture,delta)
    class Runtime(Base):
        def __init__(self):
            super().__init__();self.return_agent=None
            factory=self.engine.GoalkeeperAgent
            def agent(limits):
                self.return_agent=ReturnControl(factory(limits),limits,correct_return)
                return self.return_agent
            self.engine.GoalkeeperAgent=agent
            physical_run=self.engine.run
            def monitored_run(args):
                pd=self.engine.body_pd;command=pd.command;counts=np.zeros(29,dtype=int);peak=np.zeros(29);calls=0
                def observed_command(data,base,limits):
                    nonlocal calls
                    torque=command(data,base,limits);calls+=1
                    cap=np.minimum(np.asarray(limits),np.max(abs(self.model.jnt_actfrcrange[self.keeper.joints]),axis=1))
                    counts[:]+=abs(torque)>=cap-1e-6
                    peak[:]=np.maximum(peak,abs(data.qfrc_actuator[self.keeper.dofs]))
                    return torque
                pd.command=observed_command
                try:return physical_run(args)
                finally:
                    Path(args.output).parent.joinpath('motor_monitor.json').write_text(json.dumps(dict(
                        calls=calls,rate_hz=500,saturation_command_steps_per_joint=counts.tolist(),
                        actual_torque_peak_nm_per_joint=peak.tolist(),names=pd.names,
                        note='Read-only observer of the single PD return value; does not write ctrl'),indent=2),encoding='utf-8')
            self.engine.run=monitored_run
            execute=self.execute
            def run(distance,opponent,output,on_prepared,on_shooting):
                self.return_agent=None
                try:return execute(distance,opponent,output,on_prepared,on_shooting)
                finally:
                    if self.return_agent:
                        rows=self.return_agent.rows
                        Path(output).parent.joinpath('return.json').write_text(json.dumps(dict(
                            correction_enabled=correct_return,rows=rows,
                            first_DONE=next((r for r in rows if r['state']=='DONE'),None),final=rows[-1],
                            final_physical=dict(time_s=float(self.data.time),q_m=float(self.data.qpos[self.rail.qpos]),
                                v_mps=float(self.data.qvel[self.rail.dof]),force_n=float(self.data.ctrl[self.rail.actuator]))),indent=2),encoding='utf-8')
            self.execute=run
    return Runtime,Selector
