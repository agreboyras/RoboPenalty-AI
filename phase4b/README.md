# Fase 4B — selección inteligente del delantero

Solo código propio. Las fases anteriores y los repositorios externos se importan
sin modificar sus archivos. No contiene pesos, meshes ni modelos copiados.

## Arquitectura

- `catalog.py`: mapea acciones a presets existentes y carga una referencia histórica
  por acción/distancia. Separa datos geométricos de calibración y evaluación del resultado.
- `striker_agent.py`: observación inicial inmutable, utilidad, exploración y estadísticas
  por contexto. No importa MuJoCo, FreeKick, resultados futuros ni el runner físico.
- `physical_episode.py`: observa el estado inicial real de MuJoCo en t=0, pide una
  acción, guarda la decisión y ejecuta el runner propio de Fase 4A mediante un hook
  anterior al primer paso. FreeKick recibe únicamente su bias runtime existente.
- `tournament.py`: episodios físicos secuenciales, historiales independientes por
  estrategia/oponente y continuación de estadísticas entre episodios de cada grupo.
- `test_striker.py` y `regressions.py`: pruebas de conducta, causalidad y regresiones.

Los hooks afectan únicamente una instancia importada en memoria. Cada episodio
usa un proceso nuevo; no se edita el runner anterior ni se copia el controlador.
La decisión, configuración inicial, ejecución y resultado tienen archivos separados.

## Acciones y observaciones

| Acción del runtime original | Escenario original | Escenario ampliado | target_y_bias |
|---|---|---|---:|
| center | center | long_center | 0 |
| left | preset_left | long_preset_left | +0,75 |
| right | preset_right | long_preset_right | -0,50 |

Son los únicos presets disponibles. Su implementación no es una nueva política.
La configuración ampliada sitúa inicialmente delantero en x=-2 m y pelota en x=-1 m;
arquero en x=4,2 m y arco en x=5 m. Orientaciones, masas, fricciones y límites se
conservan. Los tiros no garantizan un punto de llegada exacto.

La observación anterior al tiro incluye posición lateral, q/v inicial del arquero,
dimensiones geométricas, posición inicial de pelota y delantero, distancia y acciones.
El protocolo conoce el tipo de oponente configurado (fijo/agente): no lo infiere de
su comportamiento futuro. Contexto = distancia/oponente/bin lateral de 0,25 m.
No se mezcla el aprendizaje entre contextos. La evaluación física principal usa
solo distancia ampliada y arquero inicialmente centrado; no demuestra generalización
a posiciones laterales distintas ni identificación de un oponente desconocido.

La geometría histórica de cada preset procede de un probe real de Fase 4A. Se
identifica como `historical_calibration`, con ruta y SHA-256. El selector recibe
solo y de intercepción histórica; no recibe una trayectoria del episodio actual.
La probabilidad inicial de gol NO se carga de los resultados antiguos: arranca neutral.

## Utilidad y aprendizaje

Para acción a y contexto c se guardan goles g, atajadas s y errados m; n=g+s+m.
Estimación Dirichlet con pseudocuentas (1,1,1), supuesto neutral explícito:

```
p_gol = (g+1)/(n+3)
p_errado = (m+1)/(n+3)
coverage = max(0, 1 - abs(y_calibrada - y_arquero)/(semiancho_AABB + radio_pelota))
U = p_gol - 0.5*p_errado - 0.1*coverage
    + 0.15*sqrt(log(1+N)/(1+n))
```

N = resultados resueltos observados en el contexto. Las pseudocuentas y los pesos
0,5/0,1/0,15 son decisiones de diseño, no mediciones ni probabilidades físicas.
Cada candidato registra también su fracción empírica de goles, indefinida si n=0.
`coverage` es una heurística de cercanía a una envolvente inicial: no modela huecos,
rebotes ni la futura reacción del arquero. Las estadísticas observadas corrigen
parcialmente esa limitación.

