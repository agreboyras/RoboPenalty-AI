from phase7c.cameras import CameraBus,VIEWS,specification as previous

def specification(name,ball=None):
    if name=='behind':return dict(lookat=[2.7,0,2.8],distance=11.8,azimuth=15.,elevation=5.)
    if name=='overview':return dict(lookat=[-4,0,7],distance=78.,azimuth=15.,elevation=-43.)
    return previous(name,ball)
