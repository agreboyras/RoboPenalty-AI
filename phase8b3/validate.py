from bootstrap import *
import hashlib
import json
from phase5.benchmark import compare_physics
from phase8b2.integrity import protected_sources

def main():
    root=HERE/'results'
    out=root/'validation.json'
    if out.exists():raise ValueError('Validation exists')
    left=root/'match_headless/match_001';right=root/'viewer_one/match_001'
    x,y=[json.loads((folder/'penalty_01/physical.json').read_text()) for folder in (left,right)]
    compare_physics(x,y)
    for key in ('phase8b2','agent','initial_state'):assert x[key]==y[key],key
    assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state']
    assert json.loads((left/'penalty_01/posture.json').read_text())==json.loads((right/'penalty_01/posture.json').read_text())
    match=json.loads((left/'match.json').read_text())
    for row in match['scoreboard']['history']:
        current=json.loads((left/f'penalty_{row["penalty"]:02d}/physical.json').read_text())
        isolated=json.loads((root/'shots_v1'/f'dynamic_{row["action"]}_01/physical.json').read_text())
        compare_physics(current,isolated)
        assert current['phase5_state']['final_integration_state']==isolated['phase5_state']['final_integration_state']
    for name in ('match_headless','viewer_one'):
        s=json.loads((root/name/'session.json').read_text())
        assert s['failure'] is None and not s['previous_sources_changed']
        assert s['presentation']['viewer_closed'] and s['presentation']['viewer_render_thread_joined']
        assert s['presentation']['stadium']['physical_model_unchanged']
        assert all(p['full_integration_state_unchanged'] for p in s['control_pauses'])
    before=json.loads((root/'protected_before.json').read_text())
    changed=[p for p,h in before.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    tests=json.loads((root/'regressions/tests.json').read_text());assert all(r['returncode']==0 for r in tests)
    result=dict(passed=True,historical_files_checked=len(before),changed=changed,tests_passed=sum(r['count'] or 0 for r in tests),
        comparison='Exact physical trace, contacts, agent decisions, 500Hz trajectory, full final state; wall clocks excluded',
        native_viewer_one_penalty_equal_headless=True,five_session_penalties_equal_independent_dynamic_shots=True,
        nominal_repetitions='20 physical shot episodes: both modes, five actions, two exact repeats per combination',
        robustness_scope='Body controller stable in tested ±0.01rad shoulder and ±5mm ball conditions; shot calibration/rail residual exceptions remain documented')
    out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
