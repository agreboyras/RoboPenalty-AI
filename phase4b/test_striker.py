"""Behavioral tests: causal updates, context separation, utility and replay."""
from dataclasses import replace
import inspect
import json
import math
import unittest
from striker_agent import ACTIONS, InitialObservation, StrikerAgent

def observation(**changes):
    return replace(InitialObservation('long','agent',0.,0.,0.,.1535,.115,
                    (-1.,0.,.115),(-2.,0.,.793)),**changes)

def calibration(distance='long'):
    return {a:{'kind':'historical_calibration','distance':distance,'plane_y_w_m':y,
               'source':'synthetic_test_fixture'}
            for a,y in zip(ACTIONS,(-.1085,.2954,-.4828))}

class StrikerTests(unittest.TestCase):
    def test_neutral_prior_is_not_measured_data(self):
        d=StrikerAgent().choose(observation(),calibration(),'a')
        for c in d['candidates'].values():
            self.assertEqual(c['n_observed'],0)
            self.assertIsNone(c['empirical_goal_fraction'])
            self.assertAlmostEqual(c['estimated_p_goal'],1/3)
            self.assertAlmostEqual(c['estimated_p_miss'],1/3)

    def test_select_does_not_add_outcomes(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a')
        self.assertEqual(a.state['history'],[])
        self.assertEqual(sum(sum(x.values()) for c in a.state['contexts'].values() for x in c.values()),0)

    def test_feedback_increments_exactly_selected_action(self):
        a=StrikerAgent(); d=a.choose(observation(),calibration(),'a')
        a.observe('a','goal')
        c=a.state['contexts'][d['context']]
        self.assertEqual(c[d['action']]['goal'],1)
        self.assertEqual(sum(sum(x.values()) for x in c.values()),1)

    def test_no_second_choice_without_result(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a')
        with self.assertRaises(RuntimeError): a.choose(observation(),calibration(),'b')

    def test_no_double_feedback(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a'); a.observe('a','save')
        with self.assertRaises(RuntimeError): a.observe('a','goal')

    def test_mismatched_feedback_rejected(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a')
        with self.assertRaises(RuntimeError): a.observe('future','goal')
        self.assertIsNotNone(a.state['pending'])

    def test_unresolved_not_relabelled_miss(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a')
        with self.assertRaises(ValueError): a.observe('a','unresolved')
        self.assertEqual(a.state['history'],[])

    def test_three_initial_trials_explore_all_actions(self):
        a=StrikerAgent(); actions=[]
        for i in range(3):
            d=a.choose(observation(),calibration(),str(i)); actions.append(d['action']); a.observe(str(i),'save')
        self.assertEqual(set(actions),set(ACTIONS))

    def test_learns_successful_action_from_observed_feedback(self):
        a=StrikerAgent()
        for i in range(3):
            d=a.choose(observation(),calibration(),str(i))
            a.observe(str(i),'goal' if d['action']=='right' else 'save')
        d=a.choose(observation(),calibration(),'next')
        self.assertEqual(d['action'],'right')
        self.assertEqual(d['reason'],'maximize_updated_utility')

    def test_miss_is_penalized_more_than_save(self):
        values=[]
        for outcome in ('save','miss'):
            a=StrikerAgent(); a.choose(observation(),calibration(),'a','fixed',fixed_action='right')
            a.observe('a',outcome)
            values.append(a.choose(observation(),calibration(),'b')['candidates']['right']['base_utility'])
        self.assertGreater(values[0],values[1])

    def test_fixed_ignores_history_for_selection(self):
        a=StrikerAgent()
        for i in range(5):
            d=a.choose(observation(),calibration(),str(i),'fixed',fixed_action='center')
            self.assertEqual(d['action'],'center'); a.observe(str(i),'save')

    def test_seeded_random_replays_sequence(self):
        sequences=[]
        for _ in range(2):
            a=StrikerAgent(); seq=[]
            for i in range(12):
                d=a.choose(observation(),calibration(),str(i),'random',seed=2026)
                seq.append(d['action']); a.observe(str(i),'goal')
            sequences.append(seq)
        self.assertEqual(*sequences)
        self.assertEqual(set(sequences[0]),set(ACTIONS))

    def test_contexts_do_not_share_opponent_results(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a'); a.observe('a','goal')
        d=a.choose(observation(opponent='fixed'),calibration(),'b')
        self.assertTrue(all(c['n_observed']==0 for c in d['candidates'].values()))

    def test_contexts_do_not_share_distance_results(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a'); a.observe('a','goal')
        d=a.choose(observation(distance='original'),calibration('original'),'b')
        self.assertTrue(all(c['n_observed']==0 for c in d['candidates'].values()))

    def test_coverage_responds_to_keeper_position(self):
        center=StrikerAgent().choose(observation(),calibration(),'a')
        right=StrikerAgent().choose(observation(keeper_y_w=-.48),calibration(),'a')
        self.assertGreater(right['candidates']['right']['coverage_proximity_heuristic'],center['candidates']['right']['coverage_proximity_heuristic'])

    def test_wrong_calibration_distance_rejected(self):
        with self.assertRaises(ValueError): StrikerAgent().choose(observation(),calibration('original'),'a')

    def test_only_initial_finite_observations(self):
        for bad in (observation(time_sim_s=1),observation(keeper_y_w=math.nan)):
            with self.assertRaises(ValueError): StrikerAgent().choose(bad,calibration(),'a')

    def test_unvalidated_actions_rejected(self):
        with self.assertRaises(ValueError):
            StrikerAgent().choose(observation(available_actions=('new_shot',)),calibration(),'a')

    def test_persistence_reproduces_next_decision(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a'); a.observe('a','goal')
        b=StrikerAgent(json.loads(json.dumps(a.snapshot())))
        self.assertEqual(a.choose(observation(),calibration(),'b'),b.choose(observation(),calibration(),'b'))

    def test_completed_id_cannot_be_reused(self):
        a=StrikerAgent(); a.choose(observation(),calibration(),'a'); a.observe('a','goal')
        with self.assertRaises(ValueError): a.choose(observation(),calibration(),'a')

    def test_snapshot_is_independent(self):
        a=StrikerAgent(); s=a.snapshot(); s['history'].append('future')
        self.assertEqual(a.state['history'],[])

    def test_utility_components_sum_to_logged_value(self):
        d=StrikerAgent().choose(observation(),calibration(),'a')
        for c in d['candidates'].values():
            self.assertAlmostEqual(c['utility'],c['estimated_p_goal']-.5*c['estimated_p_miss']-.1*c['coverage_proximity_heuristic']+c['exploration_bonus'])

    def test_selector_api_does_not_accept_current_trajectory_or_result(self):
        params=inspect.signature(StrikerAgent.choose).parameters
        self.assertNotIn('outcome',params); self.assertNotIn('trajectory',params)

if __name__=='__main__': unittest.main(verbosity=2)
