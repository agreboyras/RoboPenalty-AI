"""Serial tests, configuration checks and unchanged previous-phase regressions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).resolve()
    if not out.is_relative_to(HERE.parent) or out.exists():raise ValueError('New output inside RoboPenalty required')
    out.mkdir(parents=True)
    jobs=[('game_unit',[str(HERE/'test_game.py')]),('reset_real_state',[str(HERE/'test_reset.py')]),
          ('original_five',[str(HERE/'run_match.py'),'--distance','original','--output',str(out/'original_five')]),
          ('fixed_keeper_random',[str(HERE/'run_match.py'),'--keeper','fixed','--striker','random','--output',str(out/'fixed_keeper_random')]),
          ('fixed_striker_two',[str(HERE/'run_match.py'),'--penalties','2','--striker','fixed','--fixed-action','center','--output',str(out/'fixed_striker_two')]),
          ('previous_regressions',[str(HERE.parent/'phase4b/regressions.py'),'--output',str(out/'previous_regressions')])]
    checks=[]
    for name,arguments in jobs:
        start=time.perf_counter()
        result=subprocess.run([sys.executable,'-B',*arguments],capture_output=True,text=True,encoding='utf-8')
        wall=time.perf_counter()-start
        (out/f'{name}.stdout.txt').write_text(result.stdout,encoding='utf-8')
        (out/f'{name}.stderr.txt').write_text(result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError(f'{name}: {result.stderr}')
        # The old exploratory batch allows nonfatal trial failures: inspect its
        # actual results too, including the previously demonstrated advantage.
        if name=='previous_regressions':
            folder=out/'previous_regressions/phase4a_long_left'
            for mode in ('fixed','agent'):
                r=json.loads((folder/f'long_preset_left_{mode}_01.json').read_text())
                assert r['passed'] and r['evaluation']['goal_detected']==(mode=='fixed')
                if mode=='agent':assert r['evaluation']['first_keeper_ball'] is not None
        if name in ('original_five','fixed_keeper_random','fixed_striker_two'):
            m=json.loads((out/name/'match.json').read_text())
            assert m['phase']=='FINISHED'
            assert len(m['scoreboard']['history'])==m['config']['penalties']
            assert m['runtime']['model_builds']==m['runtime']['policy_loads']==1
        checks.append({'name':name,'exit_code':result.returncode,'wall_s':wall})
        (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        print(json.dumps(checks[-1]),flush=True)

if __name__=='__main__':main()
