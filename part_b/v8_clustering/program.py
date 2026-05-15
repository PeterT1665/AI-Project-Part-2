# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent
# v8: Monte Carlo Tree Search (MCTS)
#   - UCB1 selection (exploration–exploitation tradeoff)
#   - Minimax backpropagation (alternating perspectives)
#   - v7's proven eval at leaf nodes (greedy-chain attack cost + material + power)
#   - Seeded per-agent RNG to avoid cross-module random-state interference

import math
import time
import random
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

# ── MCTS parameters ───────────────────────────────────────────────────────────
C_UCB          = 1.41   # UCB1 exploration constant (sqrt(2) is theoretical optimum)
ROLLOUT_MOVES  = 3      # random moves before static eval in each simulation
TIME_LIMIT_MAX = 5.0
TIME_LIMIT_MIN = 0.5

# Terminal rewards — much larger than any eval score so they always dominate
WIN_SCORE  =  1000.0
LOSS_SCORE = -1000.0
DRAW_SCORE =     0.0


# ── MCTS node ─────────────────────────────────────────────────────────────────
class _Node:
    """One node in the MCTS tree.

    `is_max` is True when it is the agent's (self._color's) turn at this node.
    `total`  accumulates scores from self._color's perspective so
             backpropagation never needs to negate.
    """
    __slots__ = ('action', 'parent', 'children', 'visits', 'total',
                 'untried', 'is_max')

    def __init__(self, action, parent, is_max: bool):
        self.action   = action    # action that led here (None for root)
        self.parent   = parent
        self.children = []
        self.visits   = 0
        self.total    = 0.0
        self.untried  = None      # populated lazily on first expansion
        self.is_max   = is_max    # whose turn at this node


