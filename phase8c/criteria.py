"""Declared engineering screen, not a statistical/global robustness guarantee."""
MAX_LATERAL_RANGE=.30
MIN_SPHERE_POST_MARGIN=.05
def assess(rows):
    complete=set(r.get('delta_y_m') for r in rows)=={-.005,-.002,-.001,0.,.001,.002,.005}
    crossings=[r['plane5'] for r in rows]
    valid=all(r['passed'] and r['foot_peak_n']>0 and r['fall'] is None and r['outcome']=='goal' for r in rows)
    ys=[c['position_w'][1] for c in crossings if c]
    span=max(ys)-min(ys) if len(ys)==len(rows) and ys else None
    direction=bool(ys and (all(y>.20 for y in ys) or all(y<-.20 for y in ys) or all(abs(y)<.20 for y in ys)))
    margins=[r['sphere_post_margin_m'] for r in rows if r['sphere_post_margin_m'] is not None]
    clearance=len(margins)==len(rows) and min(margins)>=MIN_SPHERE_POST_MARGIN
    physical=bool(complete and valid and clearance and span is not None and span<=MAX_LATERAL_RANGE)
    return dict(conditions=len(rows),complete_seven_point_grid=complete,valid_contact_stable_goal_all=valid,lateral_range_m=span,
        direction_consistent=direction,min_sphere_post_margin_m=min(margins) if margins else None,
        passes_engineering_screen=bool(physical and direction),
        passes_physical_consistency_screen=physical,
        positive_y_all=bool(ys and len(ys)==len(rows) and min(ys)>0),
        corner_all=bool(valid and ys and all(1.1<=abs(y)<=1.3 for y in ys)),
        scope='Only enumerated initial-Y perturbations; thresholds declared before new sweep; not a confidence bound')
