"""Second visual review; original stadium.py remains the comparison baseline."""
from dataclasses import replace
import numpy as np
from phase7d.prototype.stadium import BowlScene,prepare
from phase7b.visual_scene import connector

# Cubemap face order: +X,-X,+Y,-Y,+Z,-Z. Three dominant sector palettes,
# with white/red/dark neighbours rather than the same chessboard everywhere.
PALETTES=((.58,.21,.21),(.35,.43,.22),(.47,.23,.30),
          (.39,.35,.26),(.61,.17,.22),(.29,.46,.25))

def crowd_faces():
    faces=[]
    for face,weights in enumerate(PALETTES):
        rng=np.random.default_rng(7410+face)
        image=np.empty((512,512,3),dtype=np.uint8);image[:]=[47,44,43]
        # Irregular row spacing, offsets, body shapes, hair and clothing values.
        # Everything below writes pixels only: no meshes or spectator geometries.
        y=4
        while y<505:
            x=int(rng.integers(-7,8))
            while x<510:
                x+=int(rng.integers(9,15))
                cy=y+int(rng.integers(-2,3))
                if x>=507 or rng.random()<.045:continue
                # Smooth local neighbourhood preference prevents uniform confetti.
                patch=np.sin(x*.021+face)+np.cos(cy*.018-face*.7)
                p=np.array(weights)+np.array([.055,-.035,-.020])*patch
                group=int(rng.choice(3,p=p/p.sum()))
                base=np.array(([210,205,195],[144,24,32],[38,39,44])[group])
                color=np.clip(base+rng.integers(-26,27),0,255)
                half=int(rng.integers(3,6));height=int(rng.integers(7,12))
                yy=min(511,cy+height)
                image[max(0,cy):yy,max(0,x-half):min(512,x+half+1)]=color
                # Tiny uneven head/hair; crowd clothing remains the dominant cue.
                skin=np.array(([151,119,96],[191,157,125],[98,77,65])[int(rng.integers(3))])
                image[max(0,cy-3):max(0,cy),max(0,x-1):min(512,x+2)]=skin
                if rng.random()<.55:
                    image[max(0,cy-4):max(0,cy-2),max(0,x-1):min(512,x+2)]=[35,31,29]
            y+=int(rng.integers(12,17))
        # Small unstructured surface variation, without filters or external assets.
        image=np.clip(image.astype(np.int16)+rng.integers(-5,6,image.shape),0,255).astype(np.uint8)
        faces.append(image)
    return np.concatenate(faces,axis=0)

def prepare_revision(model):
    changes=prepare(model)
    pixels=crowd_faces();start=int(model.tex_adr[0])
    model.tex_data[start:start+pixels.size]=pixels.ravel()
    return changes+['six distinct irregular crowd cubemap faces; unchanged texture allocation']

def face_basis(face):
    # Columns are the new box axes in the original panel frame. Reassigning axes
    # and halfsizes leaves its occupied visual volume exactly unchanged.
    z=np.array([0.,0.,1.]);x=np.array([1.,0.,0.]);y=np.array([0.,1.,0.])
    matrices=(np.column_stack((z,y,-x)),np.column_stack((-z,y,x)),
              np.column_stack((x,z,-y)),np.column_stack((x,-z,y)),
              np.eye(3),np.column_stack((x,-y,-z)))
    return matrices[face]

class RevisedBowl(BowlScene):
    def __init__(self,model):
        super().__init__(model)
        self.faces={}
        # Sector variation is deterministic and independent of game RNG/history.
        for p in self.primitives:
            if p.name in self.crowd:
                _,sector,level=p.name.split('_');sector=int(sector);level=int(level)
                self.faces[p.name]=(sector//3+2*level+(sector%3==0))%6
        # Prepare axis permutations once, instead of allocating matrices per frame.
        self.face_transforms={}
        for p in self.primitives:
            if p.name in self.faces:
                b=face_basis(self.faces[p.name])
                original=np.asarray(self.rotations[p.name]).reshape(3,3)
                self.face_transforms[p.name]=(original@b,np.abs(b).T@np.array(p.size))
        supports=[]
        steel=(.34,.35,.37,1)
        for side in (-1,1):
            y=side*6.5
            supports.extend([
                connector(f'revision_screen_brace_{side}',(24.5,y,17.8),(27.8,y,20.5),.16,steel),
                connector(f'revision_screen_upper_brace_{side}',(30.5,y,19.5),(27.8,y,24.5),.11,steel),
                connector(f'revision_screen_base_{side}',(26.7,y,20.5),(29.5,y,20.5),.16,steel)])
        supports.extend([
            connector('revision_screen_lower_beam',(27.8,-6.7,20.5),(27.8,6.7,20.5),.17,steel),
            connector('revision_screen_diagonal',(28.,-6.5,20.5),(28.,6.5,24.4),.08,steel)])
        self.static+=supports
        self.static=[replace(p,color=(.33,.34,.36,1)) if p.name=='screen_frame' else p for p in self.static]
        self.update_status(dict(goals=0,saves=0,penalty=1,total=5))

    def populate(self,scene,*,replace=True):
        start=0 if replace else int(scene.ngeom)
        count=super().populate(scene,replace=replace)
        for i,p in enumerate(self.primitives,start):
            if p.name not in self.faces:continue
            g=scene.geoms[i];matrix,size=self.face_transforms[p.name]
            g.mat[:]=matrix;g.size[:]=size
            g.texrepeat[:]=[1,1]
        return count
