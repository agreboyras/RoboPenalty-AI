"""Record synthetic tests, fixed/agent pairs and unchanged earlier regressions."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pairs',type=int,default=3)
    p.add_argument('--results')
    args=p.parse_args()
    home=Path(__file__).resolve().parent
    out=Path(args.results).resolve() if args.results else home/'results'/datetime.datetime.now().strftime('benchmark_%Y%m%d_%H%M%S')
    if not out.is_relative_to(home.parents[0]) or args.pairs<1:
        raise ValueError('Invalid output or pair count')
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYGAME_HIDE_SUPPORT_PROMPT='1')
    test=subprocess.run([sys.executable,'-B',str(home/'test_agent.py')],cwd=out,env=env,capture_output=True,text=True,encoding='utf-8')
    (out/'synthetic_tests.txt').write_text(test.stdout+test.stderr,encoding='utf-8')
    if test.returncode:
        raise RuntimeError('Synthetic tests failed; see log')
    processes=[]
    rows=[]
    jobs=[(mode,n) for n in range(1,args.pairs+1) for mode in ['fixed','agent']]
    jobs += [('phase3a_center',1),('phase3a_return',1),('phase3a_moving_contact',1),('phase2_block',1)]
    for mode,n in jobs:
        result=out/f'{mode}_{n:02d}.json'
        if mode.startswith('phase3a_'):
            command=[sys.executable,'-B',str(home.parents[0]/'phase3a/experiment.py'),'--case',mode.removeprefix('phase3a_'),'--output',str(result)]
        elif mode=='phase2_block':
            command=[sys.executable,'-B',str(home.parents[0]/'phase2/experiment.py'),'--case','block','--output',str(result)]
        else:
            command=[sys.executable,'-B',str(home/'experiment.py'),'--mode',mode,'--output',str(result)]
        start=time.perf_counter()
        proc=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        elapsed=time.perf_counter()-start
        result.with_suffix('.stdout.txt').write_text(proc.stdout,encoding='utf-8')
        result.with_suffix('.stderr.txt').write_text(proc.stderr,encoding='utf-8')
        record={'mode':mode,'repeat':n,'process_wall_s':elapsed,'exit_code':proc.returncode,'file':str(result),'command':command}
        processes.append(record)
        (out/'processes.json').write_text(json.dumps(processes,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
        if proc.returncode:
            raise RuntimeError(f'Failed {mode}: see diagnostic')
        r=json.loads(result.read_text(encoding='utf-8'))
        if mode in ['fixed','agent']:
            a,e=r['agent'],r['evaluation']
            first_target=next((x['selected_target_m'] for x in a['decision_events'] if x['command_changed'] and x['state']=='TRACKING'),None)
            rows.append({'mode':mode,'repeat':n,'process_wall_s':elapsed,'loop_wall_s':r['timing']['loop_wall_s'],
                         'outcome':e['outcome'],'shot_detection_sim_s':a['detection_time_sim_s'],
                         'predicted_y_w_m':a['first_prediction_estimated']['y_w'] if a['first_prediction_estimated'] else None,
                         'first_target_q_m':first_target,'physical_reaction_s':a['physical_reaction_after_detection_s'],
                         'actual_q_at_plane_m':e['approach_crossing_measured']['rail_q_m'] if e['approach_crossing_measured'] else None,
                         'center_alignment_error_m':e['approach_crossing_measured']['center_alignment_error_m'] if e['approach_crossing_measured'] else None,
                         'prediction_lateral_error_m':e['prediction_lateral_error_vs_measured_crossing_m'],
                         'arrival_estimate_error_s':e['predicted_minus_actual_arrival_time_s'],
                         'keeper_contact':e['first_keeper_ball'] is not None,'goal':e['goal_detected'],
                         'final_q_m':r['rail']['final_q_m'],'passed':r['passed']})
    summary={}
    for mode in ['fixed','agent']:
        rs=[r for r in rows if r['mode']==mode]
        summary[mode]={'count':len(rs),'mean_process_s':statistics.mean(r['process_wall_s'] for r in rs),
                       'min_process_s':min(r['process_wall_s'] for r in rs),'max_process_s':max(r['process_wall_s'] for r in rs),
                       'mean_loop_s':statistics.mean(r['loop_wall_s'] for r in rs),
                       'goals':sum(r['goal'] for r in rs),'saves_observed':sum(r['outcome']=='save_observed' for r in rs),
                       'misses':sum(r['outcome']=='miss' for r in rs),'all_passed':all(r['passed'] for r in rs)}
    (out/'summary.json').write_text(json.dumps({'groups':summary,'runs':rows,'regressions':processes[-4:]},indent=2),encoding='utf-8')
    with (out/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    print(json.dumps({'directory':str(out),'groups':summary},indent=2),flush=True)


if __name__=='__main__':
    main()
