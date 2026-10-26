"""Approved adapted dimensions in world metres; not regulation football."""
import math

X_MIN, X_GOAL = -15., 5.
HALF_WIDTH = 12.
PENALTY_FRONT, PENALTY_HALF_WIDTH = -4., 7.
SMALL_FRONT, SMALL_HALF_WIDTH = 2., 3.5
SPOT = (-1.,0.)
ARC_RADIUS = 3.5
LINE_WIDTH = .07

def arc_points(center, radius, begin, end, segments):
    return [(center[0]+radius*math.cos(begin+(end-begin)*i/segments),
             center[1]+radius*math.sin(begin+(end-begin)*i/segments))
            for i in range(segments+1)]

def penalty_arc():
    angle=math.acos((PENALTY_FRONT-SPOT[0])/ARC_RADIUS)
    return arc_points(SPOT,ARC_RADIUS,angle,2*math.pi-angle,20)

def center_semicircle():
    return arc_points((X_MIN,0),ARC_RADIUS,-math.pi/2,math.pi/2,40)

def marking_segments():
    lines=[('sideline_positive',(-15,12),(5,12)),
           ('sideline_negative',(-15,-12),(5,-12)),
           ('halfway',(-15,-12),(-15,12)),
           ('goal_line',(5,-12),(5,12))]
    for name,x,y in [('penalty',PENALTY_FRONT,PENALTY_HALF_WIDTH),
                     ('small',SMALL_FRONT,SMALL_HALF_WIDTH)]:
        lines += [(name+'_front',(x,-y),(x,y)),
                  (name+'_positive',(x,y),(5,y)),
                  (name+'_negative',(x,-y),(5,-y))]
    for name,points in [('penalty_arc',penalty_arc()),('center_semicircle',center_semicircle())]:
        lines.extend((f'{name}_{i:02d}',a,b) for i,(a,b) in enumerate(zip(points,points[1:])))
    return lines
