"""Own low-cost terraces, seated crowd silhouettes and a visual-only goal net."""
import numpy as np
from phase7b.visual_scene import Primitive,box,connector,stadium

NAVY=(.045,.065,.095,1)
CONCRETE=(.26,.29,.32,1)
CYAN=(.06,.43,.54,1)
AMBER=(.75,.36,.12,1)
SEATS=(CYAN,(.10,.23,.34,1),AMBER,(.13,.32,.43,1),CYAN)

def terraces(lod):
    result=[]
    # Keep the perimeter advertising primitives; replace the old flat terraces.
    result.extend(p for p in stadium() if p.name.startswith(('advert_','rear_advert','floodlight_'))
                  and 'logo' not in p.name)
    for side in (-1,1):
        result.append(box(f'concourse_{side}',(-4,side*13.4,-.02),(12.1,1.1,.025),CONCRETE))
        for row in range(4):
            y=side*(14.7+row*1.1);h=.5*(row+1)
            result.append(box(f'side_step_{side}_{row}',(-4,y,h/2),(11.8,.55,h/2),CONCRETE))
            for section in range(5):
                x=-13.5+4.75*section
                result.append(box(f'seat_{side}_{row}_{section}',(x,y,h+.07),(2.1,.34,.07),SEATS[section]))
                result.append(box(f'seatback_{side}_{row}_{section}',(x,y+side*.33,h+.23),(2.1,.045,.16),SEATS[section]))
        for x in (-15.,-10.,-5.,0.,7.):
            result.append(connector(f'rail_post_{side}_{x}',(x,side*18.4,0),(x,side*18.4,3.1),.025,NAVY))
        for z in (2.65,3.1):
            result.append(connector(f'rail_{side}_{z}',(-15,side*18.4,z),(7,side*18.4,z),.025,CONCRETE))
        result.append(box(f'canopy_{side}',(-4,side*19.,4.8),(12.2,1.8,.1),NAVY))
        for x in (-14.,-4.,6.):
            result.append(connector(f'roof_support_{side}_{x}',(x,side*20.,0),(x,side*20.,4.8),.055,NAVY))
    for row in range(5):
        x=8.+1.1*row;h=.5*(row+1)
        result.append(box(f'rear_step_{row}',(x,0,h/2),(.55,12,h/2),CONCRETE))
        for section in range(5):
            y=-9.6+4.8*section
            result.append(box(f'rear_seat_{row}_{section}',(x,y,h+.07),(.34,2.1,.07),SEATS[section]))
            result.append(box(f'rear_seatback_{row}_{section}',(x+.33,y,h+.23),(.045,2.1,.16),SEATS[section]))
    result.append(box('rear_wall',(15.1,0,2.5),(.15,12.2,2.5),NAVY))
    result.append(box('rear_canopy',(13.9,0,5.0),(1.35,12.4,.1),NAVY))
    result.append(connector('rear_guardrail',(13.3,-12,3.15),(13.3,12,3.15),.025,CONCRETE))
    for y in (-12.,-6.,0.,6.,12.):
        result.append(connector(f'rear_roof_support_{y}',(15,y,0),(15,y,5),.06,CONCRETE))
    result.extend(crowd(lod))
    return result

def crowd(lod):
    rng=np.random.default_rng(7102)
    clothes=[(.11,.23,.39,1),(.72,.35,.17,1),(.18,.50,.55,1),(.62,.65,.65,1),(.25,.27,.29,1)]
    skin=[(.61,.42,.30,1),(.80,.63,.48,1),(.36,.25,.21,1)]
    positions=[]
    for row in range(0,5,2 if lod=='low' else 1):
        for y in np.linspace(-11.1,11.1,6 if lod=='low' else 12):
            positions.append((8.+row*1.1,float(y),.5*(row+1)))
    for side in (-1,1):
        for row in range(0,4,2 if lod=='low' else 1):
            for x in np.linspace(-14.5,6.5,6 if lod=='low' else 10):
                positions.append((float(x),side*(14.7+row*1.1),.5*(row+1)))
    result=[]
    for i,(x,y,h) in enumerate(positions):
        result.append(box(f'crowd_body_{i}',(x,y,h+.30),(.11,.12,.20),clothes[int(rng.integers(len(clothes)))]))
        result.append(Primitive(f'crowd_head_{i}','sphere',(x,y,h+.61),(.09,0,0),skin[int(rng.integers(len(skin)))]))
    return result

def goal_net(lod):
    result=[];back=6.1
    white=(.85,.91,.92,.48)
    for side in (-1,1):
        result.append(connector(f'goal_depth_top_{side}',(5,side*1.5,1.8),(back,side*1.5,1.8),.012,white))
        result.append(connector(f'goal_depth_floor_{side}',(5,side*1.5,.03),(back,side*1.5,.03),.012,white))
    ys=np.linspace(-1.5,1.5,11 if lod=='low' else 16)
    zs=np.linspace(.03,1.8,7 if lod=='low' else 10)
    xs=np.linspace(5.,back,4 if lod=='low' else 6)
    for i,y in enumerate(ys):
        result.append(connector(f'net_back_v_{i}',(back,y,.03),(back,y,1.8),.003,white))
        result.append(connector(f'net_roof_{i}',(5,y,1.8),(back,y,1.8),.003,white))
    for i,z in enumerate(zs):
        result.append(connector(f'net_back_h_{i}',(back,-1.5,z),(back,1.5,z),.003,white))
        for side in (-1,1):
            result.append(connector(f'net_side_h_{side}_{i}',(5,side*1.5,z),(back,side*1.5,z),.003,white))
    for i,x in enumerate(xs):
        for side in (-1,1):
            result.append(connector(f'net_side_v_{side}_{i}',(x,side*1.5,.03),(x,side*1.5,1.8),.003,white))
    return result
