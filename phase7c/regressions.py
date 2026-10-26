"""Preserved unit contracts and real reset test, writing only into phase7c."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New output inside phase7c required')
    a.output.mkdir(parents=True)
    jobs=[('phase7c',['-m','unittest','discover','-s',str(HERE/'tests'),'-v']),
          ('phase7b',['-m','unittest','discover','-s',str(PROJECT/'phase7b/tests'),'-v'])]
    jobs.extend((name,[str(PROJECT/path)]) for name,path in
        [('keeper','phase3b/test_agent.py'),('evaluation','phase4a/test_evaluation.py'),
         ('striker','phase4b/test_striker.py'),('game','phase5/test_game.py'),
         ('real_reset','phase5/test_reset.py'),('presentation','phase6a/test_presentation.py'),
         ('commands','phase6b/test_commands.py')])
    rows=[]
    for name,args in jobs:
        start=time.perf_counter()
        proc=subprocess.run([sys.executable,'-B',*args],capture_output=True,text=True,encoding='utf-8')
        (a.output/f'{name}.stdout.txt').write_text(proc.stdout,encoding='utf-8')
        (a.output/f'{name}.stderr.txt').write_text(proc.stderr,encoding='utf-8')
        rows.append({'name':name,'exit_code':proc.returncode,'wall_s':time.perf_counter()-start})
        (a.output/'report.json').write_text(json.dumps({'passed':all(r['exit_code']==0 for r in rows),'checks':rows},indent=2),encoding='utf-8')
        print(json.dumps(rows[-1]),flush=True)
        if proc.returncode:raise RuntimeError(proc.stderr)

if __name__=='__main__':main()
