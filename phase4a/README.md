# Fase 4A: escenarios físicos y evaluación

Código propio, aislado de las fases 2, 3A y 3B. No contiene modelos, meshes ni
pesos externos. FreeKick se ejecuta en su ubicación original mediante el adaptador
existente; el arquero usa exactamente GoalkeeperAgent de fase 3B y el mecanismo
de fase 3A. Los 59 actuadores conservan sus índices independientes.

## Ejecución desde la raíz TPO-IA, PowerShell

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4a\experiment.py --scenario preset_left --mode agent --duration 14 --output .\RoboPenalty\phase4a\results\nuevo_left.json
```

Cada salida debe tener un nombre nuevo. No se sobrescriben resultados.

```powershell
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4a\batch.py --scenarios center preset_left preset_right --modes fixed agent --repeats 3 --directory .\RoboPenalty\phase4a\results\nueva_comparacion
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4a\analyze.py --directory .\RoboPenalty\phase4a\results\nueva_comparacion --output .\RoboPenalty\phase4a\results\nuevo_resumen.json
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4a\verify.py --directory .\RoboPenalty\phase4a\results\nuevas_regresiones
```

Los probes usados por analyze.py son los originales de exploration y calibration_probes;
solo sirven como referencia para las mismas configuraciones registradas, no para
una configuración editada. Se verifica igualdad de condiciones iniciales del tiro
y de la trayectoria observada antes del contacto con el arquero.

## Condiciones y coordenadas

Mundo +X hacia arco x=5 m, +Z arriba. Izquierda/derecha de tiro vistas por el
delantero: +Y/-Y. Slider positivo = arquero hacia -Y; un tiro left pide q negativo.
Plano de observación/intercepción x=4 m; pelvis del arquero x=4,2 m.
La línea de gol usa el centro de pelota dentro de |y|<=1,5 m, 0<=z<=1,8 m,
con cruce interpolado a 500 Hz. Conserva la convención anterior; no implementa
el reglamento de pelota completa ni simula una red textil. Postes originales
visuales sin colisión; pelota, piso, robots y backstop sí tienen física.

scenarios.py cambia únicamente condiciones iniciales antes del primer paso:
traslada delantero y pelota juntos, gira ambos alrededor del delantero, o cambia
la posición inicial lateral de la pelota. Los presets cambian solo
state.target_y_bias en RAM: 0, +0,75 y -0,50 m, valores existentes del runtime.
El objetivo mundial del controlador sigue siendo [5,0,0.115]. Una orientación o
traslación inicial no garantiza una rotación/traslación equivalente de la trayectoria:
la política recibe el objetivo y reacciona a él.

`probe` aparta el soporte del arquero a y=8 m (primeros probes históricos: y=3 m),
conservando su dinámica. No hay contacto pelota-arquero en los probes guardados.
Es una referencia de evaluación, nunca una observación del agente. `fixed` y
`agent` tienen exactamente el mismo estado inicial, validado por SHA-256.
`capacity_left/right` son diagnósticos del mecanismo: orden sostenida ±0,65 m
desde t=4,18 hasta 8 s y luego centro; no representan otra estrategia inteligente.

Las condiciones `long_*` retrasan físicamente delantero y pelota 2 m en X;
no cambian masa, fricción, gravedad, velocidad de pelota, políticas ni límites.
No se escribe qpos/qvel durante el bucle para fabricar desplazamientos.

## Evaluación

Gol tiene prioridad incluso si hubo contacto. Atajada requiere contacto físico
con fuerza positiva, ausencia de gol y un probe del mismo tiro que sí entraba.
Un tiro que ya erraba en el probe se clasifica como errado, aunque haya contacto.
Los casos sin evidencia suficiente quedan sin resolver. No se deduce atajada
de la sola ausencia de gol. El campo provisional heredado del runner es diagnóstico;
la clasificación final está en los archivos summary generados por analyze.py.

Posiciones, velocidades, contactos y cruces son medidas de MuJoCo. Predicción,
intervalo alcanzable y tiempo mínimo cinemático son estimaciones explícitas.
q al instante de llegada contrafáctica se interpola entre observaciones de 50 Hz.
Los límites AABB de colisión son una envolvente conservadora a la altura de pelota:
no prueban cobertura continua, porque existen huecos y curvaturas.

Los tiempos de proceso incluyen importaciones, hashes, carga, simulación y salida;
scene_build, policy_load y loop_wall son temporizadores internos separados.
Las ejecuciones del batch son secuenciales; no se afirma una mejora de rendimiento.

## Procedencia

Dependencias externas leídas en ubicación original: FreeKick/RoboNaldo_Deploy
(pesos y assets sin autorización de redistribución asumida); G1 arquero de
Unitree Robotics, BSD-3-Clause en ../unitree_mujoco/LICENSE. Las atribuciones
y restricciones de fases anteriores continúan aplicándose. No se exporta el
modelo compuesto ni se copian componentes externos. Cada experimento comprueba
209 hashes externos contra la fase 2 y los 14 fuentes Python de fases previas
antes/después de la ejecución. No hubo entrenamiento ni cambios del agente.

Ver RESULTADOS.md y results/ para las mediciones efectivamente realizadas.
