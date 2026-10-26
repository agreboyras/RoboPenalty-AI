from bootstrap import *
import json
import re
import subprocess

def main():
    output=HERE/'results/regressions'
    output.mkdir(exist_ok=False);rows=[]
    paths=['phase8c/test_controls.py','phase8b3/test_posture.py','phase8b2/test_configuration.py',
        'phase8b2/test_learning.py','phase8b1/test_planners.py','phase3b/test_agent.py','phase4a/test_evaluation.py',
        'phase4b/test_striker.py','phase7d/test_integration.py','phase7c/tests/test_scene.py',
        'phase7d/prototype/test_prototype.py','phase7d/prototype/test_review.py','phase6b/test_commands.py']
    for i,path in enumerate(paths):
        r=subprocess.run([sys.executable,'-B',str(PROJECT/path)],capture_output=True,text=True,encoding='utf-8')
        log=r.stdout+'\n'+r.stderr;(output/f'{i:02d}.log').write_text(log,encoding='utf-8')
        count=re.search(r'Ran (\d+) tests?',log)
        rows.append(dict(path=path,returncode=r.returncode,count=int(count[1]) if count else None))
        (output/'tests.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        if r.returncode:raise RuntimeError(log)
    print('Historical tests passed:',sum(r['count'] or 0 for r in rows))
if __name__=='__main__':main()
