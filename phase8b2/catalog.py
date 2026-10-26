"""Versioned calibration catalog. Outcomes are opened only after each episode."""
import hashlib
import json
from pathlib import Path
from phase8b2.experiment import identifier

class ShotCatalog:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.id=hashlib.sha256(self.path.read_bytes()).hexdigest()
        raw=json.loads(self.path.read_text(encoding='utf-8'))
        if raw['version']!=1:raise ValueError('Unsupported catalog')
        self.entries=raw['actions'];self.actions=tuple(self.entries)
        if 'center' not in self.actions or len(self.actions)!=len(set(self.actions)):raise ValueError('Invalid action set')
        self.mapping={};self.calibration={}
        for action,entry in self.entries.items():
            source=(self.path.parent/entry['probe']).resolve()
            if not source.is_relative_to(Path(__file__).resolve().parent):raise ValueError('Local calibration required')
            contents=source.read_bytes()
            if hashlib.sha256(contents).hexdigest()!=entry['sha256']:raise ValueError('Calibration checksum mismatch')
            r=json.loads(contents);e=r['evaluation'];bias=float(entry['bias'])
            if not r['passed'] or not e['first_foot_ball'] or e['foot_peak_force_n']<=0 or not e['goal_detected']:
                raise ValueError('Only stable verified goal-producing probes can enter this catalog')
            arrival=e['goal_crossing_measured']['position_w']
            if abs(arrival[1])+.115>=1.5 or arrival[2]+.115>=1.8:
                raise ValueError('Candidate violates nominal sphere/post or crossbar clearance')
            if r['configuration']!={'translate_x':-2.,'target_bias':bias}:raise ValueError('Initial configuration mismatch')
            self.mapping[action]=(identifier(bias),bias)
            self.calibration[action]={'kind':'historical_calibration','distance':'long',
                'plane_y_w_m':e['approach_crossing_measured']['position_w'][1],
                'source':str(source),'sha256':entry['sha256']}

    def evaluate(self,result,distance,action):
        from evaluation import classify
        probe=json.loads(Path(self.calibration[action]['source']).read_text(encoding='utf-8'))
        if distance!='long' or result['configuration']!=probe['configuration']:raise AssertionError('Scenario mismatch')
        for key in ('qpos','qvel'):
            if result['initial_state'][key]!=probe['initial_state'][key]:raise AssertionError('Initial state mismatch')
        contact=result['evaluation']['first_keeper_ball']
        cutoff=contact['time_sim_s'] if contact else result['simulated_s'];error=0.
        if len(result['trace'])!=len(probe['trace']):raise AssertionError('Different episode length')
        for actual,reference in zip(result['trace'],probe['trace']):
            if actual['observation']['time_s']>=cutoff:break
            for key in ('ball_position_w','ball_velocity_w'):
                error=max(error,max(abs(x-y) for x,y in zip(actual['observation'][key],reference['observation'][key])))
        if error>1e-8:raise AssertionError('Ball deviates before keeper contact (existing 4B tolerance)')
        label={'save_with_contact_and_goal_counterfactual':'save'}.get(classify(result,probe),classify(result,probe))
        if label not in ('goal','save','miss'):raise RuntimeError(f'Unresolved result {label}')
        return label,error
