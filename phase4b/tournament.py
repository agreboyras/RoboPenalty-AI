"""Serial physical episodes; independent cold-start history for each strategy/opponent."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def run(a):
    output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists(): raise ValueError('New output directory required inside RoboPenalty')
    output.mkdir(parents=True)
    ledger=[]
    groups=[(opponent,strategy,'center',a.episodes) for opponent in ('fixed','agent')
            for strategy in ('fixed','random','utility')]
    if a.reference_episodes:
        groups += [(opponent,'fixed','right',a.reference_episodes) for opponent in ('fixed','agent')]
    for opponent,strategy,fixed_action,count in groups:
        group=f'{opponent}_{strategy}_{fixed_action if strategy=="fixed" else "selector"}'
        previous=None
        for n in range(1,count+1):
            episode_id=f'{group}_{n:03d}'
            directory=output/episode_id
            command=[sys.executable,'-B',str(HERE/'physical_episode.py'),
                '--strategy',strategy,'--opponent',opponent,'--distance',a.distance,
                '--fixed-action',fixed_action,'--seed',str(a.seed),'--episode-id',episode_id,'--output',str(directory)]
            if previous: command += ['--state',str(previous)]
            started=time.perf_counter()
            process=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
            elapsed=time.perf_counter()-started
            directory.mkdir(exist_ok=True)
            (directory/'process.stdout.txt').write_text(process.stdout,encoding='utf-8')
            (directory/'process.stderr.txt').write_text(process.stderr,encoding='utf-8')
            if process.returncode:
                raise RuntimeError(f'{episode_id} failed: {process.stderr}')
            decision=json.loads((directory/'decision_before_shot.json').read_text(encoding='utf-8'))
            feedback=json.loads((directory/'feedback_after_shot.json').read_text(encoding='utf-8'))
            physical=json.loads((directory/'physical.json').read_text(encoding='utf-8'))
            row={'episode_id':episode_id,'group':group,'opponent':opponent,'strategy':strategy,
                 'fixed_action':fixed_action if strategy=='fixed' else None,'episode_number':n,
                 'action':decision['action'],'outcome':feedback['outcome'],
                 'reason':decision['reason'],'candidates':decision['candidates'],
                 'counts_after':feedback['update']['counts_after'],
                 'wall_process_s':elapsed,'simulated_s':physical['simulated_s'],
                 'initial_state_sha256':physical['initial_state_sha256'],
                 'directory':str(directory)}
            ledger.append(row)
            (output/'ledger.json').write_text(json.dumps(ledger,indent=2),encoding='utf-8')
            previous=directory/'state_after.json'
            print(json.dumps({k:row[k] for k in ('episode_id','action','outcome','reason','wall_process_s')}),flush=True)
    summary={}
    for name in sorted(set(x['group'] for x in ledger)):
        rows=[x for x in ledger if x['group']==name]
        wall=[x['wall_process_s'] for x in rows]
        summary[name]={'episodes':len(rows),'outcomes':dict(Counter(x['outcome'] for x in rows)),
            'actions':dict(Counter(x['action'] for x in rows)),
            'first_three':dict(Counter(x['outcome'] for x in rows[:3])),
            'after_first_three':dict(Counter(x['outcome'] for x in rows[3:])),
            'wall_mean_s':statistics.mean(wall),'wall_min_s':min(wall),'wall_max_s':max(wall)}
    if len(set(x['initial_state_sha256'] for x in ledger))!=1:
        raise AssertionError('Strategies did not share identical initial physical states')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--episodes',type=int,default=12)
    p.add_argument('--reference-episodes',type=int,default=3)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--distance',choices=['original','long'],default='long')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    if a.episodes<1 or a.reference_episodes<0: raise ValueError('Invalid episode counts')
    run(a)

if __name__=='__main__':main()