Exploración: se prueban primero las tres acciones aún no observadas, eligiendo entre
ellas por utilidad. Luego se maximiza U, con desempate reproducible. El bonus puede
volver a favorecer acciones menos ensayadas. No se usa RL para el movimiento.

El episodio pasa por `choose -> pending -> simulación completa -> observe`.
Mientras hay un resultado pendiente no se permite otra elección; observe valida
el identificador y rechaza duplicados o resultados inválidos/sin resolver. Solo
entonces incrementa el contador de la acción seleccionada. La siguiente decisión
recalcula sus utilidades. Las estrategias fija y aleatoria también registran
estadísticas, pero no las usan para elegir.

## Evaluación y auditoría

Se usa la clasificación física de Fase 4A: contacto pie-pelota con fuerza positiva;
gol tiene prioridad; atajada requiere contacto con arquero y gol en el probe
equivalente; un tiro ya errado no se cuenta como atajada. Los probes son referencia
de evaluación histórica, no información futura del agente. Se exige igualdad de
configuración y estados iniciales del tiro y de la trayectoria previa al primer
contacto del arquero en muestras de 50 Hz. Errores físicos o resultados sin resolver
detienen la serie y no se convierten en aprendizaje.

El torneo principal predeclara center como selección fija; random es uniforme con
semilla 2026; utility arranca sin resultados propios. Cada grupo tiene su historia
independiente. Por grupo se hacen 12 episodios de aprendizaje/evaluación en línea,
no un test separado de generalización. También se ejecuta right fijo como referencia
fuerte, conocida por la calibración de Fase 4A. No basta con superar center para
concluir que aprender supera cualquier selección fija.

Cada carpeta de episodio contiene:

- `decision_before_shot.json`: observación inicial, estadísticas previas y utilidades.
- `state_pending.json`: acción elegida pendiente de resultado.
- `physical.json`: física y métricas originales del runner.
- `feedback_after_shot.json`: clasificación, actualización y momento de feedback.
- `state_after.json`: estadísticas persistentes para el siguiente episodio.

## Comandos PowerShell desde TPO-IA

Cada salida debe usar un nombre nuevo. No se sobrescriben episodios ni resultados.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\physical_episode.py --strategy utility --opponent agent --distance long --episode-id manual_001 --output .\RoboPenalty\phase4b\results\manual_001
```

Continuar con aprendizaje del episodio anterior:

```powershell
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\physical_episode.py --strategy utility --opponent agent --distance long --episode-id manual_002 --state .\RoboPenalty\phase4b\results\manual_001\state_after.json --output .\RoboPenalty\phase4b\results\manual_002
```

Comparación completa y regresiones:

```powershell
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\tournament.py --episodes 12 --reference-episodes 3 --seed 2026 --distance long --output .\RoboPenalty\phase4b\results\nuevo_torneo
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\regressions.py --output .\RoboPenalty\phase4b\results\nuevas_regresiones
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\audit.py --directory .\RoboPenalty\phase4b\results\nuevo_torneo --output .\RoboPenalty\phase4b\results\nueva_auditoria.json
& .\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe -B .\RoboPenalty\phase4b\report.py --audit .\RoboPenalty\phase4b\results\nueva_auditoria.json --output .\RoboPenalty\phase4b\NUEVOS_RESULTADOS.md
```

## Procedencia y límites

FreeKick y recursos de RoboNaldo_Deploy se leen en su ubicación original. No se
asume permiso de redistribución. G1 del arquero: Unitree Robotics, BSD-3-Clause,
licencia en ../unitree_mujoco/LICENSE. Se conservan las atribuciones de fases previas.
No se instalaron dependencias, entrenaron pesos ni exportaron modelos compuestos.
La guía física lateral, los postes visuales y el gol por cruce del centro conservan
las simplificaciones documentadas en Fase 4A. Ver RESULTADOS.md para datos medidos.
