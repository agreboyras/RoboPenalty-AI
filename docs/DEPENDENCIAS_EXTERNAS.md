# Dependencias externas

Se publica código propio y calibraciones numéricas seguras. No se redistribuyen modelos, FreeKick, ONNX, NPZ, meshes, entornos ni pesos de voz.

## Recursos

Mantener RoboPenalty, RoboNaldo_Deploy y unitree_mujoco como carpetas hermanas. Las raíces se resuelven desde el proyecto. portability/external_manifest.json contiene 209 rutas relativas con SHA-256; todas deben existir y coincidir. No hay descargas automáticas.

Deploy necesita módulos common/FSM, _FreeKickOnlyFSM en deploy_mujoco/deploy_mujoco.py, configuraciones MuJoCo/FreeKick, policy/robonaldo/model/policy-obs-aic.onnx, freekick_motion.npz y g1_description/scene_with_ball.xml con sus includes/meshes.

Unitree necesita unitree_robots/g1/g1_29dof.xml, includes/meshes y LICENSE.

Procedencias:
- https://github.com/OpenDriveLab/RoboNaldo_Deploy
- https://github.com/agreboyrasFacu1/TP07-IA-G1-Futbol
- https://github.com/unitreerobotics/unitree_mujoco

Deploy tenía modificaciones locales además de HEAD ce4b34d1bccfd0420a81bf1688271d86feb8a117; clonar ese commit no garantiza las adaptaciones usadas. Unitree observado: 1eb6642e3f3fdfb7fb13a9794fd6a2dd93ea0e7d. Solicitar acceso autorizado a los archivos exactos y verificar el manifiesto. Los derechos de redistribución de FreeKick/recursos Deploy siguen sin aclararse; permanecen fuera de esta publicación.

## Entorno y límites

Windows y Python 3.12.14 en la instalación validada. requirements.txt contiene versiones directas observadas, no un lock multiplataforma. No se hizo instalación limpia ni prueba en otra PC. El visor requiere OpenGL. El camino probado no requiere entrenamiento, CUDA, ROS, DDS ni PyTorch.

No instalar automáticamente el requirements de Deploy: mezcla versiones antiguas y dependencias de robot real. Primero conseguir recursos autorizados; después preparar el entorno del proyecto.

Los entrypoints históricos quedan intactos. Algunos requieren archivos privados/archivados y no son el launcher público. run_robopenalty.py elimina el baseline privado del flujo normal mediante un adaptador acotado. portability/run_historical.py permite ensayar 3A/3B/4A con el manifiesto relativo. Otros análisis archivísticos no quedan automáticamente portados.

La voz todavía no funciona de forma confiable. Es opcional y no validada; texto siempre disponible. requirements-voice.txt no incluye modelo ni autorización para descargarlo. Su futura validación debe planificarse explícitamente.

