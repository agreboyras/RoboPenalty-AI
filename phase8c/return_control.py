"""Keep B's interception intact; retain its return feedback after logical DONE."""
from dataclasses import replace

class ReturnControl:
    def __init__(self,base,limits,enabled=True):
        self.base,self.limits,self.enabled=base,limits,enabled;self.rows=[];self.previous=0.
    def __getattr__(self,key):return getattr(self.base,key)
    def step(self,o):
        d=self.base.step(o);raw=d.selected_target_m
        if self.enabled and d.state=='DONE':
            command=max(-.12,min(.12,-2.*o.keeper_q-.4*o.keeper_v))
            d=replace(d,selected_target_m=command,command_changed=command!=self.previous,
                reason='episode_done_keep_original_return_feedback')
        self.previous=d.selected_target_m
        context=self.base.context;servo=context['control']
        self.rows.append(dict(time_s=o.time_s,state=d.state,reason=d.reason,
            original_B_command_m=raw,executed_command_m=d.selected_target_m,q_m=o.keeper_q,v_mps=o.keeper_v,
            reference_q_m=servo.position,reference_v_mps=servo.velocity,
            enabled=self.enabled,extension_active=self.enabled and d.state=='DONE'))
        row=context['rows'][-1]
        row.update(original_B_command_m=raw,servo_command_m=d.selected_target_m,
            tracking_error_m=d.selected_target_m-o.keeper_q,reason=d.reason,return_extension_active=self.enabled and d.state=='DONE')
        return d
