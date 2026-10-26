"""A single torque-producing PD with causal, rate-limited posture references."""
import math
import numpy as np

def direction(decision,observation,previous='CENTER'):
    if decision is None or decision.state!='TRACKING':return 'WAIT'
    p=decision.prediction
    if not p.get('valid'):return previous if previous in ('LEFT','RIGHT','CENTER') else 'CENTER'
    y=p.get('y_w')
    if y is None or not math.isfinite(y):return 'CENTER'
    delta=y-(observation.rail_origin_y-observation.keeper_q)
    if delta>.18:return 'LEFT'  # world +Y, keeper anatomical right
    if delta<-.18:return 'RIGHT'
    if abs(delta)<.10:return 'CENTER'
    return previous if previous in ('LEFT','RIGHT','CENTER') else 'CENTER'

class PosturePD:
    SPEED=.6
    ACCELERATION=1.5
    def __init__(self,model,keeper,rail,mode='dynamic'):
        if mode not in ('historical','dynamic'):raise ValueError(mode)
        self.model,self.keeper,self.rail,self.mode=model,keeper,rail,mode
        self.names=[model.joint(int(j)).name.split('/')[-1] for j in keeper.joints]
        self.reference=None;self.velocity=np.zeros(29);self.decision=self.observation=None
        self.state='WAIT';self.rows=[];self.max_v=self.max_error=self.max_tau=0.;self.violations=[]
        self.self_contacts=[];self.floor_contacts=set();self.max_penetration=0.;self.steps=0
        self.initial_pelvis=None;self.max_pelvis_error=0.;self.max_joint_excursion=0.
        self.snapshots={};self.state_since=0.;self.previous_state='WAIT';self.max_actual_torque=0.
        self.ball_geom=model.geom('ball_geom').id

    def snapshot(self,label,data):
        if label not in self.snapshots:
            self.snapshots[label]=dict(time_s=float(data.time),qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),ctrl=data.ctrl.tolist(),state=self.state)

    def notify(self,decision,observation):
        self.decision,self.observation=decision,observation

    def target(self,base):
        target=np.array(base,copy=True)
        if self.mode=='historical':return target
        state=direction(self.decision,self.observation,self.state) if self.observation else 'WAIT'
        if self.decision and self.decision.state in ('RETURNING','DONE'):state='RECOVERY'
        self.state=state
        values={'left_shoulder_pitch_joint':-.22,'right_shoulder_pitch_joint':-.22,
                'left_shoulder_roll_joint':.42,'right_shoulder_roll_joint':-.42,
                'left_elbow_joint':.65,'right_elbow_joint':.65,'waist_pitch_joint':.035}
        if state=='LEFT':values.update(right_shoulder_roll_joint=-.78,left_shoulder_roll_joint=.30,waist_roll_joint=-.035)
        elif state=='RIGHT':values.update(left_shoulder_roll_joint=.78,right_shoulder_roll_joint=-.30,waist_roll_joint=.035)
        elif state=='CENTER':values.update(left_shoulder_pitch_joint=-.34,right_shoulder_pitch_joint=-.34,left_elbow_joint=.80,right_elbow_joint=.80)
        for n,value in values.items():target[self.names.index(n)]=value
        ranges=self.model.jnt_range[self.keeper.joints]
        if np.any(target<ranges[:,0]+.02) or np.any(target>ranges[:,1]-.02):raise ValueError('Unsafe posture target')
        return target

    def command(self,data,base,torque_limits):
        if self.reference is None:self.reference=np.array(base,copy=True);self.base=self.reference.copy()
        target=self.target(base)
        if self.state!=self.previous_state:self.state_since=float(data.time);self.previous_state=self.state
        if self.mode=='historical':self.reference=target
        else:
            dt=self.model.opt.timestep;delta=target-self.reference
            acceleration=np.clip(8*delta-4*self.velocity,-self.ACCELERATION,self.ACCELERATION)
            self.velocity=np.clip(self.velocity+acceleration*dt,-self.SPEED,self.SPEED)
            self.reference+=self.velocity*dt
        q=data.qpos[self.keeper.qpos];v=data.qvel[self.keeper.dofs]
        torque=np.clip(70*(self.reference-q)-5*v,-torque_limits,torque_limits)
        self.max_v=max(self.max_v,float(abs(v).max()));self.max_error=max(self.max_error,float(abs(self.reference-q).max()))
        self.max_tau=max(self.max_tau,float(abs(torque).max()));self.max_joint_excursion=max(self.max_joint_excursion,float(abs(q-self.base).max()))
        actual_torque=data.qfrc_actuator[self.keeper.dofs]
        self.max_actual_torque=max(self.max_actual_torque,float(abs(actual_torque).max()))
        joint_caps=np.maximum(abs(self.model.jnt_actfrcrange[self.keeper.joints,0]),abs(self.model.jnt_actfrcrange[self.keeper.joints,1]))
        if np.any(abs(actual_torque)>joint_caps+1e-6):self.violations.append('actual_joint_torque_limit')
        ranges=self.model.jnt_range[self.keeper.joints]
        if np.any(q<ranges[:,0]-.02) or np.any(q>ranges[:,1]+.02):self.violations.append('joint_range')
        if abs(v).max()>3.:self.violations.append('measured_joint_speed_gt_3rad_s')
        if self.steps%10==0:
            self.rows.append(dict(time_s=float(data.time),state=self.state,reference_rad=self.reference.tolist(),
                reference_velocity_rad_s=self.velocity.tolist(),actual_rad=q.tolist(),actual_velocity_rad_s=v.tolist(),
                commanded_torque_nm=torque.tolist(),actual_joint_torque_nm=data.qfrc_actuator[self.keeper.dofs].tolist(),rail_q_m=float(data.qpos[self.rail.qpos]),
                decision_state=self.decision.state if self.decision else None,
                prediction=self.decision.prediction if self.decision else None))
        pelvis=data.xpos[self.keeper.pelvis].copy();expected=data.xpos[self.rail.carriage]+[0,0,.793]
        self.max_pelvis_error=max(self.max_pelvis_error,float(abs(pelvis-expected).max()))
        for c in data.contact[:data.ncon]:
            a,b=int(c.geom1),int(c.geom2)
            if (a==self.ball_geom and b in self.keeper.geoms) or (b==self.ball_geom and a in self.keeper.geoms):
                if c.efc_address>=0 and data.efc_force[c.efc_address]>0:self.snapshot('ball_contact',data)
            if a in self.keeper.geoms and b in self.keeper.geoms:
                self.max_penetration=min(self.max_penetration,float(c.dist))
                pair=(self.model.geom(a).name,self.model.geom(b).name)
                if pair not in self.self_contacts:self.self_contacts.append(pair)
            if a in self.keeper.geoms and self.model.geom(b).name=='floor':self.floor_contacts.add(self.model.geom(a).name)
            if b in self.keeper.geoms and self.model.geom(a).name=='floor':self.floor_contacts.add(self.model.geom(b).name)
        self.steps+=1
        label='wait' if self.state=='WAIT' and data.time>=1.8 else 'reaction_'+self.state.lower() if self.state in ('LEFT','RIGHT','CENTER') and data.time-self.state_since>=.45 else 'recovery' if self.state=='RECOVERY' and data.time-self.state_since>=.45 else None
        if label:self.snapshot(label,data)
        if 4.5<=data.time<=5.3:self.snapshot(f'sequence_{int((data.time-4.5)/.1):02d}',data)
        return torque

    def summary(self):
        errors=sorted(set(self.violations))
        if self.max_penetration<-.01:errors.append('self_penetration_gt_1cm')
        if self.max_pelvis_error>.001:errors.append('pelvis_constraint_error')
        return dict(mode=self.mode,names=self.names,rows=self.rows,steps=self.steps,
            max_joint_speed_rad_s=self.max_v,max_tracking_error_rad=self.max_error,max_commanded_torque_nm=self.max_tau,
            max_joint_excursion_rad=self.max_joint_excursion,max_pelvis_constraint_error_m=self.max_pelvis_error,
            max_actual_joint_torque_nm=self.max_actual_torque,snapshots=self.snapshots,
            self_contact_pairs=self.self_contacts,min_self_contact_distance_m=self.max_penetration,
            floor_contact_geoms=sorted(self.floor_contacts),failures=errors,passed=not errors,
            reference_speed_limit_rad_s=self.SPEED,reference_acceleration_limit_rad_s2=self.ACCELERATION,
            state_direction_contract='Current keeper-B prediction minus current keeper world Y; never preset label or future trace')
