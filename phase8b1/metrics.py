"""Post-episode evaluation only. Historical crossing times never enter agents."""
import json
import numpy as np

def summarize(folder,result,outcome,variant,action):
    telemetry=json.loads((folder/'planning.json').read_text(encoding='utf-8'))
    rows=telemetry['decision_rows'];ev=result['evaluation'];cross=ev['approach_crossing_measured']
    # If blocked before X=4, use first physical keeper contact as critical event.
    critical=cross['time_sim_s'] if cross else ev['first_keeper_ball']['time_sim_s']
    before=[r for r in rows if r['time_s']<=critical]
    t=np.array([r['time_s'] for r in rows]);q=np.array([r['actual_q_m'] for r in rows])
    v=np.array([r['actual_v_mps'] for r in rows]);commands=np.array([r['servo_command_m'] for r in rows])
    direction=-np.sign(cross['position_w'][1]) if cross else -np.sign(ev['first_keeper_ball']['ball_position_w'][1])
    useful=max(float(direction*r['actual_q_m']) for r in before)
    active=[r for r in before if r['state']=='TRACKING']
    velocities=[np.sign(r['actual_v_mps']) for r in active if abs(r['actual_v_mps'])>.02]
    reversals=sum(a!=b for a,b in zip(velocities,velocities[1:]))
    probe=telemetry['physical_probe'];surfaces=probe.get('surface_samples',[])
    goal=ev['goal_crossing_measured']
    pre_goal=[s for s in surfaces if goal is None or s['time_s']<=goal['time_sim_s']]
    last=min(rows,key=lambda r:abs(r['time_s']-critical))
    return dict(variant=variant,action=action,outcome=outcome,critical_time_s=critical,
        critical_definition='actual_X4_crossing' if cross else 'first_keeper_contact_before_plane',
        useful_q_m=useful,max_abs_q_m=max(abs(result['rail']['qmin_m']),abs(result['rail']['qmax_m'])),
        final_q_m=result['rail']['final_q_m'],peak_speed_mps=result['rail']['peak_speed_mps'],
        peak_acceleration_mps2=result['rail']['peak_acceleration_mps2'],peak_force_n=result['rail']['peak_force_n'],
        tracking_error_at_nearest_decision_m=last['tracking_error_m'],
        tactical_error_at_nearest_decision_m=last['bounded_tactical_target_m']-last['actual_q_m'],
        lateral_alignment_error_m=cross['center_alignment_error_m'] if cross else abs(ev['first_keeper_ball']['ball_position_w'][1]+ev['first_keeper_ball']['rail_q_m']),
        plane_surface_distance_m=probe.get('first_plane_sample',{}).get('distance_m'),
        min_surface_distance_sampled_m=min((s['distance_m'] for s in surfaces),default=None),
        min_surface_distance_sampled_before_goal_m=min((s['distance_m'] for s in pre_goal),default=None),
        surface_minimum_note='Global minimum may occur after goal/backstop; use pre-goal minimum for useful interception evaluation',
        contact=ev['first_keeper_ball'],agent=result['agent'],direction_reversals_before_critical=int(reversals),
        max_command_before_critical_m=max(abs(r['servo_command_m']) for r in before),
        passed=result['passed'],failures=result['failures'],warnings=result['engine_warnings'],
        shooter_fall_time_s=ev['shooter_fall_time_s'],keeper_max_tilt_deg=ev['keeper_max_tilt_deg'],rail=result['rail'])
