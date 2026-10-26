"""Read-only regressions; reports/logs stay in 7D (no 7B temp-file tests)."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out.exists() or not out.is_relative_to(HERE):raise ValueError('New phase7d report folder required')
    out.mkdir(parents=True)
    tests=[HERE/'test_integration.py',HERE/'prototype/test_prototype.py',HERE/'prototype/test_review.py',
           HERE.parent/'phase7c/tests/test_scene.py',HERE.parent/'phase7b/tests/test_visual.py',
           HERE.parent/'phase7b/tests/test_cameras.py',HERE.parent/'phase7b/tests/test_validation.py',
           HERE.parent/'phase6b/test_commands.py']
    report=[]
    for test in tests:
        start=time.perf_counter()
        run=subprocess.run([sys.executable,'-B',str(test)],capture_output=True,text=True,encoding='utf-8')
        text=run.stdout+'\n'+run.stderr
        log=out/f'{test.parent.name}_{test.name}.log';log.write_text(text,encoding='utf-8')
        count=re.search(r'Ran (\d+) tests?',text)
        report.append(dict(file=str(test),returncode=run.returncode,tests=int(count[1]) if count else None,
                           wall_s=time.perf_counter()-start,log=str(log)))
        (out/'tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(f'{test}: {run.returncode}',flush=True)
        if run.returncode:raise RuntimeError(f'Regression failed; see {log}')

if __name__=='__main__':main()
