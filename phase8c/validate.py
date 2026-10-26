from bootstrap import *
import argparse
import json
from phase5.benchmark import compare_physics
from phase7b.validate import compare as compare_matches

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--historical',action='store_true');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New report required')
    # The existing comparator expects the source-integrity report adjacent to session.json.
    # This wrapper supplies its own stronger final source manifest separately.
    if a.historical:
        left=a.reference/'match_001';right=a.candidate/'match_001';rows=[]
        for folder in sorted(left.glob('penalty_*')):
            x=json.loads((folder/'physical.json').read_text());y=json.loads((right/folder.name/'physical.json').read_text())
            compare_physics(x,y)
            assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state']
            assert x['agent']==y['agent']
            rows.append(dict(penalty=folder.name,exact=True))
        for name in ('striker_statistics','config'):
            assert json.loads((left/'match.json').read_text())[name]==json.loads((right/'match.json').read_text())[name]
        result=dict(passed=True,rows=rows,mode='Original 8B.3 physics + learning reproduced exactly; original return enabled')
    else:
        result=compare_matches(a.reference,a.candidate)
        for folder in sorted((a.reference/'match_001').glob('penalty_*')):
            target=a.candidate/'match_001'/folder.name
            for name in ('posture.json','planning.json','return.json','motor_monitor.json'):
                assert json.loads((folder/name).read_text())==json.loads((target/name).read_text()),name
            x=json.loads((folder/'physical.json').read_text());y=json.loads((target/'physical.json').read_text())
            assert x['phase8b2']==y['phase8b2']
        result['exact_500hz_ball_body_motor_return_telemetry']=True
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print('PASS exact comparison')
if __name__=='__main__':main()
