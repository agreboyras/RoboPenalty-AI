"""Run fresh, sequential processes and save diagnostic results only."""
import argparse
import csv
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--results', default=str(Path(__file__).parent / 'results' / 'benchmark'))
    args = parser.parse_args()
    folder = Path(args.results).resolve()
    if not folder.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Results must stay inside RoboPenalty')
    folder.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).with_name('experiment.py')
    records = []
    for repetition in range(1, args.repeats + 1):
        # Interleave reference and two-robot conditions to reduce timing-order bias.
        for case in ['single', 'clear', 'block']:
            stem = f'{case}_{repetition:02d}'
            target = folder / f'{stem}.json'
            command = [sys.executable, '-B', str(script), '--case', case,
                       '--duration', '14', '--output', str(target)]
            start = time.perf_counter()
            try:
                proc = subprocess.run(command, cwd=folder, capture_output=True, text=True,
                                      encoding='utf-8', errors='replace', timeout=180,
                                      env=dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
                                               PYGAME_HIDE_SUPPORT_PROMPT='1'))
            except subprocess.TimeoutExpired as exc:
                (folder / 'timeout.txt').write_text(str(exc), encoding='utf-8')
                raise
            elapsed = time.perf_counter() - start
            (folder / f'{stem}.stdout.txt').write_text(proc.stdout, encoding='utf-8')
            (folder / f'{stem}.stderr.txt').write_text(proc.stderr, encoding='utf-8')
            row = {'case': case, 'repetition': repetition, 'process_wall_s': elapsed,
                   'exit_code': proc.returncode, 'file': str(target)}
            records.append(row)
            (folder / 'processes.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
            print(json.dumps(row), flush=True)
            if proc.returncode:
                raise RuntimeError(f'{stem} failed with {proc.returncode}; see saved diagnostics')
    groups = {}
    baseline = json.loads(Path(records[0]['file']).read_text(encoding='utf-8'))
    table = []
    for case in ['single', 'clear', 'block']:
        items = [r for r in records if r['case'] == case]
        results = [json.loads(Path(r['file']).read_text(encoding='utf-8')) for r in items]
        for process, result in zip(items, results):
            physics = result['physics']
            if result['warnings'] or result['external_inputs']['original_files_changed']:
                raise AssertionError('Engine warning or original-file change')
            if physics['shooter_keeper_contact']:
                raise AssertionError('Unexpected contact between robots')
            if case != 'single' and not result['control']['robot_actuator_sets_disjoint']:
                raise AssertionError('Robot control maps overlap')
            if case == 'clear' and physics['first_keeper_ball'] is not None:
                raise AssertionError('Off-path goalkeeper touched the ball')
            row = {'case': case, 'repetition': process['repetition'],
                   'process_wall_s': process['process_wall_s'],
                   'scene_build_s': result['timing']['scene_build_s'],
                   'policy_load_s': result['timing']['policy_initialization_s'],
                   'simulation_wall_s': result['timing']['simulation_loop_wall_s'],
                   'simulated_s': result['simulated_s'],
                   'foot_contact_sim_s': physics['first_shooter_foot_ball']['time_sim_s'],
                   'keeper_contact_sim_s': physics['first_keeper_ball']['time_sim_s'] if physics['first_keeper_ball'] else None,
                   'displacement_m': physics['ball_net_displacement_m'],
                   'goal': physics['goal_detected'], 'shooter_fall': physics['shooter_first_fall'] is not None,
                   'max_tilt_deg': physics['shooter_max_tilt_deg']}
            table.append(row)
        durations = [r['process_wall_s'] for r in items]
        loops = [r['timing']['simulation_loop_wall_s'] for r in results]
        # Compare state at matching times, using the current single-robot run.
        deltas = []
        before_joint, before_position, overall_joint, overall_position = [], [], [], []
        for result in results:
            deltas.append(max(abs(a-b) for base, other in zip(baseline['shooter_checkpoints'], result['shooter_checkpoints'])
                              for key in ['shooter_root_qpos', 'shooter_joint_qpos']
                              for a, b in zip(base[key], other[key])))
            contact = result['physics']['first_keeper_ball']
            contact_time = contact['time_sim_s'] if contact else float('inf')
            for base, other in zip(baseline['shooter_checkpoints'], result['shooter_checkpoints']):
                joint_delta = max(abs(a-b) for a, b in zip(base['shooter_joint_qpos'], other['shooter_joint_qpos']))
                position_delta = max(abs(a-b) for a, b in zip(base['shooter_root_qpos'][:3], other['shooter_root_qpos'][:3]))
                overall_joint.append(joint_delta)
                overall_position.append(position_delta)
                if other['time_sim_s'] < contact_time:
                    before_joint.append(joint_delta)
                    before_position.append(position_delta)
        groups[case] = {'count': len(items), 'mean_process_wall_s': statistics.mean(durations),
                        'min_process_wall_s': min(durations), 'max_process_wall_s': max(durations),
                        'mean_simulation_loop_s': statistics.mean(loops),
                        'mean_scene_build_s': statistics.mean(r['timing']['scene_build_s'] for r in results),
                        'mean_policy_initialization_s': statistics.mean(r['timing']['policy_initialization_s'] for r in results),
                        'max_shooter_checkpoint_delta_vs_single': max(deltas),
                        'max_shooter_joint_delta_before_keeper_contact_rad': max(before_joint),
                        'max_shooter_root_position_delta_before_keeper_contact_m': max(before_position),
                        'max_shooter_joint_delta_overall_rad': max(overall_joint),
                        'max_shooter_root_position_delta_overall_m': max(overall_position),
                        'goals': sum(r['physics']['goal_detected'] for r in results),
                        'keeper_ball_contacts': sum(r['physics']['first_keeper_ball'] is not None for r in results),
                        'falls': sum(r['physics']['shooter_first_fall'] is not None for r in results)}
    for case in ['clear', 'block']:
        groups[case]['process_overhead_vs_current_single_percent'] = 100 * (groups[case]['mean_process_wall_s'] / groups['single']['mean_process_wall_s'] - 1)
        groups[case]['simulation_overhead_vs_current_single_percent'] = 100 * (groups[case]['mean_simulation_loop_s'] / groups['single']['mean_simulation_loop_s'] - 1)
    with (folder / 'summary.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=table[0].keys())
        writer.writeheader()
        writer.writerows(table)
    summary = {'groups': groups, 'runs': table,
               'timing_note': 'Process wall includes interpreter startup, imports, input hash checks, build, policy load, loop, and shutdown. Loop timer excludes model/policy load; includes own control/diagnostics. No render in these measurements.',
               'phase1_mean_process_wall_s': 8.772916659992188,
               'sampling_note': 'Ball speed sampled at 500 Hz here vs 50 Hz in original benchmark; speed maxima are not directly comparable.'}
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(groups, indent=2), flush=True)


if __name__ == '__main__':
    main()
