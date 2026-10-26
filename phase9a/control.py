import time
from control import Control as PreviousControl
from phase9a.commands import LABELS

HELP='Iniciar partido; modo dirigido/automatico; patea al centro/a la izquierda/a la derecha/a la derecha abierta/a la esquina derecha; microfono; estado; mostrar marcador; pausar partida; reanudar partida; salir. Izquierda = centro-izquierda. La llegada depende de la fisica.'

class Control(PreviousControl):
    def __init__(self,bus,mode='directed',emit=print):
        super().__init__(bus,False,emit);self.mode=mode;self.awaiting_shot=False;self.pending_shot=None;self.voice=None
    def open_selection(self):
        self.assert_owner();self.awaiting_shot=True;self.pending_shot=None;return self.bus.open_window()
    def close_selection(self):
        self.assert_owner();self.awaiting_shot=False;self.bus.close_window()
        if self.voice:self.voice.cancel_request()
    def process(self,message):
        self.assert_owner()
        intent=message.intent
        if intent=='help':return True,HELP
        if intent=='state':return True,f'Modo {self.mode.upper()} | estado {self.phase} | penal {self.penalty} | esperando tiro={self.awaiting_shot} | {self.score}'
        if intent and intent.startswith('mode:'):
            mode=intent.split(':',1)[1]
            safe=self.phase in ('READY','FINISHED') or (self.phase=='PREPARING' and self.awaiting_shot)
            if not safe or self.pending_shot or self.paused:return False,'Modo solo entre penales o esperando seleccion, sin pausa ni tiro elegido'
            if self.mode!=mode:self.close_selection();self.mode=mode
            return True,f'Modo {mode.upper()}; arquero autonomo'
        if intent=='listen':
            if not self.awaiting_shot or self.mode!='directed' or self.paused:return False,'Microfono solo mientras se espera una orden dirigida'
            if not self.voice:return False,'Voz no habilitada; use --voice o continue por texto'
            return self.voice.request(self.bus.active_ticket())
        if intent=='unsupported:left_corner':return False,'No hay esquina izquierda validada en 8C. Izquierda disponible: centro-izquierda; repita una orden valida'
        if intent and intent.startswith('shot:'):
            if self.mode!='directed' or not self.awaiting_shot or self.phase!='PREPARING' or self.paused or self.pending_shot:
                return False,'Tiro permitido solo al esperar seleccion en modo dirigido; no se guarda para otro penal'
            if getattr(message,'ticket',None)!=self.bus.active_ticket():return False,'Orden antigua o recibida fuera de esta ventana; repita'
            action=intent.split(':',1)[1]
            if action not in LABELS:return False,'Accion fuera del catalogo 8C'
            self.pending_shot=dict(action=action,text=message.text,source=message.source,ticket=message.ticket)
            self.close_selection()
            return True,f'Accion seleccionada: {LABELS[action]}. Arquero autonomo. La trayectoria depende del contacto fisico'
        accepted,reason=super().handle(intent)
        if intent in ('stop','reset') and accepted:self.close_selection()
        return accepted,reason
    def pump(self):
        self.assert_owner()
        while (m:=self.bus.drain()) is not None:
            if m.generation!=self.bus.epoch():continue
            if m.kind=='status':
                self.emit(f'[microfono] {m.text}',flush=True);self.events.append(dict(kind='status',text=m.text));continue
            before=dict(phase=self.phase,penalty=self.penalty,mode=self.mode,awaiting_shot=self.awaiting_shot)
            accepted,reason=self.process(m)
            event=dict(kind='command',text=m.text,intent=m.intent,source=m.source,capture_id=m.capture_id,
                ticket=getattr(m,'ticket',None),accepted=accepted,reason=reason,state_before=before,
                phase=self.phase,penalty=self.penalty,mode=self.mode,paused=self.paused,
                queue_age_s=time.perf_counter()-m.created,score=dict(self.score),generation=m.generation)
            self.events.append(event)
            self.emit(f'[{m.source}] {m.text!r} -> {m.intent or "desconocido"} | {"ACEPTADO" if accepted else "RECHAZADO"}: {reason}',flush=True)
    def reset(self):
        self.close_selection();self.pending_shot=None;super().reset()
