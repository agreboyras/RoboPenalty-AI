from bootstrap import *
import argparse
import json
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True)
    shots=json.loads((HERE/'results/shots_v1/summary.json').read_text())
    lines=['| Tiro | Postura | Resultado | q al cruce m | Distancia mínima antes de gol m | Vel. articular máx rad/s | Error PD máx rad |','|---|---|---|---:|---:|---:|---:|']
    for row in shots:
        if row['repeat']!=1:continue
        b=row['posture']
        lines.append(f"| {row['action']} | {row['variant']} | {row['outcome']} | {row['actual_q_at_critical_m']:.6f} | {row['minimum_surface_before_goal_sampled_m']:.6f} | {b['max_joint_speed_rad_s']:.6f} | {b['max_tracking_error_rad']:.6f} |")
    (a.output/'comparacion.md').write_text('\n'.join(lines),encoding='utf-8')
    # Measured joint reference/position, not visual animation curves.
    pieces=[]
    for n,action in enumerate(('intermediate_left_b110','intermediate_right_m080','center')):
        b=json.loads((HERE/'results/shots_v1'/f'dynamic_{action}_01/posture.json').read_text())
        names=b['names'];rows=b['rows'];idx=names.index('right_shoulder_roll_joint' if n==0 else 'left_shoulder_roll_joint' if n==1 else 'left_elbow_joint')
        y0=70+n*230
        pieces.append(f'<text x="50" y="{y0}" font-size="17">{action}: {names[idx]}</text><rect x="60" y="{y0+15}" width="900" height="160" fill="#f4f6fa" stroke="#aaa"/>')
        for key,color in [('reference_rad','#c33'),('actual_rad','#146ca4')]:
            points=' '.join(f'{60+r["time_s"]/14*900:.1f},{y0+95-r[key][idx]*70:.1f}' for r in rows)
            pieces.append(f'<polyline points="{points}" stroke="{color}" fill="none" stroke-width="2"/>')
        pieces.append(f'<text x="60" y="{y0+195}">0 s</text><text x="900" y="{y0+195}">14 s</text>')
        for value in (-1,0,1):pieces.append(f'<text x="25" y="{y0+95-value*70}">{value}</text>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1020" height="810"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#18334b"><text x="40" y="30" font-size="20">Posturas reales: referencia roja / posición azul (radianes)</text>'+''.join(pieces)+'</g></svg>'
    (a.output/'articulaciones.svg').write_text(svg,encoding='utf-8')
    rob=json.loads((HERE/'results/ball_perturbations/summary.json').read_text())
    lines=['| ΔY inicial m | Tiro | Postura | Resultado físico | Y X=5 libre m | Validación completa |','|---:|---|---|---|---:|---|']
    for r in rob:
        y=r['free_goal_crossing']['position_w'][1] if r['free_goal_crossing'] else None
        lines.append(f"| {r['delta_y_m']:+.3f} | {r['action']} | {r['mode']} | {r['outcome']} | {f'{y:+.6f}' if y is not None else 'sin cruce'} | {r['physical_passed']} |")
    (a.output/'robustez.md').write_text('\n'.join(lines),encoding='utf-8')
    derived=[]
    for path in (HERE/'results/shots_v1').glob('*/posture.json'):
        b=json.loads(path.read_text());rows=b['rows'];names=b['names']
        waiting=next((r for r in reversed(rows) if r['time_s']<4),None)
        recovery=[r for r in rows if r['state']=='RECOVERY']
        settled=next((r['time_s']-recovery[0]['time_s'] for r in recovery if waiting and np.max(np.abs(np.array(r['reference_rad'])-waiting['reference_rad']))<.01),None)
        derived.append(dict(source=str(path),return_reference_within_001rad_s=settled,
            reference_speed_measured=max(abs(v) for r in rows for v in r['reference_velocity_rad_s']),
            actual_joint_torque_sampled_peak_nm=max(abs(v) for r in rows for v in r['actual_joint_torque_nm']),
            final_reference_rad=rows[-1]['reference_rad'],final_actual_rad=rows[-1]['actual_rad']))
    (a.output/'derived.json').write_text(json.dumps(derived,indent=2),encoding='utf-8')
    print('Tables, measured joint plot and recovery metrics written')
if __name__=='__main__':main()
