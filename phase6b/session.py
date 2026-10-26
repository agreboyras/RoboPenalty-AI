"""Minimal extension points around the unchanged phase-5/6A implementations."""
from dataclasses import asdict
from pathlib import Path
import sys
import threading
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'phase6a'))
from integration import VisualRuntime, VisualMatch
from presentation import Presenter
from game import Phase


class BoundaryEnd(Exception): pass


class Script:
    """Deterministic text-input fixture. Scheduling is test-only, on the owner."""
    def __init__(self, rows):
        self.rows = rows
        self.done = set()
        self.paused_at = None

    def tick(self, service):
        c = service.control
        if c.paused and self.paused_at is None: self.paused_at = time.perf_counter()
        if not c.paused: self.paused_at = None
        for i, row in enumerate(self.rows):
            if i in self.done: continue
            if not all(j in self.done for j in row.get('after', [])): continue
            if row.get('phase', c.phase) != c.phase: continue
            if row.get('penalty', c.penalty) != c.penalty: continue
            if 'paused' in row and row['paused'] != c.paused: continue
            if float(service.runtime.data.time)+1e-9 < row.get('sim_s', 0): continue
            if 'pause_wall_s' in row and (self.paused_at is None or time.perf_counter()-self.paused_at < row['pause_wall_s']): continue
            if row.get('waiting_next', False) and not c.waiting_next: continue
            service.control.bus.submit(row['text'], 'script-text')
            self.done.add(i)


class Service:
    def __init__(self, control, runtime, presenter, script=None):
        self.control, self.runtime, self.presenter = control, runtime, presenter
        self.script = script
        self.pause_records = []

    def poll(self):
        self.control.assert_owner()
        if self.script: self.script.tick(self)
        self.control.pump()

    def checkpoint(self):
        self.poll()
        if not self.control.paused: return
        start = time.perf_counter()
        before = self.runtime.integration_state(self.runtime.data)
        sim = float(self.runtime.data.time)
        while self.control.paused:
            self.presenter.sync('pause')
            time.sleep(.02)
            self.poll()
        duration = time.perf_counter()-start
        unchanged = bool(self.runtime.engine.np.array_equal(before, self.runtime.integration_state(self.runtime.data)))
        if not unchanged: raise RuntimeError('Control pause changed authoritative physics')
        # A control pause is excluded from the visual real-time pacing deadline.
        if hasattr(self.presenter, 'episode_start'): self.presenter.episode_start += duration
        self.pause_records.append({'wall_s': duration, 'sim_before_s': sim,
                                   'sim_after_s': float(self.runtime.data.time),
                                   'full_integration_state_unchanged': unchanged})

    def idle(self):
        self.checkpoint()
        self.presenter.sync('pause')
        time.sleep(.02)


class CommandBoundary:
    def __init__(self, base, service): self.base, self.service, self.steps = base, service, 0
    def __getattr__(self, name): return getattr(self.base, name)
    def mj_step(self, model, data, *args, **kwargs):
        self.service.checkpoint()  # no reset, motor command or integration here
        result = self.base.mj_step(model, data, *args, **kwargs)
        self.steps += 1
        return result


