"""Native MjvGeom primitives only: these never enter MjModel or contacts."""
from dataclasses import dataclass
import math
import numpy as np
import mujoco
from phase7b import layout

@dataclass(frozen=True)
class Primitive:
    name: str
    kind: str
    position: tuple
    size: tuple
    color: tuple
    end: tuple | None = None
    yaw: float = 0.
    emission: float = 0.

def box(name, center, halfsize, color):
    return Primitive(name,'box',tuple(center),tuple(halfsize),tuple(color))

def turf():
    # Tops at 0.0005 m are visual only. No coplanar surface or contact layer.
    return [box(f'turf_{i:02d}',(-14+2*i,0,-.005),(1,12,.0055),
                (.065,.31,.135,1) if i%2 else (.052,.265,.11,1)) for i in range(10)]

def markings():
    result=[]
    for name,a,b in layout.marking_segments():
        dx,dy=b[0]-a[0],b[1]-a[1]
        result.append(Primitive(name,'box',((a[0]+b[0])/2,(a[1]+b[1])/2,.003),
            (math.hypot(dx,dy)/2,layout.LINE_WIDTH/2,.001),(1.,1.,.94,1.),
            yaw=math.atan2(dy,dx)))
    result.append(Primitive('penalty_spot','cylinder',(*layout.SPOT,.0035),
                            (.09,.0015,0),(1.,1.,.94,1.)))
    return result

def connector(name,a,b,radius,color):
    return Primitive(name,'capsule',tuple(a),(radius,0,0),tuple(color),tuple(b))

def stadium():
    """Stepped terraces, own RP signs and decorative floodlights; no meshes."""
    result=[]
    navy=(.035,.065,.11,1);blue=(.10,.27,.42,1);gold=(.86,.62,.22,1)
    concrete=(.22,.27,.29,1);white=(.87,.92,.92,1)
    # All terrace footprints are outside the approved playing rectangle.
    for side in (-1,1):
        result.append(box(f'walkway_{side}',(-4,side*13.3,-.015),(12,.9,.02),concrete))
        for row in range(4):
            y=side*(14.7+1.1*row);height=.45*(row+1)
            result.append(box(f'terrace_{side}_{row}',(-4,y,height/2),(11.8,.55,height/2),navy))
            for section in range(5):
                result.append(box(f'seating_{side}_{row}_{section}',(-13.5+4.75*section,y,height+.08),
                    (2.15,.40,.08),gold if section==2 else blue))
        for i,x in enumerate((-12.,-6.,0.)):
            y=side*12.9
            result.append(box(f'advert_{side}_{i}',(x,y,.42),(2.6,.07,.42),blue if i%2 else navy))
            result.append(box(f'advert_stripe_{side}_{i}',(x,y,.79),(2.6,.08,.025),gold))
            # Two original stroke letters: RP. No external logos or textures.
            face=y-side*.085
            for letter,offset in [('R',-.55),('P',.15)]:
                strokes=[((0,0),(0,.48)),((0,.48),(.28,.48)),
                         ((.28,.48),(.28,.25)),((0,.25),(.28,.25))]
                if letter=='R':strokes.append(((0,.25),(.30,0)))
                for j,(a,b) in enumerate(strokes):
                    result.append(connector(f'advert_logo_{side}_{i}_{letter}_{j}',
                        (x+offset+a[0],face,.16+a[1]),(x+offset+b[0],face,.16+b[1]),.018,white))
    for row in range(4):
        x=8.2+1.1*row;height=.45*(row+1)
        result.append(box(f'rear_terrace_{row}',(x,0,height/2),(.55,12,height/2),navy))
        for section in range(5):
            result.append(box(f'rear_seating_{row}_{section}',(x,-9.6+4.8*section,height+.08),
                (.40,2.15,.08),gold if section==2 else blue))
    for i,y in enumerate((-9.,-5.,5.,9.)):
        result.append(box(f'rear_advert_{i}',(6.5,y,.42),(.07,1.8,.42),blue if i%2 else navy))
        result.append(box(f'rear_advert_stripe_{i}',(6.5,y,.79),(.08,1.8,.025),gold))
    for x in (-15.,7.):
        for y in (-13.5,13.5):
            name=f'floodlight_{x}_{y}'
            result.append(connector(name+'_mast',(x,y,0),(x,y,7.5),.055,concrete))
            result.append(box(name+'_housing',(x,y,7.5),(.6,.16,.3),navy))
            result.append(Primitive(name+'_lamp','box',(x,y-(.18 if y>0 else -.18),7.5),
                                    (.53,.025,.22),(1.,.94,.72,1.),emission=.8))
    return result

class VisualScene:
    def __init__(self, stage, decoration=True):
        self.primitives = turf() if stage>=2 else []
        if stage>=3:self.primitives.extend(markings())
        if stage>=6 and decoration:self.primitives.extend(stadium())

    def populate(self, scene, *, replace=True):
        start = 0 if replace else int(scene.ngeom)
        count = len(self.primitives)
        if start+count > scene.maxgeom:
            raise RuntimeError(f'Visual scene needs {start+count} geoms; capacity is {scene.maxgeom}')
        for index, item in enumerate(self.primitives,start):
            geom=scene.geoms[index]
            kind = getattr(mujoco.mjtGeom,'mjGEOM_'+item.kind.upper())
            c,s=math.cos(item.yaw),math.sin(item.yaw)
            rotation=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
            mujoco.mjv_initGeom(geom,kind,np.asarray(item.size,dtype=float),
                np.asarray(item.position,dtype=float),rotation.ravel(),
                np.asarray(item.color,dtype=np.float32))
            if item.end is not None:
                mujoco.mjv_connector(geom,kind,item.size[0],
                    np.asarray(item.position,dtype=float),np.asarray(item.end,dtype=float))
            geom.category = mujoco.mjtCatBit.mjCAT_DECOR
            geom.objtype = mujoco.mjtObj.mjOBJ_UNKNOWN
            geom.objid = -1
            geom.specular = .05
            geom.emission = item.emission
            geom.label = ''
        scene.ngeom=start+count
        return count

def apply_appearance(model, stage):
    changes = []
    if stage>=2:
        floor=model.geom('floor').id
        model.geom_matid[floor]=-1
        model.geom_rgba[floor]=[.035,.12,.065,1]
        changes.append('floor: visual color and material only')
    if stage>=3:
        for index in range(model.ngeom):
            if (model.geom(index).name or '').startswith('pitch_'):
                if model.geom_contype[index] or model.geom_conaffinity[index]:
                    raise RuntimeError('Experimental marking unexpectedly has contacts')
                model.geom_rgba[index,3]=0
                changes.append('hidden experimental marking: '+model.geom(index).name)
    if stage>=4:
        # Keep the original scoring frame/net. Hide only the orange test backstop;
        # its dynamic body, free joint, mass and collisions remain authoritative.
        model.geom_rgba[model.geom('box_geom').id,3]=0
        changes.append('box_geom: hidden rendering; dynamic backstop unchanged')
        for index in range(model.ngeom):
            if (model.geom(index).name or '').startswith('goal_'):
                if model.geom_contype[index] or model.geom_conaffinity[index]:
                    raise RuntimeError('Existing visual goal unexpectedly has contacts')
    return changes
