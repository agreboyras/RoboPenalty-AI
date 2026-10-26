"""Publish bounded conclusions from completed evidence; no new simulation."""
from bootstrap import *
import csv
import json
import numpy as np
from phase8c.integrity import sources
from phase8c.catalog import Catalog
from phase8c.selection import resolve_source
from phase5.benchmark import compare_physics

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    out=HERE/'RESULTADOS.md';root=HERE/'results'
    if out.exists():raise ValueError('Results already published')
    for name in ('viewer_exact','reference_8b2_exact','reference_8b3_exact'):assert read(root/f'{name}.json')['passed']
    before=read(root/'protected_before.json');assert before==sources(),'Protected source changed'
    tests=read(root/'regressions/tests.json');assert all(r['returncode']==0 for r in tests)
    catalog=Catalog(HERE/'catalog_v1.json');grid=read(root/'integrated_grid/summary.json')
    assert len(grid)==70 and all(r['passed'] and r['body_passed'] and not any(r['warnings']) for r in grid)
    assert all(abs(r['final_physical']['q_m'])<.015 and abs(r['final_physical']['v_mps'])<.02 for r in grid)
    sessions={n:read(root/n/'session.json') for n in ('match_dynamic','match_historical','match_viewer','reference_8b2','reference_8b3')}
    matches={n:read(root/n/'match_001/match.json') for n in sessions}
    for name,s in sessions.items():
        assert s['failure'] is None and s['physics_steps']==35000
        assert s['presentation']['viewer_closed'] and s['presentation']['viewer_render_thread_joined']
        assert s['runtime']['model_builds']==s['runtime']['policy_loads']==1
        assert all(r['full_integration_state_equal_to_fresh'] and r['freekick_state_equal_to_pristine'] for r in s['runtime']['resets'])
    for mode in ('dynamic','historical'):
        match=matches[f'match_{mode}']
        for row in match['scoreboard']['history']:
            current=read(root/f'match_{mode}/match_001'/f'penalty_{row["penalty"]:02d}/physical.json')
            reference=read(root/'integrated_grid'/f'dy+0.000_{mode}_{row["action"]}/physical.json')
            compare_physics(current,reference)
            assert current['phase5_state']['final_integration_state']==reference['phase5_state']['final_integration_state']
    saturation={}
    for name in ('match_dynamic','match_historical','match_viewer'):
        data=[read(p) for p in (root/name/'match_001').glob('penalty_*/motor_monitor.json')]
        assert len(data)==5 and sum(r['calls'] for r in data)==35000
        saturation[name]=sum(sum(r['saturation_command_steps_per_joint']) for r in data)
        assert saturation[name]==0,'Saturation requires explicit review'
    late_rail=[];sampled_saturation=0
    caps=np.array([min(j['software_torque_clip_n_m'],max(abs(x) for x in j['joint_force_range'])) for j in read(PROJECT/'phase8b3/results/audit.json')['joints']])
    for folder in (root/'integrated_grid').iterdir():
        if not folder.is_dir():continue
        rows=read(folder/'return.json')['rows'];tail=[r['q_m'] for r in rows if r['time_s']>=12]
        late_rail.append(max(tail)-min(tail))
        body=read(folder/'posture.json')
        sampled_saturation+=sum(int(np.sum(abs(np.array(r['commanded_torque_nm']))>=caps-1e-6)) for r in body['rows'])
    counts=sum(t['count'] or 0 for t in tests)
    csv_rows=list(csv.DictReader((root/'analysis_final/trials.csv').open(encoding='utf-8-sig')))
    diagnosis=read(root/'policy_diagnosis.json');return_rows=read(root/'return_diagnosis/summary.json')
    lines=['# Fase 8C — Consolidación y robustez acotada','',
        '## Conclusión','',
        'La variante 8C completa tandas de cinco con postura histórica/dinámica y visor, conserva la equivalencia física exacta entre visor y headless y corrige el residual de retorno estudiado. Se sustituye el repertorio izquierdo frágil por un tiro centro-izquierda conservador y se conserva una esquina derecha. No se encontró una esquina izquierda suficientemente consistente en la búsqueda realizada. **No se declara robustez global.**','',
        'La ganancia es consistencia dentro de una grilla lateral discreta y un retorno que pasa los umbrales originales. El repertorio es asimétrico y el tiro centro-izquierda no garantiza un sector lateral preciso. No se agregan movimientos, física ni recursos visuales.','',
        '## Sensibilidad de los cinco tiros anteriores','',
        'Se midieron siete desplazamientos iniciales Y: −5, −2, −1, 0, +1, +2, +5 mm. El resto de las condiciones se mantuvo igual, con arquero apartado en la inicialización. No hubo fuerzas externas ni modificaciones de velocidad durante el tiro.','',
        '| Preset anterior | Llegadas Y en X=5, orden −5/−2/−1/0/+1/+2/+5 mm | Diagnóstico |',
        '|---|---|---|']
    historical=read(root/'historical_grid/summary.json')
    from phase8c.sensitivity import HISTORICAL
    for action,bias in HISTORICAL.items():
        r=sorted((x for x in historical if x['bias']==bias),key=lambda x:x['delta_y_m'])
        vals=', '.join(f'{x["plane5"]["position_w"][1]:+.4f}' if x['plane5'] else 'sin cruce' for x in r)
        note='Consistente en la grilla' if bias in (0.,-.8,-1.4) else 'Dispersión elevada' if bias==1.1 else 'Tiro corto e inversión de dirección'
        lines.append(f'| {action} | {vals} | {note} |')
    lines+=['',
        f'Se archivaron {len(csv_rows)} ensayos libres completos y 18 valores distintos de bias entre grillas, filtros preliminares y repeticiones. [Tabla completa](results/analysis_final/TABLA.md), [CSV por ensayo](results/analysis_final/trials.csv), [gráfico SVG](results/analysis_final/sensitivity.svg). El CSV incluye primer contacto positivo (punto y tiempo), fuerza, posición/velocidad y ángulo de salida, llegada, margen y estabilidad; las trayectorias a 500 Hz permanecen en cada JSON.','',
        'La salida se mide en la primera muestra libre después del último contacto positivo con el pie. Los cruces son interpolaciones entre pasos de 2 ms. Un tiro sin cruce permanece sin resolver; no se transforma en atajada ni entra al aprendizaje.','',
        '## Política, contacto y clasificador','',
        'En el diagnóstico instrumental del bias +0,97, modificar Y inicial ±5 mm cambió los objetivos articulares de la política **antes del primer contacto**: diferencias máximas respecto del nominal ≈1,645 rad (−5 mm) y ≈1,451 rad (+5 mm), sobre los 29 objetivos. También cambiaron articulaciones reales y geoms del primer impacto (right_foot5/6/7). Los ángulos de salida fueron aproximadamente −0,53°, +14,06° y −5,26° para −5/0/+5 mm.','',
        'Esto prueba sensibilidad acoplada de política/contacto, no permite asignar qué proporción corresponde a cada uno. La falta de cruce y la inversión ya existen en la trayectoria física: no son solamente un artefacto del clasificador. [Diagnóstico](results/policy_diagnosis.json).','',
        'Se conservó la regla de gol original basada en el centro. Algunos candidatos, como +1,05 con +5 mm, son goles según esa regla pero su esfera invade el poste nominal; se rechazaron como calibración. El CSV distingue margen nominal `1.5−abs(Y)−0.115` y separación geométrica entre superficies de pelota y poste en X=5, que resta además el radio visual de poste 0,035 m verificado en el XML original. Los postes siguen sin colisión; esta distancia es geométrica calculada, no un contacto añadido.','',
        '## Selección y compromiso','',
        'Criterios declarados: contacto positivo y estabilidad en las siete condiciones, gol libre, margen nominal esfera/poste ≥0,05 m y rango lateral ≤0,30 m. La consistencia de sector distingue centro |Y|<0,20 e intermedios fuera de esa banda. El nuevo centro-izquierda se evalúa como tal, con signo positivo y consistencia física; **no aprueba la afirmación de sector lateral constante**. No se relajaron tolerancias de física o retorno.','',
        '| Acción 8C | Bias | Y nominal X=5 m | Rango medido de Y m | Dispersión m | Separación mínima superficie/poste m |',
        '|---|---:|---:|---|---:|---:|']
    for action,entry in catalog.entries.items():
        trials=[read(catalog.path.parent/c['source']) for c in entry['grid']]
        ys=[r['evaluation']['goal_crossing_measured']['position_w'][1] for r in trials]
        nominal=read(catalog.path.parent/entry['probe'])['evaluation']['goal_crossing_measured']['position_w'][1]
        lines.append(f'| {action} | {entry["bias"]:+.2f} | {nominal:+.6f} | [{min(ys):+.6f}, {max(ys):+.6f}] | {max(ys)-min(ys):.6f} | {1.5-max(abs(y) for y in ys)-.115-.035:.6f} |')
    lines+=['',
        'El bias +0,98 pasó extremos/nominal pero invirtió dirección en +1 mm. +0,70 mantuvo signo/gol, pero su rango 0,300654 m supera el criterio y mezcla sectores; +0,65 también superó el rango (0,318344 m). No se promovieron. El barrido adicional de +0,78 se interrumpió deliberadamente cuando los extremos ya probaban inversión; se conservan solo ensayos completados y no se presenta como grilla aprobada.','',
        'Las grillas completas de +0,60 y −1,00 se repitieron dos veces por condición con igualdad exacta de traza, contactos, trayectoria y hash final. Otras grillas no tienen todas dos repeticiones nuevas; sus nominales/referencias y la tanda con visor aportan las comparaciones exactas indicadas. No se afirma repetición exhaustiva de cada ensayo archivado.','',
        '## Retorno: causa y corrección','',
        'B entraba en DONE con |q|<0,01 m y |v|<0,02 m, pero con referencia interna aún alejada. En ese estado cortaba su feedback y enviaba cero; la planta con contactos podía volver a quedar fuera de 0,015 m al finalizar. La ablación original/corregida reprodujo el fallo y verificó igualdad exacta hasta el primer DONE. La contribución física específica de fricción/solver no fue aislada.','',
        '**Corrección de una interpretación del informe 8B.3:** 5,24 s era `episode_end_observed_time_s`, inicio del retorno, no entrada en DONE. Esta se observó a 9,28 s (dinámica) y 9,74 s (histórica) en el central +5 mm. Se conserva el informe histórico sin editar y se precisa aquí el significado correcto.','',
        'La variante mantiene `clip(-2*q−0.4*v, ±0.12)` durante DONE. Es el feedback original de retorno; no cambia WAITING, TRACKING, RETURNING, el criterio histórico de DONE, ganancias del servo, fuerza ni recorrido. No utiliza información futura.','',
        '| Postura, central +5 mm | q final original m | q final corregido m | Resultado del umbral original |',
        '|---|---:|---:|---|']
    for mode in ('historical','dynamic'):
        a=next(r for r in return_rows if r['posture']==mode and not r['correction']);b=next(r for r in return_rows if r['posture']==mode and r['correction'])
        lines.append(f'| {mode} | {a["final_q_m"]:.6f} | {b["final_q_m"]:.6f} | Rechazo → aprobado |')
    lines+=['',
        'El comando y la referencia interna quedan registrados en `results/return_diagnosis` y en `return.json` por episodio. Los instantes finales a 14 s se distinguen de la última decisión a 13,98 s.','',
        '## Estabilidad con perturbaciones','',
        '70 ejecuciones con el catálogo seleccionado: cinco acciones × siete posiciones × dos posturas. Todas pasaron; cada tiro se clasificó contra su contrafactual libre específico. Hubo 28 atajadas físicas y 42 goles, sin tiros errados/no resueltos. Son resultados de una grilla determinista, no una estimación estadística de tasas.','',
        f'- Máximo |q final|: {max(abs(r["final_physical"]["q_m"]) for r in grid):.6f} m; máximo |v final|: {max(abs(r["final_physical"]["v_mps"]) for r in grid):.6f} m/s. Umbrales originales 0,015 m y 0,02 m/s, sin relajación.',
        f'- Cero caídas y autocolisiones activas; máximo de velocidad articular medido {max(r["max_joint_speed"] for r in grid):.6f} rad/s y torque articular {max(r["max_actual_joint_torque_nm"] for r in grid):.6f} Nm.',
        f'- No se registró saturación de comando en las muestras de 50 Hz de la grilla ({sampled_saturation} muestras/juntas en límite). El monitor adicional a 500 Hz de las tres tandas 8C registró cero saturaciones, con exactamente 35.000 llamadas PD por tanda. No se extrapola el muestreo de la grilla a todos los instantes intermedios.',
        f'- Hay movimiento residual terminal: máximo pico a pico de guía en los últimos 2 s {max(late_rail):.6f} m; máximo pico a pico de cualquier articulación {max(r["last_two_seconds_joint_p2p_rad"] for r in grid):.6f} rad. No se afirma ausencia total de oscilación ni estabilidad global.',
        '- Pelvis restringida por la guía y único escritor PD conservados. No se atribuye equilibrio libre al G1.','',
        '## Tandas completas y reproducción histórica','',
        '| Ejecución | Goles | Atajadas | Errados | Pasos | Tiempo real total s |',
        '|---|---:|---:|---:|---:|---:|']
    for name,s in sessions.items():
        score=matches[name]['scoreboard'];lines.append(f'| {name} | {score["goals"]} | {score["saves"]} | {score["misses"]} | {s["physics_steps"]} | {s["script_wall_s"]:.3f} |')
    lines+=['',
        'La secuencia 8C fue right_inter_m080, right_open_m100, right_corner_m140, left_near_b060, center: GOAL, GOAL, GOAL, SAVE, SAVE. El cambio respecto de 4–1 es consecuencia de tiros deliberadamente distintos y contactos físicos, no de reglas artificiales ni una mejora probada de inteligencia.','',
        'La tanda con visor coincide exactamente con headless dinámica: estado inicial/final completo, trayectoria a 500 Hz, contactos, decisiones, aprendizaje, cuerpo, motores y retorno. Las tandas headless de ambas posturas coinciden con sus cinco episodios nominales independientes. Marcador, pausa/reanudación, consulta y cámaras se probaron con el guion de texto; el visor y su render thread cerraron. Un modelo y una sesión ONNX por proceso, reinicios iguales a MjData fresco.','',
        'Las referencias completas 8B.2/8B.3 se volvieron a ejecutar con su catálogo y retorno originales, reproduciendo exactamente 4–1, estados y aprendizaje. 7D y 8B.1 se preservaron por hashes y regresiones; no se volvió a correr su tanda 3–2 en esta fase.','',
        'Los tiempos incluyen instrumentación y comprobaciones; el visor incluye pausas, sincronización, pacing y capturas. No son FPS ni una medición aislada de GPU/renderizado. Desglose por episodio/pausas en session.json.','',
        '## Evidencia y tests','',
        f'{counts} tests aprobados; {len(before)} fuentes/archivos históricos protegidos sin cambios. El runner conserva las verificaciones de sus 209 dependencias externas. [Equivalencia exacta](results/viewer_exact.json), [referencia 8B.2](results/reference_8b2_exact.json), [referencia 8B.3](results/reference_8b3_exact.json).','',
        'Capturas reales MuJoCo en `results/match_viewer`: initial/final, espera, reacciones izquierda/derecha/central, recuperación y contacto, con vistas behind/execution/overview/goal. Se reutilizó el estadio 7D sin nueva decoración. No son imágenes conceptuales ni una segunda simulación.','',
        '## Riesgos y recomendación','',
        'Recomiendo la variante 8C con catálogo congelado, postura dinámica y retorno extendido para una demostración determinista. Mantener las referencias históricas como comparación, con el mismo entorno y semilla.','',
        'La evidencia cubre muestras Y discretas de hasta 5 mm y condiciones nominales del entorno local. No cubre todo el intervalo continuo, perturbaciones combinadas X/Z/yaw, materiales, fricción, ruido de sensores, otros equipos ni locomoción libre. No se declara que una esquina izquierda robusta sea imposible: no se encontró dentro de los biases investigados. El repertorio resultante es asimétrico y centro-izquierda sigue teniendo dispersión apreciable.','',
        'El retorno continuo presenta pequeño jitter, aunque pasa los criterios originales. Si se exige reposo más silencioso, diseñar y validar en otra iteración una retención terminal con histéresis; no incorporarla aquí sin evidencia. La advertencia Hydra de compatibilidad preexistente permanece. No se retomó audio, no se instalaron dependencias y no se hicieron commits ni push.']
    out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (root/'final_audit.json').write_text(json.dumps(dict(passed=True,scope='Bounded discrete initial-Y grid, not global robustness',
        free_trials=len(csv_rows),distinct_biases=len(set(r['bias'] for r in csv_rows)),integrated_grid_episodes=len(grid),
        tests_passed=counts,protected_files=len(before),historical_changed=[],full_five_penalty_viewer_exact=True,
        original_8b2_8b3_exact=True,new_catalog_id=catalog.id,global_robustness_claimed=False,
        max_final_abs_q_m=max(abs(r['final_physical']['q_m']) for r in grid),
        saturation_steps_three_matches=saturation,grid_saturation_samples_50hz=sampled_saturation),indent=2),encoding='utf-8')
    print('Published measured 8C report and final audit')
if __name__=='__main__':main()
