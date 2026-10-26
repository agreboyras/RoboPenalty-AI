"""Initial-Y perturbations, physical FreeKick, free keeper counterfactuals."""
from bootstrap import *
import argparse
import json
import math
from phase8b2.experiment import BiasRuntime,identifier,summarize
from phase8c.integrity import sources
DELTAS=(-.005,-.002,-.001,0.,.001,.002,.005)
HISTORICAL={'center':0.,'intermediate_left_b110':1.1,'intermediate_right_m080':-.8,'corner_left_b097':.97,'corner_right_m140':-1.4}

def validate_delta(delta):
    if not math.isfinite(delta) or abs(delta)>.005:raise ValueError('Finite initial Y perturbation up to 5mm required')

class FreeTrials(BiasRuntime):
    def __init__(self):
        super().__init__();self.delta=0.;original=self.original_initialize
        def initialize(config,m,d,kick,rail,probe):
            original(config,m,d,kick,rail,probe)
            q=int(m.jnt_qposadr[m.body_jntadr[m.body('ball').id]])
            d.qpos[q+1]+=self.delta
        self.original_initialize=initialize
        self.policy_rows=[]
    def reset_adapter(self):
        kick=super().reset_adapter();original=kick.update
        def update(data,ball_pos,ball_vel,sim_time):
            original(data,ball_pos,ball_vel,sim_time)
            if 3.5<=sim_time<=4.5:
                self.policy_rows.append(dict(time_s=sim_time,joint_target_rad=kick.target.tolist(),
                    actual_joints_rad=data.qpos[self.shooter.qpos].tolist(),
                    root_qpos=data.qpos[kick.root_q:kick.root_q+7].tolist(),
                    ball_sensor_w=kick.state.ball_pos_w.tolist(),
                    effective_target_b=kick.fsm.freekick_policy._debug_target_pos_b.tolist()))
        kick.update=update
        return kick
    def run_condition(self,bias,delta,path):
        validate_delta(delta);self.delta=delta;self.policy_rows=[]
        r=self.trial(bias,path)
        r['phase8c']={'initial_ball_delta_y_m':delta,'initial_only':True,'artificial_ball_forces':False,'policy_rows':self.policy_rows}
        path.write_text(json.dumps(r,indent=2),encoding='utf-8')
        s=summarize(r,path);s.update(delta_y_m=delta)
        contacts=r['phase8b2']['positive_foot_contacts']
        s['first_positive_contact']=contacts[0] if contacts else None
        s['classification_note']='Original center-based goal rule; nominal sphere/post margin additionally reported, not a new goal rule'
        return r,s

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--biases',type=float,nargs='+');p.add_argument('--deltas',type=float,nargs='+',default=DELTAS)
    p.add_argument('--repeats',type=int,default=1);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New phase8c output required')
    if a.repeats<1:p.error('Positive repeats required')
    for v in a.deltas:validate_delta(v)
    biases=a.biases if a.biases is not None else list(HISTORICAL.values())
    if len({identifier(b) for b in biases})!=len(biases):p.error('Unique biases required')
    a.output.mkdir(parents=True);before=sources();runtime=FreeTrials();rows=[]
    for bias in biases:
        for delta in a.deltas:
            first=None
            for n in range(a.repeats):
                path=a.output/f'{identifier(bias)}_dy{delta:+.3f}_{n+1:02d}.json'
                r,row=runtime.run_condition(bias,delta,path);row['repeat']=n+1
                if first is not None:
                    from phase5.benchmark import compare_physics
                    compare_physics(first,r)
                    for key in ('trajectory','positive_foot_contacts','final_state_sha256'):assert first['phase8b2'][key]==r['phase8b2'][key]
                first=r;rows.append(row)
                (a.output/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
                print(json.dumps(dict(bias=bias,dy_mm=delta*1000,repeat=n+1,outcome=row['outcome'],
                    y5=row['plane5']['position_w'][1] if row['plane5'] else None,foot_n=row['foot_peak_n'],failures=row['failures'])),flush=True)
                if row['fall'] is not None or any(r['engine_warnings']):raise RuntimeError('Physical instability; stop sweep')
    if before!=sources():raise AssertionError('Historical files changed')
    (a.output/'runtime.json').write_text(json.dumps(runtime.summary(),indent=2),encoding='utf-8')

if __name__=='__main__':main()
