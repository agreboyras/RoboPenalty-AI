# Auditoría articular 8B.3

| Articulación | Actuador | Rango rad | Ref histórica | Clip software Nm | Límite fuerza articular Nm |
|---|---:|---|---:|---:|---|
| gk/left_hip_pitch_joint | 29 | [-2.5307, 2.8798] | 0.0 | 88.0 | [-88.0, 88.0] |
| gk/left_hip_roll_joint | 30 | [-0.5236, 2.9671] | 0.0 | 139.0 | [-88.0, 88.0] |
| gk/left_hip_yaw_joint | 31 | [-2.7576, 2.7576] | 0.0 | 88.0 | [-88.0, 88.0] |
| gk/left_knee_joint | 32 | [-0.087267, 2.8798] | 0.0 | 139.0 | [-139.0, 139.0] |
| gk/left_ankle_pitch_joint | 33 | [-0.87267, 0.5236] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/left_ankle_roll_joint | 34 | [-0.2618, 0.2618] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/right_hip_pitch_joint | 35 | [-2.5307, 2.8798] | 0.0 | 88.0 | [-88.0, 88.0] |
| gk/right_hip_roll_joint | 36 | [-2.9671, 0.5236] | 0.0 | 139.0 | [-88.0, 88.0] |
| gk/right_hip_yaw_joint | 37 | [-2.7576, 2.7576] | 0.0 | 88.0 | [-88.0, 88.0] |
| gk/right_knee_joint | 38 | [-0.087267, 2.8798] | 0.0 | 139.0 | [-139.0, 139.0] |
| gk/right_ankle_pitch_joint | 39 | [-0.87267, 0.5236] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/right_ankle_roll_joint | 40 | [-0.2618, 0.2618] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/waist_yaw_joint | 41 | [-2.618, 2.618] | 0.0 | 88.0 | [-88.0, 88.0] |
| gk/waist_roll_joint | 42 | [-0.52, 0.52] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/waist_pitch_joint | 43 | [-0.52, 0.52] | 0.0 | 50.0 | [-50.0, 50.0] |
| gk/left_shoulder_pitch_joint | 44 | [-3.0892, 2.6704] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/left_shoulder_roll_joint | 45 | [-1.5882, 2.2515] | 0.25 | 25.0 | [-25.0, 25.0] |
| gk/left_shoulder_yaw_joint | 46 | [-2.618, 2.618] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/left_elbow_joint | 47 | [-1.0472, 2.0944] | 0.3 | 25.0 | [-25.0, 25.0] |
| gk/left_wrist_roll_joint | 48 | [-1.97222, 1.97222] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/left_wrist_pitch_joint | 49 | [-1.61443, 1.61443] | 0.0 | 5.0 | [-5.0, 5.0] |
| gk/left_wrist_yaw_joint | 50 | [-1.61443, 1.61443] | 0.0 | 5.0 | [-5.0, 5.0] |
| gk/right_shoulder_pitch_joint | 51 | [-3.0892, 2.6704] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/right_shoulder_roll_joint | 52 | [-2.2515, 1.5882] | -0.25 | 25.0 | [-25.0, 25.0] |
| gk/right_shoulder_yaw_joint | 53 | [-2.618, 2.618] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/right_elbow_joint | 54 | [-1.0472, 2.0944] | 0.3 | 25.0 | [-25.0, 25.0] |
| gk/right_wrist_roll_joint | 55 | [-1.97222, 1.97222] | 0.0 | 25.0 | [-25.0, 25.0] |
| gk/right_wrist_pitch_joint | 56 | [-1.61443, 1.61443] | 0.0 | 5.0 | [-5.0, 5.0] |
| gk/right_wrist_yaw_joint | 57 | [-1.61443, 1.61443] | 0.0 | 5.0 | [-5.0, 5.0] |

PD histórico: Kp=70, Kd=5; motores 29–57, guía 58. Pelvis anclada en altura y orientación, con desplazamiento lateral físico. No representa equilibrio humanoide libre.

Se conservan piernas/tobillos: flexionar rodillas no puede bajar la pelvis y puede descargar/despegar pies. Esta variante probará brazos y una inclinación de torso pequeña antes de considerar cambios de piernas.

Contactos iniciales del arquero: `[]`. Las máscaras y exclusiones completas están en audit.json; se medirán autocolisiones activas y penetraciones en ejecución, sin activar contactos nuevos.