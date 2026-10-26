"""Causal, interpretable statistical action selection. Standard library only."""
from dataclasses import dataclass, asdict
import copy
import math
import random

ACTIONS = ('center', 'left', 'right')
OUTCOMES = ('goal', 'save', 'miss')


@dataclass(frozen=True)
class InitialObservation:
    distance: str
    opponent: str
    keeper_y_w: float
    keeper_q_m: float
    keeper_v_mps: float
    keeper_half_span_m: float
    ball_radius_m: float
    ball_position_w: tuple
    shooter_position_w: tuple
    available_actions: tuple = ACTIONS
    time_sim_s: float = 0.0

    def context(self):
        if self.distance not in ('original', 'long') or self.opponent not in ('fixed', 'agent'):
            raise ValueError('Unknown initial scenario')
        numbers = (self.keeper_y_w, self.keeper_q_m, self.keeper_v_mps,
                   self.keeper_half_span_m, self.ball_radius_m, self.time_sim_s,
                   *self.ball_position_w, *self.shooter_position_w)
        if not all(math.isfinite(x) for x in numbers) or self.time_sim_s != 0:
            raise ValueError('Finite pre-shot initial observations required')
        if self.keeper_half_span_m <= 0 or self.ball_radius_m <= 0:
            raise ValueError('Invalid physical dimensions')
        if tuple(self.available_actions) != ACTIONS:
            raise ValueError('Only the three calibrated actions are available')
        # An explicit coarse context, not a claim of generalization between bins.
        return f'{self.distance}/{self.opponent}/keeper_y_bin_{round(self.keeper_y_w/0.25)}'


class StrikerAgent:
    """Dirichlet outcome estimates + geometric heuristic + controlled exploration.

    Utility weights and priors are design assumptions, never measured probabilities.
    A pending transaction blocks further selection until feedback is committed.
    """
    def __init__(self, state=None):
        self.state = copy.deepcopy(state) if state is not None else {
            'version': 1, 'contexts': {}, 'history': [], 'pending': None}
        if self.state.get('version') != 1:
            raise ValueError('Unsupported statistics version')

    def snapshot(self):
        return copy.deepcopy(self.state)

    def choose(self, observation, calibration, episode_id, strategy='utility', seed=2026,
               fixed_action='center'):
        if self.state['pending'] is not None:
            raise RuntimeError('Feedback required before choosing another shot')
        if any(x['episode_id'] == episode_id for x in self.state['history']):
            raise ValueError('Episode already completed')
        if strategy not in ('fixed','random','utility') or fixed_action not in ACTIONS:
            raise ValueError('Unsupported strategy/action')
        context = observation.context()
        stats = self.state['contexts'].setdefault(context,
            {a:{o:0 for o in OUTCOMES} for a in ACTIONS})
        total = sum(sum(c.values()) for c in stats.values())
        rng = random.Random(seed + total)
        candidates = {}
        for action in ACTIONS:
            c = stats[action]
            n = sum(c.values())
            historical = calibration[action]
            if historical['distance'] != observation.distance or historical['kind'] != 'historical_calibration':
                raise ValueError('Calibration must match the initial distance')
            y = float(historical['plane_y_w_m'])
            if not math.isfinite(y):
                raise ValueError('Invalid historical calibration')
            span = observation.keeper_half_span_m + observation.ball_radius_m
            coverage = max(0., 1. - abs(y-observation.keeper_y_w)/span)
            p_goal, p_miss = (c['goal']+1)/(n+3), (c['miss']+1)/(n+3)
            bonus = 0.15*math.sqrt(math.log(1+total)/(1+n))
            base = p_goal - 0.5*p_miss - 0.1*coverage
            candidates[action] = {
                'counts_observed':dict(c), 'n_observed':n,
                'empirical_goal_fraction':c['goal']/n if n else None,
                'estimated_p_goal':p_goal, 'estimated_p_miss':p_miss,
                'prior_pseudocount_each_outcome':1,
                'historical_plane_y_w_m':y,
                'coverage_proximity_heuristic':coverage,
                'base_utility':base, 'exploration_bonus':bonus, 'utility':base+bonus,
                'calibration_source':historical['source'], 'calibration_kind':historical['kind']}
        if strategy == 'fixed':
            action, reason = fixed_action, 'fixed_action_predeclared'
        elif strategy == 'random':
            action, reason = rng.choice(ACTIONS), 'uniform_seeded_random'
        else:
            pool = [a for a in ACTIONS if candidates[a]['n_observed']==0]
            reason = 'explore_untried_action' if pool else 'maximize_updated_utility'
            pool = pool or list(ACTIONS)
            best = max(candidates[a]['utility'] for a in pool)
            action = rng.choice([a for a in pool if abs(candidates[a]['utility']-best)<1e-12])
        decision = {'episode_id':episode_id, 'context':context, 'strategy':strategy,
                    'seed':seed, 'seed_for_this_selection':seed+total,
                    'observation':asdict(observation), 'candidates':candidates,
                    'action':action, 'reason':reason, 'completed_episodes_before':total,
                    'utility_formula':'p_goal - 0.5*p_miss - 0.1*coverage + 0.15*sqrt(log(1+N)/(1+n))'}
        self.state['pending'] = {'episode_id':episode_id, 'context':context, 'action':action}
        return decision

    def observe(self, episode_id, outcome):
        pending = self.state['pending']
        if pending is None or pending['episode_id'] != episode_id:
            raise RuntimeError('Feedback must match exactly one pending episode')
        if outcome not in OUTCOMES:
            raise ValueError('Invalid/unresolved results do not become learning labels')
        counts = self.state['contexts'][pending['context']][pending['action']]
        before = dict(counts)
        counts[outcome] += 1
        event = {**pending, 'outcome':outcome, 'counts_before':before,
                 'counts_after':dict(counts), 'learning_phase':'after_physical_episode'}
        self.state['history'].append(event)
        self.state['pending'] = None
        return copy.deepcopy(event)
