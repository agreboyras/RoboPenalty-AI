"""Reproducible offline comparison and prediction/reachability metrics."""
import argparse
import json
from pathlib import Path
import statistics
from collections import Counter
from evaluation import classify, interpolate_q, min_center_travel_time

HERE = Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--directory',required=True,nargs='+')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    records=[]
    for name in a.directory:
        directory=Path(name)
        for record in json.loads((directory/'batch.json').read_text()):
            record['batch']=directory.name
            records.append(record)
    probes={}
    for folder in ('exploration','calibration_probes','miss_probe'):
        for path in (HERE/'results'/folder).glob('*_probe_01.json'):
            probe=json.loads(path.read_text())
            probes[probe['scenario']]=probe
    rows=[]
    for record in records:
        r=json.loads(Path(record['result_file']).read_text())
        e=r['evaluation']; probe=probes[r['scenario']]
        if r['configuration'] != probe['configuration'] or r['initial_state']['qpos'] != probe['initial_state']['qpos'] or r['initial_state']['qvel'] != probe['initial_state']['qvel']:
            raise AssertionError('Probe and trial shot initial conditions differ')
        first_contact=e['first_keeper_ball']
        cutoff=first_contact['time_sim_s'] if first_contact else r['simulated_s']
        # Once a save causes a different ball path, only the prefix is comparable.
        prefix_errors=[]
        for actual,free in zip(r['trace'],probe['trace']):
            if actual['observation']['time_s']>=cutoff: break
            for key in ('ball_position_w','ball_velocity_w'):
                prefix_errors.extend(abs(x-y) for x,y in zip(actual['observation'][key],free['observation'][key]))
        prefix_error=max(prefix_errors,default=0)
        if prefix_error>1e-8: raise AssertionError('Ball trajectory differs before keeper contact')
        baseline=probe['evaluation']['approach_crossing_measured']
        arrival=baseline['time_sim_s'] if baseline else None
        detect=r['agent']['detection_time_sim_s']
        first=r['agent']['first_prediction_estimated']
        trace=r['trace']
        tracking=next((x['decision'] for x in trace if x['decision'] and x['decision']['state']=='TRACKING'),None)
        valid_before=[x for x in trace if arrival and x['observation']['time_s']<arrival and x['prediction']['valid']]
        last_prediction=valid_before[-1] if valid_before else None
        row={'scenario':r['scenario'],'mode':r['mode'],'repeat':record['repeat'],'batch':record['batch'],
             'outcome':classify(r,probe),'foot_force_n':e['foot_peak_force_n'],
             'keeper_contact':e['first_keeper_ball'], 'goal':e['goal_detected'],
             'unobstructed_plane_y_m':baseline['position_w'][1] if baseline else None,
             'unobstructed_arrival_s':arrival,'measured_trial_crossing':e['approach_crossing_measured'],
             'detection_s':detect,'prediction_at_detection':first,
             'first_tracking_decision':tracking,
             'last_causal_prediction_before_unobstructed_arrival':last_prediction,
             'available_time_from_detection_s':arrival-detect if arrival and detect else None,
             'lateral_prediction_error_m':abs(first['y_w']-baseline['position_w'][1]) if first and baseline else None,
             'predicted_minus_actual_arrival_s':detect+first['eta_s']-arrival if first and arrival else None,
             'rail_q_at_unobstructed_arrival_interpolated_m':interpolate_q(trace,arrival) if arrival else None,
             'minimum_body_center_travel_time_estimate_s':min_center_travel_time(baseline['position_w'][1]) if baseline else None,
             'reaction_s':r['agent']['physical_reaction_after_detection_s'],
             'rail':r['rail'],'process_wall_s':record['wall_process_s'],'timing':r['timing'],
             'initial_state_sha256':r['initial_state_sha256'],
             'ball_state_prefix_error_vs_unobstructed_probe':prefix_error,
             'initial_low_ball_collision_aabb_envelope':r.get('initial_low_ball_collision_aabb_envelope'),
             'passed':r['passed'],'failures':r['failures']}
        rows.append(row)
    pairs=[]
    for scenario,repeat,batch in sorted(set((x['scenario'],x['repeat'],x['batch']) for x in rows)):
        pair=[x for x in rows if x['scenario']==scenario and x['repeat']==repeat and x['batch']==batch and x['mode'] in ('agent','fixed')]
        if len(pair)==2:
            equal=pair[0]['initial_state_sha256']==pair[1]['initial_state_sha256']
            if not equal: raise AssertionError('Mismatched strategy initial states')
            pairs.append({'scenario':scenario,'repeat':repeat,'batch':batch,'identical_initial_state':equal})
    summary={}
    for mode in sorted(set(x['mode'] for x in rows)):
        selected=[x for x in rows if x['mode']==mode]
        wall=[x['process_wall_s'] for x in selected]
        summary[mode]={'n':len(selected),'outcomes':dict(Counter(x['outcome'] for x in selected)),
                       'process_wall_mean_s':statistics.mean(wall),'process_wall_min_s':min(wall),
                       'process_wall_max_s':max(wall),'loop_wall_mean_s':statistics.mean(x['timing']['loop_wall_s'] for x in selected),
                       'all_passed':all(x['passed'] for x in selected)}
    output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists():
        raise ValueError('Output must be new inside RoboPenalty')
    output.write_text(json.dumps({'summary':summary,'paired_initial_conditions':pairs,'rows':rows},indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
