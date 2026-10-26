from bootstrap import *
import argparse
import json
import re
import subprocess

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);report=[]
    paths=[HERE/'test_posture.py',PROJECT/'phase8b2/test_configuration.py',PROJECT/'phase8b2/test_learning.py',
        PROJECT/'phase8b1/test_planners.py',PROJECT/'phase3b/test_agent.py',PROJECT/'phase4a/test_evaluation.py',
        PROJECT/'phase4b/test_striker.py',PROJECT/'phase7d/test_integration.py',PROJECT/'phase7c/tests/test_scene.py',
        PROJECT/'phase7d/prototype/test_prototype.py',PROJECT/'phase7d/prototype/test_review.py',PROJECT/'phase6b/test_commands.py']
    for i,path in enumerate(paths):
        r=subprocess.run([sys.executable,'-B',str(path)],capture_output=True,text=True,encoding='utf-8')
        log=r.stdout+'\n'+r.stderr;(a.output/f'{i:02d}_{path.name}.log').write_text(log,encoding='utf-8')
        count=re.search(r'Ran (\d+) tests?',log)
        report.append(dict(path=str(path),returncode=r.returncode,count=int(count[1]) if count else None))
        (a.output/'tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(path.name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(log)
if __name__=='__main__':main()
