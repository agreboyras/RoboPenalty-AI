from bootstrap import *
import threading
import unittest
from dataclasses import fields
from phase9a.commands import interpret
from phase9a.bus import InputBus
from phase9a.control import Control
from observations import Observation

class Tests(unittest.TestCase):
    def control(self):
        b=InputBus();c=Control(b,emit=lambda *a,**k:None);c.phase='PREPARING';c.active=True;c.open_selection();return b,c
    def test_each_action(self):
        cases={'Pateá a la izquierda':'left_near_b060','PATEA A LA DERECHA':'right_inter_m080','Dispará al centro!':'center',
            'Tirá hacia la derecha abierta':'right_open_m100','Por favor, patea a la esquina derecha':'right_corner_m140'}
        for text,action in cases.items():self.assertEqual(interpret(text),'shot:'+action)
    def test_accents_and_verbs(self):
        for v in ('Pateá','Patea','Patear','Tirá','Tira','Tirar','Dispará','Dispara','Disparar'):
            self.assertEqual(interpret(v+' al centro'),'shot:center')
    def test_ambiguity_fails_closed(self):
        for text in ('patea izquierda o derecha','no patea a la derecha','patea','patea a una esquina','derecha','hola','patea al centro y luego derecha'):
            self.assertIsNone(interpret(text),text)
        self.assertEqual(interpret('patea a la esquina izquierda'),'unsupported:left_corner')
    def test_game_commands_preserved(self):
        for text,want in [('Iniciar partido','start'),('Patear cinco penales','five'),('Pausar partida','pause'),('Reanudar partida','resume'),('salir','stop')]:
            self.assertEqual(interpret(text),want)
    def test_one_selection_and_no_stale_next_shot(self):
        b,c=self.control();ticket=b.active_ticket();b.submit('Patea a la derecha');b.submit('Patea al centro');c.pump()
        self.assertEqual(c.pending_shot['action'],'right_inter_m080');self.assertEqual(sum(e['accepted'] for e in c.events),1)
        c.pending_shot=None;c.open_selection();b.submit('Patea al centro','voice',ticket=ticket);c.pump()
        self.assertIsNone(c.pending_shot);self.assertFalse(c.events[-1]['accepted'])
    def test_order_during_shot_cannot_cross_window(self):
        b,c=self.control();c.close_selection();c.phase='SHOOTING';b.submit('Patea al centro')
        c.phase='PREPARING';c.open_selection();c.pump();self.assertIsNone(c.pending_shot)
    def test_modes_safe_only(self):
        b,c=self.control();b.submit('Modo automatico');c.pump();self.assertEqual(c.mode,'auto')
        c.phase='SHOOTING';b.submit('Modo dirigido');c.pump();self.assertEqual(c.mode,'auto');self.assertFalse(c.events[-1]['accepted'])
    def test_pause_forbids_shot(self):
        b,c=self.control();c.paused=True;b.submit('Patea al centro');c.pump();self.assertIsNone(c.pending_shot)
    def test_owner_only(self):
        b,c=self.control();errors=[]
        def run():
            try:c.pump()
            except RuntimeError:errors.append(True)
        t=threading.Thread(target=run);t.start();t.join();self.assertEqual(errors,[True])
    def test_keeper_observation_schema_has_no_intent(self):
        self.assertEqual({f.name for f in fields(Observation)}, {'time_s','ball_position_w','ball_velocity_w','keeper_q','keeper_v','plane_x','rail_origin_y','rail_axis_y'})
    def test_reset_discards_old_ticket_and_commands(self):
        b,c=self.control();old=b.active_ticket();c.phase='FINISHED';b.submit('Reiniciar partido');b.submit('Patea al centro');c.pump()
        self.assertTrue(c.reset_requested);self.assertIsNone(b.active_ticket());self.assertIsNone(c.pending_shot)
        c.reset();c.phase='PREPARING';c.open_selection();b.submit('Patea al centro','voice',ticket=old);c.pump()
        self.assertFalse(c.events[-1]['accepted']);self.assertIsNone(c.pending_shot)
    def test_score_read_only_and_reset_forbidden_during_shot(self):
        b,c=self.control();c.phase='SHOOTING';c.score={'goals':2,'saves':1,'misses':0}
        b.submit('Mostrar marcador');b.submit('Reiniciar partido');c.pump()
        self.assertTrue(c.events[-2]['accepted']);self.assertIn('Goles 2',c.events[-2]['reason'])
        self.assertFalse(c.events[-1]['accepted']);self.assertFalse(c.reset_requested)

if __name__=='__main__':unittest.main()
