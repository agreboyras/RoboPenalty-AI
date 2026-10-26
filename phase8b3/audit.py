from bootstrap import *
import hashlib
import json
import numpy as np
import mujoco
import yaml
from phase8b2.integrity import protected_sources
from lateral_scene import build_scene,Limits

def main():
    out=HERE/'results';out.mkdir(exist_ok=True)
    if (out/'audit.json').exists():raise ValueError('Audit exists')
    protected=protected_sources()
    protected={k:v for k,v in protected.items() if not Path(k).is_relative_to(HERE)}
    for p in (PROJECT/'phase8b2').glob('*'):
        if p.is_file():protected[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'protected_before.json').write_text(json.dumps(protected,indent=2),encoding='utf-8')
    m,d,sh,gk,rail=build_scene(PROJECT.parent/'RoboNaldo_Deploy',PROJECT.parent/'unitree_mujoco',Limits())
    caps=np.array(yaml.safe_load((PROJECT.parent/'RoboNaldo_Deploy/deploy_mujoco/config/mujoco_freekick.yaml').read_text())['tau_limit'])
    joints=[]
    for i,j in enumerate(gk.joints):
        name=m.joint(int(j)).name;a=int(gk.actuators[i])
        initial=.25 if 'left_shoulder_roll' in name else -.25 if 'right_shoulder_roll' in name else .3 if 'elbow' in name else 0.
        d.qpos[gk.qpos[i]]=initial
        joints.append(dict(name=name,index=int(j),qpos=int(gk.qpos[i]),dof=int(gk.dofs[i]),actuator=a,
            joint_range=m.jnt_range[j].tolist(),initial_reference_rad=initial,kp=70.,kd=5.,
            software_torque_clip_n_m=float(caps[i]),gear=m.actuator_gear[a].tolist(),
            actuator_ctrl_limited=bool(m.actuator_ctrllimited[a]),actuator_ctrlrange=m.actuator_ctrlrange[a].tolist(),
            joint_force_limited=bool(m.jnt_actfrclimited[j]),joint_force_range=m.jnt_actfrcrange[j].tolist()))
    mujoco.mj_forward(m,d)
    geometry=[dict(id=int(g),name=m.geom(int(g)).name,contype=int(m.geom_contype[g]),conaffinity=int(m.geom_conaffinity[g]),
        body=m.body(int(m.geom_bodyid[g])).name,position=d.geom_xpos[g].tolist()) for g in gk.geoms]
    contacts=[dict(a=m.geom(c.geom1).name,b=m.geom(c.geom2).name,distance=float(c.dist)) for c in d.contact[:d.ncon] if c.geom1 in gk.geoms or c.geom2 in gk.geoms]
    result=dict(joints=joints,geometry=geometry,initial_contacts=contacts,exclude_signature=m.exclude_signature.tolist(),
        counts=dict(nq=m.nq,nv=m.nv,nu=m.nu,ngeom=m.ngeom),pelvis=d.xpos[gk.pelvis].tolist(),
        rail_joint=int(rail.joint),rail_actuator=rail.actuator,rail_limits=Limits().__dict__,
        pelvis_constraint='Only lateral slide; pelvis height/orientation cannot crouch or lean. Joint motion is not free balance.',
        model_opt=dict(disableflags=int(m.opt.disableflags),enableflags=int(m.opt.enableflags)))
    (out/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['# Auditoría articular 8B.3','','| Articulación | Actuador | Rango rad | Ref histórica | Clip software Nm | Límite fuerza articular Nm |','|---|---:|---|---:|---:|---|']
    for r in joints:lines.append(f"| {r['name']} | {r['actuator']} | {r['joint_range']} | {r['initial_reference_rad']} | {r['software_torque_clip_n_m']} | {r['joint_force_range']} |")
    lines+=['','PD histórico: Kp=70, Kd=5; motores 29–57, guía 58. Pelvis anclada en altura y orientación, con desplazamiento lateral físico. No representa equilibrio humanoide libre.',
        '','Se conservan piernas/tobillos: flexionar rodillas no puede bajar la pelvis y puede descargar/despegar pies. Esta variante probará brazos y una inclinación de torso pequeña antes de considerar cambios de piernas.',
        '',f'Contactos iniciales del arquero: `{contacts}`. Las máscaras y exclusiones completas están en audit.json; se medirán autocolisiones activas y penetraciones en ejecución, sin activar contactos nuevos.']
    (HERE/'AUDITORIA.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(joints=len(joints),contacts=contacts,collidable_geoms=[g['name'] for g in geometry if g['contype'] or g['conaffinity']])))
if __name__=='__main__':main()
