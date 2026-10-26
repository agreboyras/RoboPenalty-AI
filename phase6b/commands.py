"""Spanish grammar and bounded, generation-aware input bus. No simulation imports."""
from dataclasses import dataclass
import queue
import re
import threading
import time
import unicodedata


def interpret(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if unicodedata.category(c) != 'Mn')
    words = re.findall(r'[a-z0-9]+', text)
    if words[:1] == ['por'] and words[1:2] == ['favor']: words = words[2:]
    if words[-2:] == ['por', 'favor']: words = words[:-2]
    phrase = ' '.join(words)
    patterns = {
        'start': r'(iniciar|inicia|empezar|empieza|comenzar|comienza) (el |la |una )?(partido|partida|tanda)',
        'five': r'(patear|patea|lanzar) (cinco|5) penales',
        'next': r'(siguiente penal|el siguiente penal|avanzar al siguiente penal)',
        'pause': r'(pausar|pausa) (el |la )?(partido|partida|tanda)',
        'resume': r'(continuar|continua|reanudar|reanuda) (el |la )?(partido|partida|tanda)',
        'stop': r'(detener|deten|terminar|termina) (el |la )?(partido|partida|tanda)',
        'reset': r'(reiniciar|reinicia) (el |la )?(partido|partida|tanda)',
        'score': r'(mostrar|mostra|muestra|ver) (el )?marcador|cuantos goles (llevamos|tenemos)|marcador',
    }
    return next((intent for intent, pattern in patterns.items() if re.fullmatch(pattern, phrase)), None)


@dataclass(frozen=True)
class Message:
    text: str
    intent: str | None
    source: str
    generation: int
    created: float
    kind: str = 'command'
    capture_id: str | None = None


class CommandBus:
    def __init__(self, capacity=64):
        self.queue = queue.Queue(capacity)
        self.lock = threading.Lock()
        self.generation = 0
        self.dropped = 0

    def epoch(self):
        with self.lock: return self.generation

    def submit(self, text, source='text', generation=None, kind='command', capture_id=None):
        with self.lock:
            epoch = self.generation if generation is None else generation
            if epoch != self.generation:
                self.dropped += 1
                return False
            item = Message(text, interpret(text) if kind == 'command' else None,
                           source, epoch, time.perf_counter(), kind,capture_id)
            try: self.queue.put_nowait(item)
            except queue.Full:
                self.dropped += 1
                return False
            return True

    def drain(self):
        # One at a time: a reset can clear the remainder atomically.
        try: return self.queue.get_nowait()
        except queue.Empty: return None

    def rotate(self):
        with self.lock:
            self.generation += 1
            count = 0
            while self.drain() is not None: count += 1
            return count
