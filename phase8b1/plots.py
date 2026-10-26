"""Standalone scientific SVG plots, standard library only (no installations)."""
import argparse
import html
import json
from pathlib import Path

COLORS=['#555555','#d55e00','#0072b2','#009e73']
def plot(root,out,xmin=3.8,xmax=5.8):
    out.mkdir(parents=True,exist_ok=False)
    for action in ('left','center','right'):
        svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1000" viewBox="0 0 1200 1000">',
             '<rect width="1200" height="1000" fill="white"/>',
             f'<text x="55" y="28" font-family="sans-serif" font-size="21">Preset {action}: objetivos y desplazamiento (q positivo hacia -Y)</text>']
        for panel,variant in enumerate(('A','B','C')):
            rows=json.loads((root/f'{variant}_{action}_01/planning.json').read_text(encoding='utf-8'))['decision_rows']
            x0,y0,w,h=80,65+panel*300,1070,225
            ymin,ymax=-.7,.7
            X=lambda t:x0+(t-xmin)/(xmax-xmin)*w
            Y=lambda q:y0+h-(q-ymin)/(ymax-ymin)*h
            svg.append(f'<text x="80" y="{y0-10}" font-family="sans-serif" font-size="16">Planificador {variant}</text>')
            for q in (-.65,-.3,0,.3,.65):
                yy=Y(q);svg.append(f'<path d="M{x0},{yy}H{x0+w}" stroke="#ddd"/><text x="25" y="{yy+5}" font-family="sans-serif" font-size="13">{q:+.2f}</text>')
            ticks=[xmin+i*(xmax-xmin)/7 for i in range(8)] if xmax-xmin>4 else [xmin+i*(xmax-xmin)/5 for i in range(6)]
            for t in ticks:
                xx=X(t);svg.append(f'<path d="M{xx},{y0}V{y0+h}" stroke="#eee"/><text x="{xx-12}" y="{y0+h+20}" font-family="sans-serif" font-size="13">{t:.1f}</text>')
            series=[('bounded_tactical_target_m','objetivo activo'),('servo_command_m','consigna servo'),
                    ('actual_q_m','posición real'),('reference_q_m','referencia interna')]
            for n,(key,label) in enumerate(series):
                points=' '.join(f'{X(r["time_s"]):.2f},{Y(0. if key=="bounded_tactical_target_m" and r["state"]!="TRACKING" else r[key]):.2f}' for r in rows if xmin<=r['time_s']<=xmax)
                svg.append(f'<polyline points="{points}" fill="none" stroke="{COLORS[n]}" stroke-width="2"/>')
                xx=80+n*265
                svg.append(f'<text x="{xx}" y="{y0+h+43}" font-family="sans-serif" font-size="14" fill="{COLORS[n]}">{html.escape(label)}</text>')
            svg.append(f'<text x="1100" y="{y0+h+43}" font-family="sans-serif" font-size="13">t [s]</text>')
            svg.append(f'<text x="8" y="{y0-8}" font-family="sans-serif" font-size="13">q [m]</text>')
        svg.append('</svg>');(out/f'{action}.svg').write_text('\n'.join(svg),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--start',type=float,default=3.8);p.add_argument('--end',type=float,default=5.8);a=p.parse_args()
    here=Path(__file__).resolve().parent
    if not a.output.resolve().is_relative_to(here):raise ValueError('phase8b1 output required')
    if not a.end>a.start:raise ValueError('end must exceed start')
    plot(a.input,a.output,a.start,a.end)
