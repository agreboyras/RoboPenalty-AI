"""Run new behavioral tests and preserved physical/synthetic regressions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    out=Path(a.output).resolve()
    if not out.is_relative_to(HERE.parent) or out.exists(): raise ValueError('New output inside RoboPenalty required')
    out.mkdir(parents=True)
    jobs=[('striker',[str(HERE/'test_striker.py')]),
          ('previous_checks',[str(HERE.parent/'phase4a/verify.py'),'--directory',str(out/'previous_checks')]),
          ('phase4a_long_left',[str(HERE.parent/'phase4a/batch.py'),'--scenarios','long_preset_left',
             '--modes','fixed','agent','--directory',str(out/'phase4a_long_left')])]
    checks=[]
    for name,arguments in jobs:
        start=time.perf_counter()
        proc=subprocess.run([sys.executable,'-B',*arguments],capture_output=True,text=True,encoding='utf-8')
        (out/f'{name}.stdout.txt').write_text(proc.stdout,encoding='utf-8')
        (out/f'{name}.stderr.txt').write_text(proc.stderr,encoding='utf-8')
        checks.append({'name':name,'exit_code':proc.returncode,'wall_s':time.perf_counter()-start})
        (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        print(json.dumps(checks[-1]),flush=True)
        if proc.returncode: raise RuntimeError(proc.stderr)

if __name__=='__main__':main()
