"""Measured sweep tables and standalone SVG charts, no extra dependencies."""
from bootstrap import *
import argparse
import csv
import html
import json
from phase8b2.catalog import ShotCatalog

def svg(path,title,body,width=1000,height=650):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" fill="#152b3e"><text x="35" y="35" font-size="22">{html.escape(title)}</text>{body}</g></svg>',encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--catalog',type=Path,default=HERE/'catalog_v1.json');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);catalog=ShotCatalog(a.catalog)
    summaries=[]
    for folder in ('baseline','coarse','refine','positive_refine','selected_repeats'):
        summaries+=json.loads((HERE/'results'/folder/'summary.json').read_text(encoding='utf-8'))
    selected={round(v['bias'],4):k for k,v in catalog.entries.items()};flat=[]
    for s in summaries:
        c4=s['plane4'];c5=s['plane5'];release=s['release']
        flat.append(dict(bias=s['bias'],selected_action=selected.get(round(s['bias'],4),''),outcome=s['outcome'],
            passed=s['passed'],foot_force_n=s['foot_peak_n'],foot_time_s=s['contact']['time_sim_s'] if s['contact'] else None,
            release_time_s=release[0] if release else None,release_x=release[1] if release else None,
            release_y=release[2] if release else None,release_z=release[3] if release else None,
            release_vx=release[4] if release else None,release_vy=release[5] if release else None,
            release_vz=release[6] if release else None,release_angle_deg=s['release_angle_deg'],
            time4=c4['time_sim_s'] if c4 else None,y4=c4['position_w'][1] if c4 else None,z4=c4['position_w'][2] if c4 else None,
            time5=c5['time_sim_s'] if c5 else None,y5=c5['position_w'][1] if c5 else None,z5=c5['position_w'][2] if c5 else None,
            sphere_post_margin_m=s['sphere_post_margin_m'],low_corner=s['low_corner'],fall=s['fall'],
            max_tilt_deg=s['max_tilt_deg'],wall_s=s['wall_s'],source=s['source'],failures='; '.join(s['failures'])))
    with (a.output/'candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    (a.output/'candidates.json').write_text(json.dumps(flat,indent=2),encoding='utf-8')
    table=['| Bias | Y en X=4 | Y en X=5 | Margen esfera/poste | Resultado | Fuerza pie N | Caída |','|---:|---:|---:|---:|---|---:|---|']
    unique={s['bias']:s for s in summaries}
    def fmt(v):return '—' if v is None else f'{v:.4f}'
    for b,s in sorted(unique.items()):
        table.append(f"| {b:+.3f} | {fmt(s['plane4']['position_w'][1] if s['plane4'] else None)} | {fmt(s['plane5']['position_w'][1] if s['plane5'] else None)} | {fmt(s['sphere_post_margin_m'])} | {s['outcome']} | {s['foot_peak_n']:.2f} | {s['fall']} |")
    (a.output/'TABLA.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    # Front view, real measured goal-plane center coordinates.
    body='<rect x="90" y="120" width="800" height="390" fill="#e8f2e8" stroke="#555" stroke-width="4"/>'
    body+='<text x="90" y="550">Vista desde el delantero: +Y izquierda; postes nominales ±1.5 m; radio pelota 0.115 m</text>'
    for y in (-1.3,-1.1,1.1,1.3):
        x=490-y/1.5*400;body+=f'<line x1="{x}" y1="120" x2="{x}" y2="510" stroke="#bbb" stroke-dasharray="5 4"/>'
    for i,(action,entry) in enumerate(catalog.entries.items()):
        s=unique[entry['bias']];y,z=s['plane5']['position_w'][1:];x=490-y/1.5*400;yp=510-z/1.8*390
        color=['#555','#1978a4','#3a915a','#d33c31','#8857b3'][i]
        body+=f'<ellipse cx="{x:.2f}" cy="{yp:.2f}" rx="30.67" ry="24.92" fill="{color}" opacity=".6"/>'
        body+=f'<text x="100" y="{580+i*13}" font-size="12" fill="{color}">{action}: Y={y:+.4f}, Z={z:.4f} m</text>'
    svg(a.output/'goal_arrivals.svg','Llegadas medidas en X=5 (centros y radio nominal)',body,height=680)
    body='<rect x="80" y="80" width="830" height="470" fill="#eef4ef" stroke="#aaa"/>'
    for x in (-1,0,1,2,3,4,5):
        px=80+(x+1)/6*830;body+=f'<line x1="{px}" x2="{px}" y1="80" y2="550" stroke="#ccc"/><text x="{px}" y="575">{x}</text>'
    for i,(action,entry) in enumerate(catalog.entries.items()):
        r=json.loads(Path(catalog.calibration[action]['source']).read_text(encoding='utf-8'))
        rows=[row for row in r['phase8b2']['trajectory'] if row[0]<=r['evaluation']['goal_crossing_measured']['time_sim_s']]
        points=' '.join(f'{80+(row[1]+1)/6*830:.2f},{315-row[2]/1.6*220:.2f}' for row in rows[::5])
        color=['#555','#1978a4','#3a915a','#d33c31','#8857b3'][i]
        body+=f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/><text x="100" y="{595+i*13}" font-size="12" fill="{color}">{action}</text>'
    body+='<text x="800" y="610">X mundial (m)</text><text x="85" y="72">Y: + arriba, − abajo; banda ±1.6 m</text>'
    svg(a.output/'trajectories.svg','Trayectorias libres medidas hasta X=5',body,height=680)
    print(json.dumps(dict(trials=len(flat),unique_biases=len(unique),output=str(a.output))))
if __name__=='__main__':main()
