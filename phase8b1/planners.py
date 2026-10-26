"""Causal lateral planners; no MuJoCo data, future ball samples or files."""
from dataclasses import replace
import math
from agent import GoalkeeperAgent,clip
from lateral_control import LateralControl
from types import SimpleNamespace

def stopping_interval(q,v,h,limits):
    """Ideal bounded-acceleration endpoints with final v=0, not plant guarantees."""
    a=limits.reference_acceleration;vmax=limits.reference_speed
    v=float(v);h=max(0.,h)
    if h<abs(v)/a:
        endpoint=q+v*h-math.copysign(.5*a*h*h,v)
        endpoint=clip(endpoint,-limits.command_travel,limits.command_travel)
        return (endpoint,endpoint),False
    def upper(initial,total):
        if initial>vmax:
            t=(initial-vmax)/a
            return initial*t-.5*a*t*t+upper(vmax,total-t)
        peak=min(vmax,(a*total+initial)/2)
        ta=(peak-initial)/a;tb=peak/a;cruise=max(0.,total-ta-tb)
        return initial*ta+.5*a*ta*ta+peak*cruise+.5*peak*tb
    return (clip(q-upper(-v,h),-limits.command_travel,limits.command_travel),
            clip(q+upper(v,h),-limits.command_travel,limits.command_travel)),True

def servo_rollout(command,observation,h,limits,snapshot):
    """Reduced slider model, no MuJoCo rollout or future ball integration.

    Uses the unchanged reference/force laws and an ideal viscous plant. Ground
    friction, contacts and joint coupling are omitted; predictions are estimates.
    """
    if h<=0:return observation.keeper_q,observation.keeper_v
    rail=SimpleNamespace(carried_mass=snapshot['mass'],damping=snapshot['damping'])
    servo=LateralControl(limits,rail)
    servo.position=snapshot['reference_q'];servo.velocity=snapshot['reference_v']
    servo.acceleration=snapshot['reference_a'];servo.select(command)
    q,v=observation.keeper_q,observation.keeper_v
    count=max(1,math.ceil(h/.02));dt=h/count
    for _ in range(count):
        servo.advance_reference(dt)
        acc=(servo.force(q,v)-rail.damping*v)/rail.carried_mass
        v+=acc*dt;q+=v*dt
    return q,v

class InterceptionPlanner:
    def __init__(self,limits,variant,snapshot):
        if variant not in ('B','C'):raise ValueError(variant)
        self.base=GoalkeeperAgent(limits);self.limits=limits;self.variant=variant;self.snapshot=snapshot
        self.command=0.;self.last_command=-math.inf;self.first_command_time=None;self.details={}

    def __getattr__(self,key):return getattr(self.base,key)

    def step(self,o):
        d=self.base.step(o);old=self.command;self.details={}
        if d.reason in ('nonfinite_or_invalid_observation','invalid_rail_axis'):
            self.command=0.
        elif d.state=='RETURNING':
            # Reactive centering compensates the observed static residual without
            # changing the servo/gains/force. No timed motion sequence is used.
            self.command=clip(-2.*o.keeper_q-.4*o.keeper_v,-.12,.12)
            self.details={'return_feedback':'clip(-2*q - 0.4*v, +/-0.12m)'}
        elif d.state!='TRACKING':self.command=0.
        elif d.prediction['valid']:
            tactical=clip(self.base.filtered,-self.limits.command_travel,self.limits.command_travel)
            command=tactical
            h=max(0.,d.prediction['eta_s']-.05)
            interval,can_stop=stopping_interval(o.keeper_q,o.keeper_v,h,self.limits)
            self.details=dict(tactical_target_m=tactical,rest_reachable_interval_estimate_m=interval,
                              can_stop_before_estimated_crossing=can_stop,horizon_s=h)
            if self.variant=='C' and h>0:
                snap=self.snapshot()
                # Candidate servo goals differ from predicted reachable endpoints.
                # Braking is evaluated by the same reference law and stopping distance.
                candidates=sorted(set([self.command,tactical,0.,-self.limits.command_travel,
                                       self.limits.command_travel,*[self.limits.command_travel*k/4 for k in range(-4,5)]]))
                evaluations=[]
                for candidate in candidates:
                    q,v=servo_rollout(candidate,o,h,self.limits,snap)
                    stop=q+v*abs(v)/(2*self.limits.reference_acceleration)
                    direction=1 if tactical>=o.keeper_q else -1
                    overshoot=max(0.,direction*(stop-tactical))
                    cost=(q-tactical)**2+.3*overshoot**2+.0005*abs(candidate-self.command)
                    evaluations.append((cost,candidate,q,v))
                cost,command,q,v=min(evaluations)
                self.details.update(model_arrival_q_m=q,model_arrival_v_mps=v,model_cost=cost,
                                    model='reference servo + ideal viscous slider; contacts/friction omitted')
            # Retain command on invalid predictions. No collapse to current q as
            # ETA approaches zero. Both candidates keep original update throttling.
            if o.time_s-self.last_command>=.06 and abs(command-self.command)>=.01:
                self.command=clip(command,-self.limits.command_travel,self.limits.command_travel)
                self.last_command=o.time_s
        if self.first_command_time is None and abs(self.command)>=.01:self.first_command_time=o.time_s
        return replace(d,selected_target_m=self.command,command_changed=self.command!=old,
                       reason=('hold_tactical_target' if self.variant=='B' else 'temporal_servo_plan') if d.state=='TRACKING' else d.reason)

class LoggedPlanner:
    def __init__(self,limits,variant,context):
        self.variant=variant;self.context=context
        def snapshot():
            c=context['control']
            return dict(reference_q=c.position,reference_v=c.velocity,reference_a=c.acceleration,
                        mass=c.rail.carried_mass,damping=c.rail.damping)
        self.agent=GoalkeeperAgent(limits) if variant=='A' else InterceptionPlanner(limits,variant,snapshot)
    def __getattr__(self,key):return getattr(self.agent,key)
    def step(self,o):
        d=self.agent.step(o)
        base=self.agent if self.variant=='A' else self.agent.base
        tactical=base.filtered if base.filtered is not None else 0.
        c=self.context['control']
        self.context['rows'].append(dict(time_s=o.time_s,ball_position_w=o.ball_position_w,
            ball_velocity_w=o.ball_velocity_w,prediction=d.prediction,tactical_target_m=tactical,
            bounded_tactical_target_m=clip(tactical,-c.limits.command_travel,c.limits.command_travel),
            reachable_interval_estimate_m=d.reachable_interval_m,servo_command_m=d.selected_target_m,
            actual_q_m=o.keeper_q,actual_v_mps=o.keeper_v,tracking_error_m=d.selected_target_m-o.keeper_q,
            reference_q_m=c.position,reference_v_mps=c.velocity,state=d.state,reason=d.reason,
            planner_details=getattr(self.agent,'details',{})))
        return d
