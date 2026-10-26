"""Offline scoring. These results are never made available to the agent."""
import math


def classify(trial, probe):
    e, baseline = trial['evaluation'], probe['evaluation']
    if not e['first_foot_ball'] or e.get('foot_peak_force_n', 0) <= 0:
        return 'invalid_no_verified_kick'
    if e['goal_detected']:
        return 'goal'
    if not baseline['goal_detected']:
        return 'miss' if baseline['goal_crossing_measured'] else 'unresolved_short_or_stopped'
    if e['first_keeper_ball'] and e['keeper_peak_contact_force_n'] > 0:
        return 'save_with_contact_and_goal_counterfactual'
    return 'unresolved_no_goal_no_verified_save'


def interpolate_q(trace, when):
    for a,b in zip(trace,trace[1:]):
        oa, ob = a['observation'], b['observation']
        if oa['time_s'] <= when <= ob['time_s']:
            alpha=(when-oa['time_s'])/(ob['time_s']-oa['time_s'])
            return oa['keeper_q'] + alpha*(ob['keeper_q']-oa['keeper_q'])
    return None


def min_center_travel_time(distance, vmax=0.3, acceleration=0.5):
    """Optimistic rest-to-arrival time, without braking, servo lag or contact."""
    distance=abs(distance)
    ramp_distance=vmax*vmax/(2*acceleration)
    return math.sqrt(2*distance/acceleration) if distance<=ramp_distance else vmax/acceleration+(distance-ramp_distance)/vmax
