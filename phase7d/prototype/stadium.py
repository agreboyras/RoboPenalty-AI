"""Isolated render-only bowl study. No runtime, stepping or agent integration."""
from dataclasses import replace
import math
import numpy as np
from phase7b.visual_scene import VisualScene, box, connector, turf, markings
from phase7c.environment import goal_net
from phase7c.scoreboard import screen_frame, score_lines
from phase7c.visual_scene import prepare_model, ground_texture_id

WHITE=(.72,.74,.76,1); RED=(.48,.025,.035,1); DARK=(.055,.065,.075,1)
LEVELS=((0,4,.8,5.5),(5,10,6.4,11.8),(11,17,12.8,19.5))

def crowd_pixels(width=512):
    """Procedural spectator pattern, not individual people or external imagery."""
    rng=np.random.default_rng(7401)
    yy,xx=np.mgrid[:width,:width]
    row=yy//16; col=(xx+(row%2)*6)//12
    palette=np.array([[215,211,202],[156,23,32],[24,27,31],[193,188,177]])
    choices=rng.choice(4,(34,45),p=[.46,.29,.19,.06])
    image=palette[choices[row,col]].copy()
    x=(xx+(row%2)*6)%12; y=yy%16
    image[(x<2)|(y>12)]=[27,29,33]
    heads=((x-6)**2+(y-3)**2)<7
    image[heads]=[160,132,111]
    image=np.clip(image+rng.integers(-12,13,image.shape),0,255).astype(np.uint8)
    return np.tile(image,(6,1,1))

def prepare(model):
    changes=prepare_model(model,3)
    # Reuse the existing cubemap only inside this disposable render model.
    # Background skybox is disabled in populate; no texture metadata is changed.
    assert int(model.tex_width[0])==512 and int(model.tex_height[0])==3072
    pixels=crowd_pixels();start=int(model.tex_adr[0])
    model.tex_data[start:start+pixels.size]=pixels.ravel()
    model.vis.global_.fovy=65
    model.vis.map.zfar=220
    model.vis.headlight.ambient[:]=[.28,.28,.30]
    return changes+['existing cubemap RGB reused for crowd; background skybox disabled']

