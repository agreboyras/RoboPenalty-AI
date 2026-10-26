"""Exercise the actual Windows stdin worker through a pipe, not Script or voice."""
from bootstrap import *
import json
import subprocess
import threading

def main():
    output=HERE/'results/console_pipe'
    if output.exists():raise ValueError('Evidence exists')
    process=subprocess.Popen([sys.executable,'-B',str(HERE/'run_session.py'),'--once','--penalties','1',
        '--output',str(output)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',bufsize=1)
    lines=[];sent=[]
    def consume():
        for line in process.stdout:
            lines.append(line)
            command=None
            if line.startswith('READY |'):command='Iniciar partido'
            elif line.startswith('READY PARA ELEGIR'):command='Patea al centro'
            if command:
                process.stdin.write(command+'\n');process.stdin.flush();sent.append(command)
    reader=threading.Thread(target=consume);reader.start()
    try:code=process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        process.kill();process.wait();raise
    finally:reader.join(timeout=3);process.stdin.close()
    (HERE/'results/console_pipe.log').write_text(''.join(lines),encoding='utf-8')
    assert code==0 and len(sent)==2
    report=json.loads((output/'session.json').read_text(encoding='utf-8'))
    assert report['console_worker_joined'] and report['physics_steps']==7000
    assert all(e['source']=='text' for e in report['commands'] if e['kind']=='command')
    print('Actual stdin pipe: start, directed shot and worker shutdown passed')
if __name__=='__main__':main()
