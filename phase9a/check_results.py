"""Assertions over completed integration evidence, without rerunning physics."""
from bootstrap import *
import json

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    root=HERE/'results';rows=[]
    for name,manual,automatic,steps in [('directed_headless',5,0,35000),('directed_viewer',5,0,35000),('auto_headless',0,5,35000),
        ('mixed_headless_v2',2,1,21000),('mic_failure',1,0,7000),('stop_wait',0,0,0)]:
        run=load(root/name/'session.json');selection=load(root/name/'match_001/selection.json')
        assert run['failure'] is None and run['physics_steps']==steps,name
        assert len(selection['manual_history'])==manual,name
        assert len(selection['automatic_statistics']['history'])==automatic,name
        assert all(x['full_physics_unchanged'] for x in selection['waits']),name
        if name=='mic_failure':assert run['voice_worker_joined'] and any('error' in x for x in run['voice_metrics'])
        if name=='stop_wait':assert not run['matches'][0]['scoreboard']['history']
        for pause in run['control_pauses']:assert pause['full_integration_state_unchanged'],name
        if name=='directed_viewer':
            assert run['presentation']['viewer_closed'] and run['presentation']['viewer_render_thread_joined']
            assert selection['manual_history']==load(root/'directed_headless/match_001/selection.json')['manual_history']
        for n in range(1,manual+automatic+1):
            physical=load(root/name/f'match_001/penalty_{n:02d}/physical.json')
            assert physical['passed'] and not physical['failures'] and not any(physical['engine_warnings']),(name,n)
            assert physical['evaluation']['first_foot_ball'] is not None,(name,n)
            assert physical['evaluation']['shooter_fall_time_s'] is None,(name,n)
        assert run['runtime']['model_builds']==run['runtime']['policy_loads']==1
        rows.append(dict(run=name,physics_steps=steps,manual_records=manual,automatic_updates=automatic,passed=True,
            script_wall_s=run['script_wall_s']))
    (root/'integration_checks.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