class BowlScene(VisualScene):
    def __init__(self,model,decoration=True):
        self.decoration=decoration
        self.texture_id=ground_texture_id(model)
        self.material_id=model.mat('groundplane').id
        self.rotations={};self.crowd=set()
        self.primitives=[replace(p,color=(.12,.29,.15,1) if i%2 else (.105,.26,.13,1))
                         for i,p in enumerate(turf())]+markings()+goal_net('medium')
        if decoration:self.bowl()
        self.static=list(self.primitives)
        self.update_status(dict(goals=0,saves=0,penalty=1,total=5))

    def panel(self,name,center,size,u,v,w,color,textured=False):
        self.primitives.append(box(name,center,size,color))
        self.rotations[name]=np.column_stack((u,v,w)).ravel()
        if textured:self.crowd.add(name)

    def bowl(self):
        sections=[]
        # Rear semicircle continuous with both straight side terraces.
        segments=32
        for i in range(segments):
            a=-math.pi/2+(i+.5)*math.pi/segments
            sections.append((np.array([-8.,0.,0.]),np.array([math.cos(a),math.sin(a),0.]),
                             np.array([math.sin(a),-math.cos(a),0.]),math.pi/segments))
        for side in (-1,1):
            for x in (-20.25,-16.75,-13.25,-9.75):
                sections.append((np.array([x,0.,0.]),np.array([0.,side,0.]),
                                 np.array([side,0.,0.]),None))
        for s,(origin,radial,tangent,angle) in enumerate(sections):
            for level,(r0,r1,z0,z1) in enumerate(LEVELS):
                r0+=20;r1+=20
                slope=math.atan2(z1-z0,r1-r0)
                along=radial*math.cos(slope)+np.array([0,0,math.sin(slope)])
                normal=np.cross(tangent,along)
                radius=(r0+r1)/2
                width=(2*radius*math.tan(angle/2) if angle else 3.5)
                center=origin+radial*radius;center[2]=(z0+z1)/2
                tag=f'bowl_{s}_{level}'
                self.panel(tag,center,(width/2+.025,math.hypot(r1-r0,z1-z0)/2,.035),
                           tangent,along,normal,(.62,.62,.62,1),True)
                for row,fraction in enumerate((.33,.66)):
                    r=r0+(r1-r0)*fraction
                    c=origin+radial*r;c[2]=z0+(z1-z0)*fraction+.025
                    w=(2*r*math.tan(angle/2) if angle else 3.5)
                    self.panel(tag+f'_step_{row}',c,(w/2+.025,.14,.045),tangent,radial,
                               np.array([0,0,1.]),(.34,.35,.37,1))
                # Concourse fascia, front guardrail and radial aisle stripe.
                for suffix,r,z,h,color in (('fascia',r0,z0-.35,.30,WHITE),
                                           ('red_band',r0,z0-.08,.08,RED),
                                           ('rim',r1,z1,.12,WHITE)):
                    c=origin+radial*r;c[2]=z
                    w=(2*r*math.tan(angle/2) if angle else 3.5)
                    self.panel(tag+suffix,c,(w/2+.03,.13,h),tangent,radial,
                               np.array([0,0,1.]),color)
                aisle=center+tangent*(width/2-.12)+normal*.045
                self.panel(tag+'aisle',aisle,(.09,math.hypot(r1-r0,z1-z0)/2,.012),
                           tangent,along,normal,(.38,.38,.40,1))
                if s%3==0:
                    c=origin+radial*(r0+.1);c[2]=z0+.45
                    self.panel(tag+'entrance',c,(.40,.08,.42),tangent,radial,
                               np.array([0,0,1.]),DARK)
            # Continuous roof lip and emissive strip; not additional lights.
            c=origin+radial*37;c[2]=20.1
            width=(74*math.tan(angle/2) if angle else 3.5)
            self.panel(f'roof_{s}',c,(width/2+.04,.8,.16),tangent,radial,np.array([0,0,1.]),DARK)
            c=c-radial*.7;c[2]=19.9
            self.panel(f'lamp_{s}',c,(width/2-.10,.16,.10),tangent,radial,np.array([0,0,1.]),(1,.95,.85,1))
        # Screen supported by a steel frame above the rear upper tier.
        for y in (-6.5,6.5):
            self.primitives.append(connector(f'screen_support_{y}',(27.8,y,16),(27.8,y,24.5),.15,DARK))
        self.primitives.append(connector('screen_truss',(27.8,-7,22.5),(27.8,7,22.5),.18,WHITE))
        for p in screen_frame():
            if 'pole' not in p.name:self.primitives.append(self.screen_transform(p))

    @staticmethod
    def screen_transform(p):
        def position(v):return (27+(v[0]-11.7)*1.4,v[1]*1.4,22.5+(v[2]-5)*1.4)
        return replace(p,position=position(p.position),size=tuple(v*1.4 for v in p.size),
                       end=position(p.end) if p.end else None,
                       color=(.65,.025,.035,1) if p.name=='screen_accent' else p.color)

    def update_status(self,status):
        self.primitives=self.static+([self.screen_transform(p) for p in score_lines(status)] if self.decoration else [])

    def populate(self,scene,*,replace=True):
        import mujoco
        start=0 if replace else int(scene.ngeom)
        count=super().populate(scene,replace=replace)
        scene.flags[mujoco.mjtRndFlag.mjRND_SKYBOX]=False
        scene.flags[mujoco.mjtRndFlag.mjRND_HAZE]=False
        for index,p in enumerate(self.primitives,start):
            g=scene.geoms[index]
            if p.name in self.rotations:g.mat[:]=self.rotations[p.name].reshape(3,3)
            if p.name in self.crowd:
                g.matid=self.material_id;g.texid=0;g.texuniform=0;g.texrepeat[:]=[4,3];g.emission=.10
            if p.name.startswith('turf_'):
                g.matid=self.material_id;g.texid=self.texture_id;g.texuniform=1;g.texrepeat[:]=[1,3];g.specular=0
            if p.name.startswith('lamp_'):g.emission=1
        return count
