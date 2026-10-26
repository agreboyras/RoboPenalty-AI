"""Validated action mapping and explicitly historical calibration features."""
import hashlib
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
CATALOG={
    'original': {'center':('center',0.), 'left':('preset_left',.75), 'right':('preset_right',-.50)},
    'long': {'center':('long_center',0.), 'left':('long_preset_left',.75), 'right':('long_preset_right',-.50)},
}

def probe_path(distance,action):
    scenario=CATALOG[distance][action][0]
    folder='calibration_probes' if scenario in ('long_preset_left','long_preset_right') else 'exploration'
    return PROJECT/'phase4a/results'/folder/f'{scenario}_probe_01.json'

def load_calibration(distance):
    result={}
    for action,(scenario,bias) in CATALOG[distance].items():
        path=probe_path(distance,action)
        r=json.loads(path.read_text(encoding='utf-8'))
        e=r['evaluation']
        if r['scenario']!=scenario or not r['passed'] or not e['first_foot_ball'] or e['foot_peak_force_n']<=0:
            raise ValueError('Preset lacks a verified physical calibration')
        result[action]={'kind':'historical_calibration','distance':distance,
                        'plane_y_w_m':e['approach_crossing_measured']['position_w'][1],
                        'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result

def classify_after_episode(result,distance,action):
    # This outcome-bearing file is opened only AFTER simulation, outside the selector.
    import sys
    sys.path.insert(0,str(PROJECT/'phase4a'))
    from evaluation import classify
    probe=json.loads(probe_path(distance,action).read_text(encoding='utf-8'))
    if result['configuration'] != probe['configuration']:
        raise AssertionError('Physical execution and historical probe differ')
    if result['initial_state']['qpos'] != probe['initial_state']['qpos'] or result['initial_state']['qvel'] != probe['initial_state']['qvel']:
        raise AssertionError('Probe shot initial conditions differ')
    contact=result['evaluation']['first_keeper_ball']
    cutoff=contact['time_sim_s'] if contact else result['simulated_s']
    error=0.
    for actual,reference in zip(result['trace'],probe['trace']):
        if actual['observation']['time_s']>=cutoff: break
        for key in ('ball_position_w','ball_velocity_w'):
            error=max(error,max(abs(x-y) for x,y in zip(actual['observation'][key],reference['observation'][key])))
    if error>1e-8: raise AssertionError('Ball differs from calibration before keeper contact')
    label=classify(result,probe)
    label={'save_with_contact_and_goal_counterfactual':'save'}.get(label,label)
    return label,error
