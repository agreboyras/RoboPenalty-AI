"""Measured sensitivity CSV/SVG and per-bias engineering screen."""
from bootstrap import *
import argparse
import csv
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from phase8c.criteria import assess

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);allrows=[];groups=defaultdict(list)
    goal_xml=ET.parse(PROJECT.parent/'RoboNaldo_Deploy/g1_description/scene_with_ball.xml')
    post_radius=float(goal_xml.find('.//geom[@name="goal_left_post"]').get('size').split()[0])
    assert post_radius==float(goal_xml.find('.//geom[@name="goal_right_post"]').get('size').split()[0])
    for folder in a.inputs:
        for r in json.loads((folder/'summary.json').read_text()):allrows.append(r);groups[r['bias']].append(r)
    assessments={}
    for bias,rows in groups.items():
        unique={r['delta_y_m']:r for r in rows}
        assessments[str(bias)]={**assess(list(unique.values())),'tested_deltas_mm':sorted(d*1000 for d in unique)}
    (a.output/'assessments.json').write_text(json.dumps(assessments,indent=2),encoding='utf-8')
    flat=[]
    for r in allrows:
        p5=r['plane5'];release=r['release'];contact=r['first_positive_contact']
        flat.append(dict(bias=r['bias'],dy_mm=r['delta_y_m']*1000,repeat=r['repeat'],passed=r['passed'],outcome=r['outcome'],
            contact_time_s=contact['time_s'] if contact else None,contact_position=contact['contact_position_w'] if contact else None,
            foot_force_n=r['foot_peak_n'],release_position=release[1:4] if release else None,
            release_velocity=release[4:7] if release else None,release_angle_deg=r['release_angle_deg'],
            arrival_time_s=p5['time_sim_s'] if p5 else None,y5=p5['position_w'][1] if p5 else None,z5=p5['position_w'][2] if p5 else None,
            sphere_post_margin_m=r['sphere_post_margin_m'],
            post_surface_clearance_at_X5_m=r['sphere_post_margin_m']-post_radius if r['sphere_post_margin_m'] is not None else None,
            visual_post_radius_m=post_radius,fall=r['fall'],source=r['source']))
    with (a.output/'trials.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    lines=['| Bias | ΔY mm | Y en X=5 m | Resultado | Fuerza pie N | Margen esfera/poste m |','|---:|---:|---:|---|---:|---:|']
    for bias,rows in sorted(groups.items()):
        for delta,r in sorted({r['delta_y_m']:r for r in rows}.items()):
            y=r['plane5']['position_w'][1] if r['plane5'] else None;gap=r['sphere_post_margin_m']
            lines.append(f"| {bias:+.3f} | {delta*1000:+.0f} | {f'{y:+.6f}' if y is not None else 'sin cruce'} | {r['outcome']} | {r['foot_peak_n']:.2f} | {f'{gap:.6f}' if gap is not None else '—'} |")
    (a.output/'TABLA.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#20354a"><text x="45" y="30" font-size="22">Sensibilidad física: desplazamiento inicial Y vs llegada a X=5</text>']
    colors=['#222','#c33','#16a','#198754','#a15bb5','#bd7626','#5085aa','#dd66aa','#3e8562','#86572a','#777']
    for v in (-1.5,-1.,-.5,0,.5,1.,1.5):
        y=380-v*175;svg.append(f'<line x1="90" x2="850" y1="{y}" y2="{y}" stroke="#ddd"/><text x="25" y="{y+5}">{v:+.1f} m</text>')
    for d in (-5,-2,-1,0,1,2,5):
        x=470+d*70;svg.append(f'<line x1="{x}" x2="{x}" y1="90" y2="670" stroke="#eee"/><text x="{x-10}" y="700">{d:+} mm</text>')
    for i,(bias,rows) in enumerate(sorted(groups.items())):
        color=colors[i%len(colors)];unique=sorted({r['delta_y_m']:r for r in rows}.items());points=[]
        for delta,r in unique:
            if r['plane5']:
                x=470+delta*1000*70;y=380-r['plane5']['position_w'][1]*175
                points.append(f'{x},{y}');svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="1.7"/><text x="900" y="{95+i*32}" fill="{color}">bias {bias:+.3f}</text>')
    svg.append('<text x="60" y="740">Líneas unen muestras, no interpolan calibraciones válidas. Un tiro sin cruce no tiene punto Y.</text></g></svg>')
    (a.output/'sensitivity.svg').write_text(''.join(svg),encoding='utf-8')
    print(json.dumps(assessments,indent=2))
if __name__=='__main__':main()
