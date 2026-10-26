"""Versioned 8C actions; reuse the existing causal utility and post-episode scorer."""
import hashlib
import json
from pathlib import Path
from phase8b2.catalog import ShotCatalog as PreviousCatalog
from phase8b2.experiment import identifier
HERE=Path(__file__).resolve().parent

class Catalog(PreviousCatalog):
    def __init__(self,path):
        self.path=Path(path).resolve();self.id=hashlib.sha256(self.path.read_bytes()).hexdigest()
        raw=json.loads(self.path.read_text(encoding='utf-8'))
        if raw['version']!=1:raise ValueError('Unsupported catalog version')
        self.entries=raw['actions'];self.actions=tuple(self.entries)
        if 'center' not in self.actions:raise ValueError('Central reference action required')
        self.mapping={};self.calibration={}
        for action,entry in self.entries.items():
            path=(self.path.parent/entry['probe']).resolve()
            if not path.is_relative_to(HERE):raise ValueError('8C calibration must stay inside phase8c')
            payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=entry['sha256']:raise ValueError('Modified calibration')
            r=json.loads(payload);e=r['evaluation'];bias=float(entry['bias'])
            if not r['passed'] or not e['goal_detected'] or not e['first_foot_ball'] or e['foot_peak_force_n']<=0:
                raise ValueError('Invalid physical calibration')
            if r['phase8c']['initial_ball_delta_y_m']!=0. or r['configuration']!={'translate_x':-2.,'target_bias':bias}:
                raise ValueError('Nominal calibration geometry mismatch')
            if abs(e['goal_crossing_measured']['position_w'][1])+.115>=1.5:raise ValueError('Nominal sphere/post clearance')
            for condition in entry['grid']:
                trial=(self.path.parent/condition['source']).resolve()
                if not trial.is_relative_to(HERE) or hashlib.sha256(trial.read_bytes()).hexdigest()!=condition['sha256']:
                    raise ValueError('Robustness calibration changed')
            self.mapping[action]=(identifier(bias),bias)
            self.calibration[action]=dict(kind='historical_calibration',distance='long',
                plane_y_w_m=e['approach_crossing_measured']['position_w'][1],source=str(path),sha256=entry['sha256'])

def load_catalog(path):
    path=Path(path).resolve()
    return Catalog(path) if path.is_relative_to(HERE) else PreviousCatalog(path)