class CommandPresenter(Presenter):
    service = None

    def __init__(self,*args,**kwargs):
        existing = set(threading.enumerate())
        super().__init__(*args,**kwargs)
        # MuJoCo 3.13 launch_passive starts a daemon render thread. Handle.close()
        # only requests exit; join its newly created thread before Python atexit
        # terminates GLFW. No monkey-patching or private viewer handle access.
        self.render_threads = [t for t in threading.enumerate() if t not in existing
                               and t.name.endswith('(_launch_internal)')]
        self.render_joined = self.handle is None

    def close(self):
        super().close()
        for thread in self.render_threads: thread.join(timeout=3.)
        self.render_joined = self.handle is None or (bool(self.render_threads)
                             and all(not t.is_alive() for t in self.render_threads))
        if self.render_threads and not self.render_joined:
            raise RuntimeError('Native render thread did not finish after close')

    def summary(self):
        return {**super().summary(),'viewer_render_thread_joined':self.render_joined,
                'viewer_render_thread_names':[t.name for t in self.render_threads]}

    def overlay(self):
        original = self.status
        if self.service and self.service.control.paused:
            self.status = {**original, 'phase': original.get('phase', '')+' [PAUSA]'}
        try: super().overlay()
        finally: self.status = original

    def pause(self, kind, seconds):
        # Poll even without a viewer; headless has no presentation delay.
        if self.service: self.service.checkpoint()
        if self.handle is None: return
        before = self.runtime.integration_state(self.runtime.data)
        start = time.perf_counter()
        sync_before = self.sync_times['pause']
        sleep_s = 0.
        while True:
            self.sync('pause')
            if self.service: self.service.checkpoint()
            remaining = seconds-(time.perf_counter()-start)
            if remaining <= 0: break
            t = time.perf_counter(); time.sleep(min(1/self.config.fps, remaining))
            sleep_s += time.perf_counter()-t
        unchanged = bool(self.runtime.engine.np.array_equal(before, self.runtime.integration_state(self.runtime.data)))
        if not unchanged: raise RuntimeError('Presentation pause changed physics')
        self.pauses.append({'kind': kind, 'penalty': self.status.get('penalty'),
            'requested_s': seconds, 'wall_s': time.perf_counter()-start, 'sleep_s': sleep_s,
            'sync_wall_s': self.sync_times['pause']-sync_before,
            'physics_unchanged': unchanged, 'time_sim_s': float(self.runtime.data.time)})


class CommandMatch(VisualMatch):
    # A controlled stop at READY is an orchestration transition, with no physics reset.
    ALLOWED = {phase: set(targets) for phase, targets in VisualMatch.ALLOWED.items()}
    ALLOWED[Phase.READY].add(Phase.FINISHED)
    def __init__(self, *args, service, **kwargs):
        self.service = service
        self.stop_reason = None
        super().__init__(*args, **kwargs)

    def transition(self, phase):
        c = self.service.control
        c.score = {key: getattr(self.score, key) for key in ('goals','saves','misses')}
        if phase == Phase.PREPARING:
            c.penalty = self.current.number
            self.publish()
            c.waiting_next = c.manual_next and c.penalty > 1
            if c.waiting_next:
                print('READY | Diga siguiente penal para avanzar', flush=True)
            self.service.checkpoint()
            while c.waiting_next and not c.next_requested and not c.stop_requested and not c.reset_requested:
                self.service.idle()
            c.waiting_next = c.next_requested = False
            if c.stop_requested or c.reset_requested:
                self.stop_reason = 'reset' if c.reset_requested else 'stop'
                if c.stop_requested:
                    super().transition(Phase.FINISHED)
                    c.phase = 'FINISHED'
                raise BoundaryEnd()
        if self.phase == Phase.RESOLVING and c.stop_requested:
            phase = Phase.FINISHED
        super().transition(phase)
        c.phase = self.phase.value
        c.penalty = self.current.number if self.current else 0
        c.score = {key: getattr(self.score, key) for key in ('goals','saves','misses')}
        self.service.checkpoint()
        if phase in (Phase.READY, Phase.FINISHED) and (c.stop_requested or c.reset_requested):
            self.stop_reason = 'reset' if c.reset_requested else 'stop'
            if c.stop_requested and self.phase == Phase.READY:
                super().transition(Phase.FINISHED)
                c.phase = 'FINISHED'
            raise BoundaryEnd()

    def play(self):
        start = time.perf_counter()
        try: return super().play()
        except BoundaryEnd:
            # Only reached between completed episodes, never aborting a physical shot.
            result = {'config': asdict(self.config), 'phase': self.phase.value,
                'termination': self.stop_reason, 'scoreboard': asdict(self.score),
                'transitions': self.transitions, 'play_wall_s': time.perf_counter()-start,
                'total_simulated_s': sum(x['simulated_s'] for x in self.score.history),
                'striker_statistics': self.selector.snapshot(), 'runtime': self.runtime.summary()}
            self.save(self.output/'match.json', result)
            return result
