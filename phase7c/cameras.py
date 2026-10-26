"""Behind-striker default, preserving all 7B alternative views."""
import queue
from phase7b.cameras import specification as previous_specification, ViewCommandBus

VIEWS=('behind','execution','overview','goal','follow')

def specification(name,ball=None):
    if name=='behind':return {'lookat':[1.8,0.,1.6],'distance':11.,'azimuth':15.,'elevation':-15.}
    if name=='overview':return {'lookat':[-2.,-1.,1.],'distance':62.,'azimuth':-90.,'elevation':-65.}
    return previous_specification(name,ball)

class CameraBus(ViewCommandBus):
    def submit(self,text,source='text',generation=None,kind='command',capture_id=None):
        if source in ('text','script-text') and kind=='command' and text.strip().lower()=='/cam behind':
            with self.lock:
                epoch=self.generation if generation is None else generation
                if epoch!=self.generation:self.dropped+=1;return False
                try:self.camera_requests.put_nowait((epoch,'behind'))
                except queue.Full:self.dropped+=1;return False
                return True
        return super().submit(text,source,generation,kind,capture_id)
