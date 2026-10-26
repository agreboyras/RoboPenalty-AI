"""Sequential fresh-process motion tests plus unchanged phase-2 regression."""
import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--results')
    args = parser.parse_args()
    home = Path(__file__).resolve().parent
    folder = Path(args.results).resolve() if args.results else home / 'results' / datetime.datetime.now().strftime('benchmark_%Y%m%d_%H%M%S')
    if not folder.is_relative_to(home.parents[0]) or args.repeats < 1:
        raise ValueError('Invalid results folder or repeat count')
    folder.mkdir(parents=True, exist_ok=False)
    processes = []
    rows = []
    for repeat in range(1, args.repeats+1):
        for case in ['phase2_block','center','left','right','return','moving_contact','limits']:
            duration = 18 if case == 'limits' else 14
            target = folder / f'{case}_{repeat:02d}.json'
            if case == 'phase2_block':
                script = home.parents[0] / 'phase2/experiment.py'
                command_case = 'block'
            else:
                script, command_case = home / 'experiment.py', case
            command = [sys.executable, '-B', str(script), '--case', command_case,
                       '--duration', str(duration), '--output', str(target)]
            start = time.perf_counter()
            proc = subprocess.run(command, cwd=folder, text=True, capture_output=True, timeout=180,
                                  encoding='utf-8', errors='replace',
                                  env=dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYGAME_HIDE_SUPPORT_PROMPT='1'))
            elapsed = time.perf_counter()-start
            target.with_suffix('.stdout.txt').write_text(proc.stdout, encoding='utf-8')
            target.with_suffix('.stderr.txt').write_text(proc.stderr, encoding='utf-8')
            process = {'case': case, 'repeat': repeat, 'command': command,
                       'process_wall_s': elapsed, 'exit_code': proc.returncode, 'result': str(target)}
            processes.append(process)
            (folder/'processes.json').write_text(json.dumps(processes, indent=2), encoding='utf-8')
            print(json.dumps(process), flush=True)
            if proc.returncode:
                raise RuntimeError(f'{case} failed: inspect {target}')
            result = json.loads(target.read_text(encoding='utf-8'))
            if case == 'phase2_block':
                physics = result['physics']
                row = {'case': case, 'repeat': repeat, 'process_wall_s': elapsed,
                       'loop_wall_s': result['timing']['simulation_loop_wall_s'],
                       'simulated_s': result['simulated_s'], 'passed': True,
                       'foot_contact_s': physics['first_shooter_foot_ball']['time_sim_s'],
                       'moving_contact_speed_mps': None, 'final_slide_m': None,
                       'peak_speed_mps': None, 'peak_acceleration_mps2': None,
                       'goal': physics['goal_detected'], 'shooter_fall': physics['shooter_first_fall'] is not None}
            else:
                p, r = result['physics'], result['rail']
                row = {'case': case, 'repeat': repeat, 'process_wall_s': elapsed,
                       'loop_wall_s': result['timing']['loop_wall_s'],
                       'simulated_s': result['simulated_s'], 'passed': result['passed'],
                       'foot_contact_s': p['first_foot_ball']['time_sim_s'],
                       'moving_contact_speed_mps': p['first_keeper_ball']['rail_speed_mps'] if p['first_keeper_ball'] else None,
                       'final_slide_m': r['final_q_m'], 'peak_speed_mps': r['peak_speed_mps'],
                       'peak_acceleration_mps2': r['peak_acceleration_mps2'],
                       'goal': p['goal_detected'], 'shooter_fall': p['shooter_first_fall_s'] is not None}
            rows.append(row)
    groups = {}
    for case in dict.fromkeys(r['case'] for r in rows):
        selected = [r for r in rows if r['case'] == case]
        groups[case] = {'count': len(selected), 'mean_process_s': statistics.mean(r['process_wall_s'] for r in selected),
                        'min_process_s': min(r['process_wall_s'] for r in selected),
                        'max_process_s': max(r['process_wall_s'] for r in selected),
                        'mean_loop_s': statistics.mean(r['loop_wall_s'] for r in selected),
                        'simulated_s': selected[0]['simulated_s'],
                        'all_passed': all(r['passed'] and not r['shooter_fall'] for r in selected)}
    summary = {'groups': groups, 'runs': rows}
    (folder/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (folder/'summary.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'folder': str(folder), 'groups': groups}, indent=2), flush=True)


if __name__ == '__main__':
    main()
