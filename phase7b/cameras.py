"""Camera presets and a strict /cam namespace; no game-command grammar edits."""
import queue
from commands import CommandBus

VIEWS=('execution','overview','goal','follow')

def specification(name, ball=None):
    if name=='overview':return {'lookat':[-4.,-1.,.8],'distance':52.,'azimuth':-90.,'elevation':-65.}
    if name=='goal':return {'lookat':[3.,0.,.65],'distance':6.5,'azimuth':150.,'elevation':-18.}
    if name=='follow':
        p=ball if ball is not None else (-1.,0.,.115)
        return {'lookat':[float(p[0]),float(p[1]),max(.65,float(p[2]))],
                'distance':10.5,'azimuth':-60.,'elevation':-26.}
    if name=='execution':return {'lookat':[1.5,0.,.65],'distance':10.5,'azimuth':-60.,'elevation':-22.}
    raise ValueError('Unknown camera: '+name)

class ViewCommandBus(CommandBus):
    def __init__(self,*args,camera_requests,**kwargs):
        super().__init__(*args,**kwargs);self.camera_requests=camera_requests
    def submit(self,text,source='text',generation=None,kind='command',capture_id=None):
        words=text.strip().lower().split()
        if source in ('text','script-text') and kind=='command' and len(words)==2 and words[0]=='/cam' and words[1] in VIEWS:
            with self.lock:
                epoch=self.generation if generation is None else generation
                if epoch!=self.generation:self.dropped+=1;return False
                try:self.camera_requests.put_nowait((epoch,words[1]))
                except queue.Full:self.dropped+=1;return False
            return True
        return super().submit(text,source,generation,kind,capture_id)
