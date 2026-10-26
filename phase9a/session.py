import time
from session import CommandMatch as PreviousMatch,Service,CommandBoundary,BoundaryEnd
from game import Phase
from phase9a.selection import SelectionRouter

class Match(PreviousMatch):
    ALLOWED={key:set(value) for key,value in PreviousMatch.ALLOWED.items()}
    ALLOWED[Phase.PREPARING].add(Phase.FINISHED)
    def __init__(self,*args,automatic,service,**kwargs):
        self.router=SelectionRouter(automatic,service);service.match=self
        super().__init__(*args,selector=self.router,service=service,**kwargs)
    def cancel_selection(self):
        if float(self.runtime.data.time)!=0. or self.current.action is not None:raise RuntimeError('Unsafe cancellation outside pre-shot selection')
        self.stop_reason='stop_before_shot';self.transition(Phase.FINISHED);raise BoundaryEnd()

class Script:
    """Owner-thread test fixture. It does not forge voice recognition evidence."""
    def __init__(self,rows):self.rows=rows;self.done=set();self.paused_at=None;self.waiting_since=None
    def tick(self,service):
        c=service.control
        if c.paused and self.paused_at is None:self.paused_at=time.perf_counter()
        if not c.paused:self.paused_at=None
        if c.awaiting_shot and self.waiting_since is None:self.waiting_since=time.perf_counter()
        if not c.awaiting_shot:self.waiting_since=None
        for i,row in enumerate(self.rows):
            if i in self.done or not all(n in self.done for n in row.get('after',[])):continue
            if row.get('phase',c.phase)!=c.phase or row.get('penalty',c.penalty)!=c.penalty:continue
            if row.get('waiting_shot',c.awaiting_shot)!=c.awaiting_shot:continue
            if 'paused' in row and row['paused']!=c.paused:continue
            if row.get('mode',c.mode)!=c.mode:continue
            if float(service.runtime.data.time)+1e-9<row.get('sim_s',0):continue
            if 'wait_wall_s' in row and (self.waiting_since is None or time.perf_counter()-self.waiting_since<row['wait_wall_s']):continue
            if 'pause_wall_s' in row and (self.paused_at is None or time.perf_counter()-self.paused_at<row['pause_wall_s']):continue
            if row.get('voice_error') and not any(e['kind']=='status' and 'ERROR VOZ' in e['text'] for e in c.events):continue
            c.bus.submit(row['text'],'script-text');self.done.add(i)
