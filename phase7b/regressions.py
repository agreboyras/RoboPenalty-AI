"""Run preserved tests in subprocesses, writing logs only inside phase7b."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(HERE) or out.exists():raise ValueError('New directory inside phase7b required')
    out.mkdir(parents=True)
    jobs=[('phase7b_unit',['-m','unittest','discover','-s',str(HERE/'tests'),'-v']),
          ('phase6a_unit',[str(PROJECT/'phase6a/test_presentation.py')]),
          ('phase6b_commands',[str(PROJECT/'phase6b/test_commands.py')]),
          ('phase5_and_earlier',[str(PROJECT/'phase5/validate.py'),'--output',str(out/'phase5_and_earlier')])]
    checks=[]
    for name,args in jobs:
        start=time.perf_counter()
        result=subprocess.run([sys.executable,'-B',*args],capture_output=True,text=True,encoding='utf-8')
        (out/f'{name}.stdout.txt').write_text(result.stdout,encoding='utf-8')
        (out/f'{name}.stderr.txt').write_text(result.stderr,encoding='utf-8')
        checks.append({'name':name,'exit_code':result.returncode,'wall_s':time.perf_counter()-start})
        (out/'report.json').write_text(json.dumps({'passed':all(c['exit_code']==0 for c in checks),
                                                 'checks':checks},indent=2),encoding='utf-8')
        print(json.dumps(checks[-1]),flush=True)
        if result.returncode:raise RuntimeError(result.stderr)

if __name__=='__main__':main()
