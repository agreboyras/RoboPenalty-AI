"""Serial, timed comparison: one five-penalty process vs five fresh processes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def command_run(command,directory):
    start=time.perf_counter()
    p=subprocess.run([sys.executable,'-B',*command],capture_output=True,text=True,encoding='utf-8')
    elapsed=time.perf_counter()-start
    directory.mkdir(exist_ok=True)
    (directory/'process.stdout.txt').write_text(p.stdout,encoding='utf-8')
    (directory/'process.stderr.txt').write_text(p.stderr,encoding='utf-8')
    if p.returncode: raise RuntimeError(p.stderr)
    return elapsed

def compare_physics(a,b):
    # Timer metadata and process IDs intentionally differ; physical data must not.
    for key in ('initial_state_sha256','evaluation','rail','trace','configuration'):
        if a[key]!=b[key]: raise AssertionError(f'Physical divergence in {key}')

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    root=Path(a.output).resolve()
    if not root.is_relative_to(HERE.parent) or root.exists(): raise ValueError('New directory inside RoboPenalty required')
    root.mkdir(parents=True)
    common=['--penalties','5','--seed','2026','--keeper','agent','--striker','utility','--distance','long']
    session=root/'session'
    session_wall=command_run([str(HERE/'run_match.py'),*common,'--output',str(session)],session)
    match=json.loads((session/'match.json').read_text())
    print(f'Five-penalty session complete: {session_wall:.3f} s',flush=True)
    references=[]
    for record in match['scoreboard']['history']:
        n=record['penalty']; path=root/f'independent_{n:02d}'
        wall=command_run([str(HERE/'reference_episode.py'),'--action',record['action'],
                          '--output',str(path)],path)
        original=json.loads((path/'physical.json').read_text())
        reused=json.loads((session/f'penalty_{n:02d}/physical.json').read_text())
        ref=json.loads((path/'reference.json').read_text())
        compare_physics(reused,original)
        assert ref['final_integration_state']==reused['phase5_state']['final_integration_state']
        assert ref['final_integration_sha256']==reused['phase5_state']['final_integration_sha256']
        assert ref['outcome']==record['outcome']
        references.append({'penalty':n,'action':record['action'],'outcome':ref['outcome'],
            'wall_process_s':wall,'full_final_integration_state_identical':True,
            'physical_trace_and_metrics_identical':True})
        print(json.dumps(references[-1]),flush=True)
    replay=root/'replay'
    replay_wall=command_run([str(HERE/'run_match.py'),*common,'--output',str(replay)],replay)
    replay_match=json.loads((replay/'match.json').read_text())
    assert match['striker_statistics']==replay_match['striker_statistics']
    for n in range(1,6):
        left=json.loads((session/f'penalty_{n:02d}/physical.json').read_text())
        right=json.loads((replay/f'penalty_{n:02d}/physical.json').read_text())
        compare_physics(left,right)
        assert left['phase5_state']['final_integration_state']==right['phase5_state']['final_integration_state']
    ids=[json.loads((session/f'penalty_{n:02d}/physical.json').read_text())['phase5_state'] for n in range(1,6)]
    for key in ('model_object_id','data_object_id','onnx_session_object_id'):
        assert len(set(v[key] for v in ids))==1
    independent=sum(x['wall_process_s'] for x in references)
    result={'passed':True,'session_process_wall_s':session_wall,'replay_process_wall_s':replay_wall,
        'five_independent_processes_wall_s':independent,'difference_s':independent-session_wall,
        'five_process_over_session_ratio':independent/session_wall,
        'note':'One serial timing pair, plus seed replay. Reference actions are frozen from the completed match only for offline physics equivalence; no live agent sees future results.',
        'scoreboard':match['scoreboard'],'model_builds_per_session':match['runtime']['model_builds'],
        'policy_loads_per_session':match['runtime']['policy_loads'],'references':references,
        'same_seed_reproduced':True,'same_model_data_session_ids':True}
    (root/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('scoreboard','references')},indent=2))

if __name__=='__main__':main()
