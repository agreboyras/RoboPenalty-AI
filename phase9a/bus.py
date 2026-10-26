from dataclasses import dataclass
import queue
import time
from phase7d.cameras import CameraBus
from phase9a.commands import interpret

@dataclass(frozen=True)
class Message:
    text:str;intent:str|None;source:str;generation:int;created:float
    kind:str='command';capture_id:str|None=None;ticket:int|None=None

class InputBus(CameraBus):
    def __init__(self,camera_requests=None):
        super().__init__(camera_requests=camera_requests or queue.Queue(16))
        self.ticket=None;self.ticket_counter=0
    def open_window(self):
        with self.lock:
            self.ticket_counter+=1;self.ticket=self.ticket_counter;return self.ticket
    def close_window(self):
        with self.lock:self.ticket=None
    def active_ticket(self):
        with self.lock:return self.ticket
    def submit(self,text,source='text',generation=None,kind='command',capture_id=None,*,ticket='current'):
        if source in ('text','script-text') and kind=='command' and text.strip().lower().startswith('/cam '):
            return super().submit(text,source,generation,kind,capture_id)
        with self.lock:
            epoch=self.generation if generation is None else generation
            if epoch!=self.generation:self.dropped+=1;return False
            item=Message(text,interpret(text) if kind=='command' else None,source,epoch,time.perf_counter(),kind,capture_id,
                self.ticket if ticket=='current' else ticket)
            try:self.queue.put_nowait(item)
            except queue.Full:self.dropped+=1;return False
            return True
    def rotate(self):
        result=super().rotate();self.close_window();return result
