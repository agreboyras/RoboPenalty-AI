"""Fingerprints of model arrays and protected source files; no physics edits."""
import hashlib
import json
from pathlib import Path
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
# The only compiled-model arrays the visual adapter may change.
VISUAL_ARRAYS = frozenset({'geom_rgba', 'geom_matid'})

def model_signature(model):
    arrays = {}
    for name in dir(model):
        value = getattr(model, name)
        if isinstance(value, np.ndarray) and name not in VISUAL_ARRAYS:
            arrays[name] = hashlib.sha256(value.tobytes()).hexdigest()
    opt = {name: (value.tolist() if hasattr(value, 'tolist') else value)
           for name in dir(model.opt) if not name.startswith('_')
           and not callable(value := getattr(model.opt, name))}
    return {'arrays': arrays, 'options': opt,
            'counts': {name: int(getattr(model, name)) for name in
                       ('nq','nv','nu','nbody','njnt','ngeom','ncam','nlight')}}

def protected_sources():
    paths = []
    for folder in PROJECT.glob('phase*'):
        if folder.name == 'phase7b' or not folder.is_dir(): continue
        paths.extend(p for p in folder.rglob('*') if p.is_file()
                     and not {'results','models','__pycache__'}.intersection(p.relative_to(folder).parts)
                     and p.suffix in ('.py','.xml','.yaml','.json','.md'))
    external = PROJECT.parent
    for folder in (external/'RoboNaldo_Deploy/g1_description',
                   external/'RoboNaldo_Deploy/policy/robonaldo',
                   external/'unitree_mujoco/unitree_robots/g1'):
        paths.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding='utf-8')
