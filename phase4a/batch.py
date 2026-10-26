"""Serial subprocess measurements. Does not mix concurrent performance runs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenarios', nargs='+', required=True)
    p.add_argument('--modes', nargs='+', choices=['probe','fixed','agent','capacity_left','capacity_right'], default=['probe'])
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--directory', required=True)
    a = p.parse_args()
    directory = Path(a.directory).resolve()
    if not directory.is_relative_to(HERE.parent) or directory.exists():
        raise ValueError('Choose a new result directory within RoboPenalty')
    directory.mkdir(parents=True)
    measurements = []
    for scenario in a.scenarios:
        for repeat in range(1,a.repeats+1):
            for mode in a.modes:
                stem = directory / f'{scenario}_{mode}_{repeat:02d}'
                command = [sys.executable,'-B',str(HERE/'experiment.py'),'--scenario',scenario,
                           '--mode',mode,'--duration','14','--output',str(stem.with_suffix('.json'))]
                start = time.perf_counter()
                process = subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
                elapsed = time.perf_counter()-start
                stem.with_suffix('.stdout.txt').write_text(process.stdout,encoding='utf-8')
                stem.with_suffix('.stderr.txt').write_text(process.stderr,encoding='utf-8')
                record = {'scenario':scenario,'mode':mode,'repeat':repeat,'wall_process_s':elapsed,
                          'exit_code':process.returncode,'result_file':str(stem.with_suffix('.json'))}
                measurements.append(record)
                (directory/'batch.json').write_text(json.dumps(measurements,indent=2),encoding='utf-8')
                if stem.with_suffix('.json').exists():
                    result=json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
                    e=result['evaluation']
                    record.update(foot=e['first_foot_ball'] is not None,
                                  crossing=e['approach_crossing_measured'], goal=e['goal_detected'],
                                  keeper_contact=e['first_keeper_ball'] is not None, failures=result['failures'])
                print(json.dumps(record),flush=True)
                # Unexpected exceptions stop; physical failures are recorded exploratory trials.
                if process.returncode not in (0,2):
                    raise RuntimeError(process.stderr)

if __name__ == '__main__':
    main()
