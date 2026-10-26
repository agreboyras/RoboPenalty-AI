"""Run scoring tests and the preserved earlier-phase regressions serially."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(); p.add_argument('--directory',required=True); a=p.parse_args()
    out=Path(a.directory).resolve()
    if not out.is_relative_to(HERE.parent) or out.exists(): raise ValueError('New directory within RoboPenalty required')
    out.mkdir(parents=True)
    tests=[('scoring',[str(HERE/'test_evaluation.py')]),
           ('agent_synthetic',[str(HERE.parent/'phase3b/test_agent.py')]),
           ('phase2_block',[str(HERE.parent/'phase2/experiment.py'),'--case','block','--duration','14','--output',str(out/'phase2_block.json')]),
           ('phase3a_return',[str(HERE.parent/'phase3a/experiment.py'),'--case','return','--duration','14','--output',str(out/'phase3a_return.json')])]
    results=[]
    for name,arguments in tests:
        start=time.perf_counter()
        proc=subprocess.run([sys.executable,'-B',*arguments],capture_output=True,text=True,encoding='utf-8')
        (out/f'{name}.stdout.txt').write_text(proc.stdout,encoding='utf-8')
        (out/f'{name}.stderr.txt').write_text(proc.stderr,encoding='utf-8')
        result={'test':name,'exit_code':proc.returncode,'wall_s':time.perf_counter()-start}
        results.append(result)
        (out/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
        if proc.returncode: raise RuntimeError(f'{name} failed: {proc.stderr}')

if __name__=='__main__':main()
