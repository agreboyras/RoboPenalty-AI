"""Owner-thread command policy, independent from MuJoCo and both agents."""
import threading
import time


class Control:
    def __init__(self, bus, manual_next=False, emit=print):
        self.bus, self.manual_next, self.emit = bus, manual_next, emit
        self.owner = threading.get_ident()
        self.phase = 'READY'
        self.active = self.paused = self.stop_requested = self.start_requested = False
        self.reset_requested = self.next_requested = False
        self.five_requested = False
        self.waiting_next = False
        self.score = {'goals': 0, 'saves': 0, 'misses': 0}
        self.penalty = 0
        self.events = []
        self.on_command_result = None

    def assert_owner(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Commands must be processed by the simulation owner thread')

    def pump(self):
        self.assert_owner()
        while (message := self.bus.drain()) is not None:
            if message.generation != self.bus.epoch(): continue
            if message.kind == 'status':
                self.emit(f'[microfono] {message.text}', flush=True)
                self.events.append({'kind': 'status', 'text': message.text, 'wall': time.perf_counter()})
                continue
            state_before={key:getattr(self,key) for key in
                ('phase','active','paused','start_requested','waiting_next','manual_next','penalty')}
            state_before['score']=dict(self.score)
            accepted, reason = self.handle(message.intent)
            event = {'kind': 'command', 'text': message.text, 'intent': message.intent,
                     'capture_id':message.capture_id,
                     'source': message.source, 'accepted': accepted, 'reason': reason,
                     'state_before':state_before,
                     'phase': self.phase, 'paused': self.paused, 'penalty': self.penalty,
                     'generation': message.generation, 'queue_age_s': time.perf_counter()-message.created,
                     'score': dict(self.score)}
            self.events.append(event)
            if self.on_command_result:self.on_command_result(event)
            self.emit(f'[{message.source}] {message.text!r} -> {message.intent or "desconocido"} | '
                      f'{"ACEPTADO" if accepted else "RECHAZADO"}: {reason} | {self.phase}', flush=True)

    def handle(self, intent):
        self.assert_owner()
        if intent is None: return False, 'No reconozco una orden valida'
        if intent == 'score':
            return True, f'Goles {self.score["goals"]} / Atajadas {self.score["saves"]} / Errados {self.score["misses"]}'
        if intent in ('start', 'five'):
            if self.active or self.start_requested or self.phase != 'READY':
                return False, 'Ya hay una tanda o debe reiniciar primero'
            self.start_requested = True
            self.five_requested = intent == 'five'
            return True, 'Inicio solicitado'
        if intent == 'reset':
            if self.phase not in ('READY', 'FINISHED') or self.start_requested:
                return False, 'Reinicio permitido solo en READY o FINISHED; no durante un penal'
            self.reset_requested = True
            self.paused = False
            self.next_requested = False
            self.bus.rotate()
            return True, 'Nueva tanda preparada; comandos pendientes descartados'
        if intent == 'stop':
            self.stop_requested = True
            self.paused = False
            return True, 'Se termina el penal en curso y se cierra de forma controlada'
        if intent == 'pause':
            if not self.active or self.phase == 'FINISHED' or self.paused:
                return False, 'No hay una tanda activa sin pausar'
            self.paused = True
            return True, 'Pausa en el limite entre pasos fisicos'
        if intent == 'resume':
            if not self.paused: return False, 'La partida no esta pausada'
            self.paused = False
            return True, 'Partida reanudada'
        if intent == 'next':
            if not self.manual_next or not self.waiting_next or self.phase != 'READY' or self.paused or self.next_requested:
                return False, 'Siguiente penal solo al esperar en READY con --manual-next, sin pausa'
            self.next_requested = True
            return True, 'Siguiente penal autorizado'
        return False, 'Orden no disponible'

    def reset(self):
        self.assert_owner()
        self.phase = 'READY'
        self.active = self.paused = self.stop_requested = self.start_requested = False
        self.reset_requested = self.next_requested = self.five_requested = self.waiting_next = False
        self.score = {'goals': 0, 'saves': 0, 'misses': 0}
        self.penalty = 0
