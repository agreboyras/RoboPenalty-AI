"""Production adapter reusing the approved prototype without changing it."""
from phase7d.prototype.revision import RevisedBowl,prepare_revision
from phase7d.prototype.stadium import BowlScene

class StadiumScene(RevisedBowl):
    def __init__(self,model,lod='medium'):
        self.screen_state=None;self.screen_updates=0;self.lod=lod
        if lod=='none':
            self.faces={};self.face_transforms={}
            BowlScene.__init__(self,model,False)
        else:
            super().__init__(model)
            if lod=='low':
                self.static=[p for p in self.static if '_step_' not in p.name]
                BowlScene.update_status(self,dict(zip(('goals','saves','penalty','total'),self.screen_state)))

    def update_status(self,status):
        state=tuple(int(status.get(k,v)) for k,v in [('goals',0),('saves',0),('penalty',0),('total',5)])
        changed=state!=self.screen_state
        self.screen_state=state
        BowlScene.update_status(self,status)
        if changed:self.screen_updates+=1
        return changed

prepare_model=prepare_revision