class Agent:
    def __init__(self, color: PlayerColor, **referee: dict):
        self._color        = color
        self._opp          = color.opponent
        self._board        = Board()
        self._start_t      = 0.0
        self._time_limit   = TIME_LIMIT_MAX
        self._turns_played = 0
        # Per-agent RNG: seeded by color so RED/BLUE noise is independent
        self._rng = random.Random(0 if color == PlayerColor.RED else 1)

        match color:

    # ── Public interface ──────────────────────────────────────────────────────

    def action(self, **referee: dict) -> Action:
        if self._board.phase == GamePhase.PLACEMENT:
            return self._best_placement()

        time_rem = referee.get('time_remaining', 60.0)
        self._turns_played += 1
        turns_left = max(20, 150 - self._turns_played)
        self._time_limit = max(TIME_LIMIT_MIN,
                               min(TIME_LIMIT_MAX, time_rem / turns_left * 0.85))
        self._start_t = time.time()

        return self._mcts_search()

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        self._board.apply_action(action)

    # ── MCTS main loop ────────────────────────────────────────────────────────

    def _mcts_search(self) -> Action:
        root = _Node(action=None, parent=None, is_max=True)

        while time.time() - self._start_t < self._time_limit:
            # ── 1. SELECT: walk tree via UCB1 until leaf ──────────────────────
            node, path_depth = self._select(root)

            # ── 2. EXPAND: add one untried child ─────────────────────────────
            if not self._board.game_over:
                if node.untried is None:
                    active = self._color if node.is_max else self._opp
                    node.untried = self._legal_actions(active)
                if node.untried:
                    act   = node.untried.pop()
                    child = _Node(act, node, is_max=not node.is_max)
                    node.children.append(child)
                    self._board.apply_action(act)
                    path_depth += 1
                    node = child

            # ── 3. SIMULATE: random rollout → static eval ─────────────────────
            score = self._simulate()

            # ── 4. BACKPROPAGATE + UNDO ───────────────────────────────────────
            cur = node
            while cur is not None:
                cur.visits += 1
                cur.total  += score
                cur = cur.parent
            for _ in range(path_depth):
                self._board.undo_action()

        if not root.children:
            acts = self._legal_actions(self._color)
            return acts[0] if acts else None

        # Robust selection: choose child with most visits
        return max(root.children, key=lambda c: c.visits).action

    # ── Selection ─────────────────────────────────────────────────────────────

    def _select(self, root: _Node):
        """Traverse tree using UCB1 until we reach a node with untried actions
        (or a terminal state).  Applies actions to self._board along the way."""
        node  = root
        depth = 0
        while (not self._board.game_over
               and node.children
               and node.untried is not None
               and not node.untried):
            child = max(node.children,
                        key=lambda c, n=node: self._ucb1(c, n))
            self._board.apply_action(child.action)
            depth += 1
            node  = child
        return node, depth

    def _ucb1(self, child: _Node, parent: _Node) -> float:
        """UCB1 value of `child` as seen by the player to move at `parent`."""
        if child.visits == 0:
            return math.inf
        # exploitation: score from self._color's perspective
        exploit = child.total / child.visits
        # opponent (is_max=False) wants to MINIMISE our score
        if not parent.is_max:
            exploit = -exploit
        # exploration bonus
        explore = C_UCB * math.sqrt(math.log(parent.visits + 1) / child.visits)
        return exploit + explore

    # ── Simulation ────────────────────────────────────────────────────────────

    def _simulate(self) -> float:
        """Play ROLLOUT_MOVES random moves from the current position,
        then return the static eval score (from self._color's perspective)."""
        applied = []
        turn    = True   # True = self._color to move, False = opponent
        for _ in range(ROLLOUT_MOVES):
            if self._board.game_over:
                break
            color = self._color if turn else self._opp
            acts  = self._legal_actions(color)
            if not acts:
                break
            a = self._rng.choice(acts)
            self._board.apply_action(a)
            applied.append(a)
            turn = not turn

        if self._board.game_over:
            score = self._terminal_score()
        else:
            score = self._evaluate()

        for _ in applied:
            self._board.undo_action()
        return score

    def _terminal_score(self) -> float:
        w = self._board.winner_color
        if w == self._color:          return WIN_SCORE
        if w == self._color.opponent: return LOSS_SCORE
        return DRAW_SCORE

    # ── Evaluation (v7 proven formula) ────────────────────────────────────────

    def _evaluate(self) -> float:
        state = self._board._state
        color = self._color
        opp   = self._opp

        my_towers  = {c: v for c, v in state.items() if v.color == color and v.height > 0}
        opp_towers = {c: v for c, v in state.items() if v.color == opp   and v.height > 0}

        if not my_towers:  return LOSS_SCORE / 2
        if not opp_towers: return WIN_SCORE  / 2

        my_h  = sum(v.height for v in my_towers.values())
        opp_h = sum(v.height for v in opp_towers.values())

        my_attack  = self._attack_cost(my_towers, opp_towers)
        opp_attack = self._attack_cost(opp_towers, my_towers)

        my_ap  = sum(1 for av in my_towers.values()
                       for tv in opp_towers.values() if av.height >= tv.height)
        opp_ap = sum(1 for tv in opp_towers.values()
                       for av in my_towers.values() if tv.height >= av.height)

        return (opp_attack - my_attack) + (my_h - opp_h) + (my_ap - opp_ap)

    def _attack_cost(self, attackers: dict, targets: dict) -> float:
        """Greedy-chain attack cost — mirrors v6/v7."""
        attackers = dict(attackers)
        total = 0
        for tc, tv in targets.items():
            if not attackers:
                break
            min_dist = math.inf
            best_ac  = None
            for ac, av in attackers.items():
                if av.height < tv.height:
                    continue
                d = _mhdist(ac, tc)
                if d < min_dist:
                    min_dist = d
                    best_ac  = ac
            if best_ac is None:
                total += 100
                continue
            total += -(-min_dist // attackers[best_ac].height)
            attackers[tc] = attackers.pop(best_ac)
        return total

    # ── Move generation ───────────────────────────────────────────────────────

    def _legal_actions(self, color: PlayerColor) -> list:
        """Generate all legal actions ordered by tactical priority
        (eats → cascades → moves) — gives MCTS a good prior ordering."""
        state = self._board._state
        opp   = color.opponent
        eats, cascades, moves = [], [], []

        for coord, cell in state.items():
            if cell.color != color:
                continue
            for d in CARDINAL_DIRECTIONS:
                try:
                    des = coord + d
                    dst = self._board[des]
                    if dst.is_empty or dst.color == color:
                        moves.append(MoveAction(coord, d))
                    elif dst.color == opp and cell.height >= dst.height:
                        eats.append(EatAction(coord, d))
                except ValueError:
                    pass
            if cell.height >= 2:
                for d in CARDINAL_DIRECTIONS:
                    cascades.append(CascadeAction(coord, d))

        # Shuffle within each group so rollouts explore diverse lines
        self._rng.shuffle(eats)
        self._rng.shuffle(cascades)
        self._rng.shuffle(moves)
        # Pop from the end → eats explored first, then cascades, then moves
        return moves + cascades + eats

    # ── Placement phase ───────────────────────────────────────────────────────

    def _best_placement(self) -> PlaceAction:
        best_score = -math.inf
        best_place = None
        for action in self._legal_placements():
            s = self._score_placement(action.coord)
            if s > best_score:
                best_score = s
                best_place = action
        return best_place

    def _score_placement(self, coord: Coord) -> float:
        state      = self._board._state
        color      = self._color
        team_count = sum(1 for c in state.values() if c.color == color)

        center = -(abs(coord.r - 3.5) + abs(coord.c - 3.5))

        spread = math.inf
        for tc, cell in state.items():
            if cell.color == color:
                spread = min(spread, _mhdist(tc, coord))
        if spread == math.inf:
            spread = 0

        cascade = 0
        for d in CARDINAL_DIRECTIONS:
            if   d == Direction.Right: cnt = 7 - coord.c
            elif d == Direction.Down:  cnt = 7 - coord.r
            elif d == Direction.Left:  cnt = coord.c
            else:                      cnt = coord.r
            if cnt <= 3:
                cascade += cnt

        if team_count == 1:
            for tc, cell in state.items():
                if cell.color == color and _mhdist(tc, coord) == 1:
                    return center + 100

        return 2 * center + spread + 1.5 * cascade

    def _legal_placements(self) -> list:
        actions = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                coord = Coord(r, c)
                if not self._board[coord].is_empty:
                    continue
                if self._board._placement_count > 0 and self._adj_opp(coord):
                    continue
                actions.append(PlaceAction(coord))
        return actions

    def _adj_opp(self, coord: Coord) -> bool:
        for d in CARDINAL_DIRECTIONS:
            try:
                if self._board[coord + d].color == self._opp:
                    return True
            except ValueError:
                pass
        return False


# ── Module-level helper ───────────────────────────────────────────────────────

def _mhdist(a: Coord, b: Coord) -> int:
    return abs(a.r - b.r) + abs(a.c - b.c)
