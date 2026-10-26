from bootstrap import *
import json
import numpy as np
from phase8c.selection import resolve_source

def main():
    folder=HERE/'results/policy_diagnostic'
    rows=json.loads((folder/'summary.json').read_text());nominal=next(r for r in rows if r['delta_y_m']==0)
    base=json.loads(resolve_source(nominal['source']).read_text());reports=[]
    for row in rows:
        trial=json.loads(resolve_source(row['source']).read_text());samples=trial['phase8c']['policy_rows'];reference=base['phase8c']['policy_rows']
        cut=min(trial['evaluation']['first_foot_ball']['time_sim_s'],base['evaluation']['first_foot_ball']['time_sim_s'])-.02
        errors=[max(abs(x-y) for x,y in zip(a['joint_target_rad'],b['joint_target_rad'])) for a,b in zip(samples,reference) if a['time_s']<cut]
        qerrors=[max(abs(x-y) for x,y in zip(a['actual_joints_rad'],b['actual_joints_rad'])) for a,b in zip(samples,reference) if a['time_s']<cut]
        contacts=trial['phase8b2']['positive_foot_contacts']
        reports.append(dict(delta_y_mm=row['delta_y_m']*1000,cutoff_before_first_contact_s=cut,
            maximum_precontact_policy_target_difference_rad=max(errors,default=None),maximum_precontact_actual_joint_difference_rad=max(qerrors,default=None),
            first_positive_contact=contacts[0] if contacts else None,release=row['release'],release_angle_deg=row['release_angle_deg'],
            goal_crossing=row['plane5'],sphere_post_margin_m=row['sphere_post_margin_m']))
    out=HERE/'results/policy_diagnosis.json'
    if out.exists():raise ValueError('Report exists')
    out.write_text(json.dumps(dict(rows=reports,conclusion='Precontact policy targets and joint motions vary, then contact geometry/impulses differ. This establishes coupled policy/contact sensitivity, not a quantified causal allocation. Missing crossing/reversal are not classifier-only effects.'),indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
