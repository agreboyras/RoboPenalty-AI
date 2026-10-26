"""Native geometry and deterministic procedural RGB, never collision assets."""
from dataclasses import replace
import numpy as np
from phase7b.visual_scene import VisualScene, turf, markings, stadium, apply_appearance
from phase7c.environment import terraces,goal_net
from phase7c.scoreboard import screen_frame,score_lines,floodlights

def ground_texture_id(model):
    material=model.mat('groundplane').id
    texture=int(model.mat_texid[material,1])
    if texture<0 or int(model.tex_nchannel[texture])!=3:
        raise ValueError('Expected the existing RGB groundplane texture')
    return texture

def grass_pixels(height,width):
    rng=np.random.default_rng(7101)  # local visual RNG: never touches agent randomness
    noise=rng.normal(0,3,(height,width))
    blades=rng.normal(0,1.8,(height,1))
    yy,xx=np.mgrid[:height,:width]
    variation=noise+blades+2*np.sin(xx*.035)*np.cos(yy*.027)
    return np.clip(np.array([202,217,190])+variation[:,:,None],0,255).astype(np.uint8)

def prepare_model(model,stage):
    changes=apply_appearance(model,6)
    model.vis.map.zfar=125.
    model.vis.global_.offwidth=960;model.vis.global_.offheight=640
    if stage>=1:
        texture=ground_texture_id(model)
        width,height=int(model.tex_width[texture]),int(model.tex_height[texture])
        pixels=grass_pixels(height,width)
        start=int(model.tex_adr[texture]);model.tex_data[start:start+pixels.size]=pixels.ravel()
        changes.append('existing groundplane RGB buffer: deterministic grass grain')
    if stage>=2:
        for i in range(model.ngeom):
            name=model.geom(i).name or ''
            if name=='goal_back_net' or name.startswith('goal_net_'):
                if model.geom_contype[i] or model.geom_conaffinity[i]:raise RuntimeError('Goal detail is not visual-only')
                model.geom_rgba[i,3]=0
        changes.append('original shallow net hidden; visual depth/net in user_scn')
    if stage>=3:
        # Recolor existing skybox pixels; no new texture/asset or light is added.
        for tex in range(model.ntex):
            if tex==ground_texture_id(model):continue
            width,height=int(model.tex_width[tex]),int(model.tex_height[tex])
            if int(model.tex_nchannel[tex])!=3:continue
            yy=np.arange(height)%width
            factor=(yy/(max(1,width-1)))[:,None,None]
            gradient=np.array([12,22,37])[None,None,:]*(1-factor)+np.array([30,47,64])[None,None,:]*factor
            pixels=np.broadcast_to(gradient,(height,width,3)).astype(np.uint8)
            start=int(model.tex_adr[tex]);model.tex_data[start:start+pixels.size]=pixels.ravel()
        model.vis.headlight.ambient[:]=[.22,.22,.24]
        model.vis.headlight.diffuse[:]=[.65,.65,.65]
        model.vis.headlight.specular[:]=[.20,.20,.20]
        model.vis.rgba.haze[:]=[.065,.095,.14,1]
        changes.append('existing sky RGB/headlight only; no extra MuJoCo lights')
    return changes

class EnhancedScene(VisualScene):
    def __init__(self,model,stage,lod='medium'):
        self.texture_id=ground_texture_id(model) if stage>=1 else None
        self.enhancement_stage=stage;self.lod=lod
        if stage==0:
            super().__init__(6,lod!='none')
        else:
            self.primitives=[replace(p,color=(.10,.27,.15,1) if i%2 else (.09,.245,.135,1))
                             for i,p in enumerate(turf())]+markings()
            if stage>=2:
                self.primitives.extend(goal_net('low' if lod=='none' else lod))
                if lod!='none':self.primitives.extend(terraces(lod))
            elif lod!='none':self.primitives.extend(stadium())
        if stage>=3 and lod!='none':self.primitives.extend(screen_frame()+floodlights())
        self.static_primitives=list(self.primitives)
        self.screen_state=None;self.screen_updates=0
        self.update_status({'goals':0,'saves':0,'penalty':0,'total':5})

    def update_status(self,status):
        if self.enhancement_stage<3 or self.lod=='none':return False
        state=tuple(int(status.get(k,default)) for k,default in
                    (('goals',0),('saves',0),('penalty',0),('total',5)))
        if state==self.screen_state:return False
        self.screen_state=state;self.screen_updates+=1
        self.primitives=self.static_primitives+score_lines(dict(zip(('goals','saves','penalty','total'),state)))
        return True

    def populate(self,scene,*,replace=True):
        start=0 if replace else int(scene.ngeom)
        count=super().populate(scene,replace=replace)
        if self.texture_id is not None:
            for index,item in enumerate(self.primitives,start):
                if item.name.startswith('turf_'):
                    g=scene.geoms[index];g.texid=self.texture_id
                    g.texuniform=1;g.texrepeat[:]=[1.,3.]
                    g.reflectance=0.;g.specular=0.
        return count
