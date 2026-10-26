"""Stages for real native-viewer tests, physical equivalence and regressions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'phase5'))
from benchmark import compare_physics

def execute(arguments,folder):
    start=time.perf_counter()
    proc=subprocess.run([sys.executable,'-B',*arguments],capture_output=True,text=True,encoding='utf-8')
    wall=time.perf_counter()-start
    folder.mkdir(exist_ok=True)
    (folder/'process.stdout.txt').write_text(proc.stdout,encoding='utf-8')
    (folder/'process.stderr.txt').write_text(proc.stderr,encoding='utf-8')
    if proc.returncode:raise RuntimeError(f'{folder.name}: {proc.stderr}')
    return wall

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['diagnostic','comparison','regressions'],required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.output).resolve()
    if not root.is_relative_to(HERE.parent) or root.exists():raise ValueError('New directory inside RoboPenalty required')
    root.mkdir(parents=True)
    if a.stage=='diagnostic':
        folder=root/'viewer_one'
        wall=execute([str(HERE/'run_match.py'),'--viewer','--penalties','1','--capture-frame','--output',str(folder)],folder)
        report={'stage':a.stage,'passed':True,'process_wall_s':wall}
    elif a.stage=='comparison':
        headless,visual=root/'headless',root/'viewer'
        baseline_wall=execute([str(HERE/'run_match.py'),'--output',str(headless)],headless)
        print(f'Headless reference finished: {baseline_wall:.3f}s',flush=True)
        viewer_wall=execute([str(HERE/'run_match.py'),'--viewer','--output',str(visual)],visual)
        h=json.loads((headless/'match.json').read_text());v=json.loads((visual/'match.json').read_text())
        assert h['striker_statistics']==v['striker_statistics']
        rows=[]
        for n in range(1,6):
            hp=json.loads((headless/f'penalty_{n:02d}/physical.json').read_text())
            vp=json.loads((visual/f'penalty_{n:02d}/physical.json').read_text())
            compare_physics(hp,vp)
            assert hp['phase5_state']['final_integration_state']==vp['phase5_state']['final_integration_state']
            assert hp['phase5_state']['final_integration_sha256']==vp['phase5_state']['final_integration_sha256']
            hd=json.loads((headless/f'penalty_{n:02d}/decision_before_shot.json').read_text())
            vd=json.loads((visual/f'penalty_{n:02d}/decision_before_shot.json').read_text());assert hd==vd
            rows.append({'penalty':n,'action':v['scoreboard']['history'][n-1]['action'],
                'outcome':v['scoreboard']['history'][n-1]['outcome'],'exact_physical_equivalence':True,
                'headless_loop_wall_s':hp['timing']['loop_wall_s'],'visual_loop_wall_s':vp['timing']['loop_wall_s']})
        presentation=json.loads((visual/'presentation.json').read_text())
        assert presentation['viewer_closed'] and presentation['same_world_passed_to_viewer']
        assert all(p['physics_unchanged'] for p in presentation['pause_records'])
        assert presentation['mj_step_calls']==35000
        assert all(e['viewer_running'] for e in presentation['events'])
        report={'stage':a.stage,'passed':True,'headless_process_wall_s':baseline_wall,
            'viewer_process_wall_s':viewer_wall,'same_decisions_and_learning':True,
            'same_contacts_results_and_full_state':True,'rows':rows,'presentation':presentation}
    else:
        checks=[]
        for name,args in [('presentation_unit',[str(HERE/'test_presentation.py')]),
            ('phase5_and_earlier',[str(HERE.parent/'phase5/validate.py'),'--output',str(root/'phase5_and_earlier')])]:
            folder=root/name
            if name=='phase5_and_earlier':
                # Validation creates its own root; process logs go separately.
                log=root/f'{name}_logs'
            else:log=folder
            wall=execute(args,log);checks.append({'name':name,'wall_s':wall,'passed':True})
            print(json.dumps(checks[-1]),flush=True)
        report={'stage':a.stage,'passed':True,'checks':checks}
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('presentation','rows')},indent=2))

if __name__=='__main__':main()
