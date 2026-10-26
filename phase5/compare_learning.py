"""Five fresh phase-4B processes, carrying exactly the same striker learning."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from benchmark import compare_physics

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--match',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();root=Path(a.output).resolve();session=Path(a.match).resolve()
    if not root.is_relative_to(HERE.parent) or root.exists():raise ValueError('New output inside RoboPenalty required')
    root.mkdir(parents=True)
    match=json.loads((session/'match.json').read_text());config=match['config']
    assert config['striker']=='utility'
    rows=[];previous=None
    for n in range(1,config['penalties']+1):
        folder=root/f'penalty_{n:02d}'
        command=[sys.executable,'-B',str(HERE.parent/'phase4b/physical_episode.py'),
            '--strategy','utility','--opponent',config['keeper'],'--distance',config['distance'],
            '--seed',str(config['seed']),'--episode-id',f'penalty_{n:02d}','--output',str(folder)]
        if previous:command+=['--state',str(previous)]
        start=time.perf_counter();proc=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        wall=time.perf_counter()-start
        folder.mkdir(exist_ok=True)
        (folder/'process.stdout.txt').write_text(proc.stdout,encoding='utf-8')
        (folder/'process.stderr.txt').write_text(proc.stderr,encoding='utf-8')
        if proc.returncode:raise RuntimeError(proc.stderr)
        physical=json.loads((folder/'physical.json').read_text())
        expected=json.loads((session/f'penalty_{n:02d}/physical.json').read_text())
        compare_physics(expected,physical)
        own=json.loads((session/f'penalty_{n:02d}/decision_before_shot.json').read_text())
        decision=json.loads((folder/'decision_before_shot.json').read_text())
        assert all(json.dumps(v,sort_keys=True)==json.dumps(decision[k],sort_keys=True) for k,v in own['decision'].items())
        assert own['statistics_before']==decision['statistics_before']
        previous=folder/'state_after.json'
        state=json.loads(previous.read_text())
        expected_after=json.loads((session/f'penalty_{n:02d}/feedback_after_shot.json').read_text())['statistics_after']
        assert state==expected_after
        rows.append({'penalty':n,'action':decision['action'],'wall_process_s':wall,
            'physical_trace_and_metrics_identical':True,'decision_and_learning_identical':True})
        print(json.dumps(rows[-1]),flush=True)
    session_wall=json.loads((session.parent/'comparison.json').read_text())['session_process_wall_s']
    total=sum(r['wall_process_s'] for r in rows)
    result={'passed':True,'five_independent_learning_processes_wall_s':total,
        'single_session_wall_s':session_wall,'difference_s':total-session_wall,
        'rows':rows,'note':'Same two agents, decision history, action sequence, physics and feedback; five fresh processes carrying state_after between penalties.'}
    (root/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
