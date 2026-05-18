# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import math
import time
import random
from referee.game import PlayerColor, Coord, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

MAX_DEPTH      = 10      # max iterative-deepening depth
QDEPTH         = 2       # extra depth for captures after horizon
TIME_LIMIT_MAX = 10.0    # per-turn upper bound (seconds)
TIME_LIMIT_MIN = 0.5     # per-turn lower bound (seconds)
TT_SIZE        = 1 << 20  # transposition table slots (1M)

# TT flags:
# EXACT = true value,
# LOWER = we failed high (lower bound)
# UPPER = we failed low (upper bound)
EXACT = 0
LOWER = 1
UPPER = 2

# Zobrist hashing: fixed seed so it is the same every run
_rng = random.Random(0xDEADC0DE)
_ZOB = [[[_rng.getrandbits(64) for _ in range(13)]
          for _ in range(2)]
         for _ in range(64)]


# Hash the current board state by XORing all pieces' Zobrist keys together
def _hash_state(state: dict) -> int:
    h = 0
    for coord, cell in state.items():
        ci = 0 if cell.color == PlayerColor.RED else 1
        h ^= _ZOB[coord.r * 8 + coord.c][ci][min(cell.height, 12)]
    return h


# Manhattan distance between two coordinates
def _mhdist(a: Coord, b: Coord) -> int:
    return abs(a.r - b.r) + abs(a.c - b.c)


# How many cells a tower of this height can reach in all 4 directions (capped at 6)
def _cascade_reach(coord: Coord, height: int) -> int:
    h = min(height, 6)
    r, c = coord.r, coord.c
    return min(h, r) + min(h, 7 - r) + min(h, c) + min(h, 7 - c)


# Fixed-size transposition table using array-based storage for speed
class _TTable:
    # Each slot stores: key, value, depth, flag, best move
    __slots__ = ('_k', '_v', '_d', '_f', '_m')

    def __init__(self):
        n = TT_SIZE
        self._k = [0]     * n
        self._v = [0.0]   * n
        self._d = [-1]    * n
        self._f = [EXACT] * n
        self._m = [None]  * n

    # Look up a position -> returns (val, depth, flag, move) or None if not found
    def probe(self, key: int):
        i = key & (TT_SIZE - 1)
        if self._k[i] == key and self._d[i] >= 0:
            return self._v[i], self._d[i], self._f[i], self._m[i]
        return None

    # Save a position —> only overwrite if new result is from a deeper search
    def store(self, key: int, val: float, depth: int, flag: int, move):
        i = key & (TT_SIZE - 1)
        if self._d[i] <= depth:
            self._k[i] = key
            self._v[i] = val
            self._d[i] = depth
            self._f[i] = flag
            self._m[i] = move


class Agent:
    def __init__(self, color: PlayerColor, **referee: dict):
        self._color = color
        self._opp   = color.opponent
        self._board = Board()
        self._tt    = _TTable()                                          # transposition table
        self._killers    = [[None, None] for _ in range(MAX_DEPTH + QDEPTH + 2)]  # best cutoff moves per depth
        self._history    = {}                                            # history heuristic scores
        self._pos_hist   = []                                            # recent board hashes for repetition detection
        self._start_t    = 0.0
        self._time_limit = TIME_LIMIT_MAX
        self._turns_played = 0

    def action(self, **referee: dict) -> Action:
        # Smart placement using placement evaluation
        if self._board.phase == GamePhase.PLACEMENT:
            return self._best_placement()

        # Adaptive time management
        # spread remaining time evenly across turns left
        time_rem = referee.get('time_remaining', 60.0)
        self._turns_played += 1
        turns_left = max(10, 120 - self._turns_played)
        self._time_limit = max(TIME_LIMIT_MIN,
                               min(TIME_LIMIT_MAX, time_rem / turns_left))

        self._start_t = time.time()
        best       = None
        prev_score = 0

        # Iterative deepening
        # search depth 1 -> 2 -> 3 until time runs out
        for depth in range(1, MAX_DEPTH + 1):
            if self._timed_out():
                break

            # Aspiration windows -> narrow search window around previous score
            if depth <= 2:
                move, score = self._root(depth, -math.inf, math.inf)
            else:
                delta = 30
                move, score = self._root(depth, prev_score - delta, prev_score + delta)
                # Re-search with full window if score fell outside the aspiration range
                if (abs(score) < math.inf and
                        (score <= prev_score - delta or score >= prev_score + delta)):
                    move, score = self._root(depth, -math.inf, math.inf)

            if move is not None:
                best = move
            prev_score = score
            if abs(score) >= math.inf:
                break  # forced win or loss — no point searching deeper

        return best

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        self._board.apply_action(action)
        # Track recent board hashes to detect repeated positions (draw avoidance)
        zh = _hash_state(self._board._state)
        self._pos_hist.append(zh)
        if len(self._pos_hist) > 16:
            self._pos_hist.pop(0)

    # Score every candidate placement and return the best one
    def _best_placement(self) -> PlaceAction:
        best_score = -math.inf
        best_place = None
        for action in self._legal_placements():
            s = self._score_placement(action.coord)
            if s > best_score:
                best_score = s
                best_place = action
        return best_place

    # Score a candidate placement cell based on centre, cascade coverage, teammate support, and opponent pressure
    def _score_placement(self, coord: Coord) -> float:
        state  = self._board._state
        color  = self._color
        opp    = self._opp
        r, c   = coord.r, coord.c

        # Reward central positions
        center_score = -(abs(r - 3.5) + abs(c - 3.5))
        # Reward cells with more cascade reach
        coverage     = _cascade_reach(coord, 3)

        # Reward being close to our existing towers (easier to merge)
        support  = 0.0
        my_count = 0
        for tc, cell in state.items():
            if cell.color != color:
                continue
            my_count += 1
            d = _mhdist(tc, coord)
            if d == 1:
                support += 5.0
            elif d == 2:
                support += 1.5
            elif d <= 4:
                support += 0.5

        # Penalise placing too close to enemy towers
        opp_pressure = 0.0
        for tc, cell in state.items():
            if cell.color != opp:
                continue
            d = _mhdist(tc, coord)
            if d == 1:
                opp_pressure += 3.0
            elif d <= 3:
                opp_pressure += 1.0

        # force adjacency on piece 2 so turn-1 merge is available
        if my_count == 1:
            for tc, cell in state.items():
                if cell.color == color and _mhdist(tc, coord) == 1:
                    return 200.0

        return 2.0 * center_score + 0.8 * coverage + support + opp_pressure

    # Root search node: runs minimax on every move, returns best move and score
    def _root(self, depth: int, alpha: float, beta: float):
        best_move = None
        zh  = _hash_state(self._board._state)
        hit = self._tt.probe(zh)
        tt_move = hit[3] if hit else None

        moves = self._ordered_actions(self._color, 0, tt_move)

        for i, action in enumerate(moves):
            if i > 0 and self._timed_out():
                break
            self._board.apply_action(action)
            score = self._minimax(depth - 1, alpha, beta, is_max=False)
            self._board.undo_action()

            if best_move is None or score > alpha:
                alpha = score
                best_move = action

        self._tt.store(zh, alpha, depth, EXACT, best_move)
        return best_move, alpha

    def _minimax(self, depth: int, alpha: float, beta: float, is_max: bool) -> float:
        # Terminal state: win, loss, or draw
        if self._board.game_over:
            if self._board.winner_color == self._color:          return  math.inf
            if self._board.winner_color == self._color.opponent: return -math.inf
            return 0.0

        # Base case: drop into quiescence search instead of returning static eval
        if depth == 0:
            return self._quiescence(alpha, beta, QDEPTH, is_max)

        zh = _hash_state(self._board._state)

        # Repeated position — treat as draw to avoid cycles
        if self._pos_hist.count(zh) >= 2:
            return 0.0

        # Check TT — if we've seen this position at sufficient depth, reuse the result
        hit     = self._tt.probe(zh)
        tt_move = None
        if hit:
            tt_val, tt_depth, tt_flag, tt_move = hit
            if tt_depth >= depth:
                if tt_flag == EXACT:                     return tt_val
                if tt_flag == LOWER: alpha = max(alpha, tt_val)
                if tt_flag == UPPER: beta  = min(beta,  tt_val)
                if alpha >= beta:                        return tt_val

        color     = self._color if is_max else self._opp
        moves     = self._ordered_actions(color, depth, tt_move)
        orig_a    = alpha
        orig_b    = beta
        best      = -math.inf if is_max else math.inf
        best_move = tt_move

        for move_idx, action in enumerate(moves):
            self._board.apply_action(action)

            # Late Move Reductions: search later non-capture, non-killer moves at shallower depth
            reduce = (
                depth >= 3 and
                move_idx >= 4 and
                not isinstance(action, EatAction) and
                action not in (self._killers[depth][0], self._killers[depth][1])
            )
            val = self._minimax(depth - 1 - (1 if reduce else 0), alpha, beta, not is_max)

            # LMR re-search: if reduced search beat the bound, re-search at full depth
            if reduce and ((is_max and val > alpha) or (not is_max and val < beta)):
                val = self._minimax(depth - 1, alpha, beta, not is_max)

            self._board.undo_action()

            # Max (us): pick highest value
            if is_max:
                if val > best:
                    best      = val
                    best_move = action
                alpha = max(alpha, val)
            # Min (opp): pick lowest value
            else:
                if val < best:
                    best      = val
                    best_move = action
                beta = min(beta, val)

            # Pruning - no need for further search
            if beta <= alpha:
                self._store_killer(depth, action)
                self._update_history(action, depth)
                break

        if not moves:
            return self._evaluate()

        if   best <= orig_a: flag = UPPER
        elif best >= orig_b: flag = LOWER
        else:                flag = EXACT

        self._tt.store(zh, best, depth, flag, best_move)
        return best

    # Search captures only beyond the horizon to avoid mis-evaluating tactical positions
    def _quiescence(self, alpha: float, beta: float, qdepth: int, is_max: bool) -> float:
        stand_pat = self._evaluate()

        if qdepth == 0:
            return stand_pat

        # Max (us): pick highest value
        if is_max:
            if stand_pat >= beta:  return beta
            alpha = max(alpha, stand_pat)
            for action in self._captures(self._color):
                self._board.apply_action(action)
                score = self._quiescence(alpha, beta, qdepth - 1, False)
                self._board.undo_action()
                alpha = max(alpha, score)
                # Pruning - no need for further search
                if alpha >= beta:
                    break
            return alpha
        # Min (opp): pick lowest value
        else:
            if stand_pat <= alpha: return alpha
            beta = min(beta, stand_pat)
            for action in self._captures(self._opp):
                self._board.apply_action(action)
                score = self._quiescence(alpha, beta, qdepth - 1, True)
                self._board.undo_action()
                beta = min(beta, score)
                # Pruning - no need for further search
                if beta <= alpha:
                    break
            return beta

    # board evaluation -> returns +inf for win, -inf for loss
    def _evaluate(self) -> float:
        state = self._board._state
        color = self._color
        opp   = self._opp

        my_towers  = {c: v for c, v in state.items() if v.color == color and v.height > 0}
        opp_towers = {c: v for c, v in state.items() if v.color == opp   and v.height > 0}

        # game over
        if not my_towers:  return -math.inf
        if not opp_towers: return  math.inf

        my_h  = sum(v.height for v in my_towers.values())
        opp_h = sum(v.height for v in opp_towers.values())

        # token count gap is the main signal
        token_diff = (my_h - opp_h) * 2.0

        # towers over height 6 become liabilities
        height_penalty = 0.0
        for v in my_towers.values():
            if v.height > 6:
                height_penalty -= (v.height - 6) * 2.0
        for v in opp_towers.values():
            if v.height > 6:
                height_penalty += (v.height - 6) * 2.0

        # how much of the board each side can reach via cascade
        my_ctrl  = sum(_cascade_reach(mc, mv.height) for mc, mv in my_towers.items())
        opp_ctrl = sum(_cascade_reach(tc, tv.height) for tc, tv in opp_towers.items())
        control_diff = (my_ctrl - opp_ctrl) * 0.3

        # towers near edges have less room to move
        my_edge_val  = sum(min(mc.r, 7 - mc.r, mc.c, 7 - mc.c) for mc in my_towers) * 0.2
        opp_edge_val = sum(min(tc.r, 7 - tc.r, tc.c, 7 - tc.c) for tc in opp_towers) * 0.4
        edge_pressure = my_edge_val - opp_edge_val

        # score how well each enemy tower can be threatened
        my_threat = sum(
            max((min(mv.height, tv.height) / (_mhdist(mc, tc) + 1)
                 for mc, mv in my_towers.items() if mv.height >= tv.height),
                default=0.0)
            for tc, tv in opp_towers.items()
        )
        opp_threat = sum(
            max((min(tv.height, mv.height) / (_mhdist(mc, tc) + 1)
                 for tc, tv in opp_towers.items() if tv.height >= mv.height),
                default=0.0)
            for mc, mv in my_towers.items()
        )

        # match our towers to the best enemy target they can eat
        assigned = {}
        for tc, tv in opp_towers.items():
            best_q, best_mc = 0.0, None
            for mc, mv in my_towers.items():
                if mv.height >= tv.height and mv.height >= 3:
                    q = min(mv.height, tv.height) / (_mhdist(mc, tc) + 1)
                    if q > best_q:
                        best_q, best_mc = q, mc
            if best_mc is not None:
                assigned[tc] = best_mc
        pairing = len(set(assigned.values())) * 1.5

        # being in the same row/col within range is a cascade threat
        # closer to the edge means less room for the enemy to escape
        cascade_line_bonus = 0.0
        for mc, mv in my_towers.items():
            h = min(mv.height, 6)
            if h < 2:
                continue
            for tc, tv in opp_towers.items():
                if mc.r == tc.r or mc.c == tc.c:
                    d = _mhdist(mc, tc)
                    if 1 <= d <= h:
                        if mc.r == tc.r:
                            edge_in_dir = (7 - tc.c) if tc.c > mc.c else tc.c
                        else:
                            edge_in_dir = (7 - tc.r) if tc.r > mc.r else tc.r
                        edge_trap = max(0, 3 - edge_in_dir)
                        cascade_line_bonus += (1.0 + 0.5 * edge_trap) / (d + 1)
        for tc, tv in opp_towers.items():
            h = min(tv.height, 6)
            if h < 2:
                continue
            for mc, mv in my_towers.items():
                if tc.r == mc.r or tc.c == mc.c:
                    d = _mhdist(tc, mc)
                    if 1 <= d <= h:
                        cascade_line_bonus -= 0.5 / (d + 1)

        # extra points if multiple towers can hit the same enemy
        coord_bonus = 0.0
        for tc, tv in opp_towers.items():
            attackers = 0
            for mc, mv in my_towers.items():
                h = min(mv.height, 6)
                if mv.height >= tv.height and _mhdist(mc, tc) == 1:
                    attackers += 1
                elif h >= 2 and (mc.r == tc.r or mc.c == tc.c):
                    if 1 <= _mhdist(mc, tc) <= h:
                        attackers += 1
            if attackers >= 2:
                coord_bonus += min(attackers - 1, 2) * 0.8

        return (token_diff
                + height_penalty
                + control_diff
                + edge_pressure
                + (my_threat - opp_threat) * 1.5
                + pairing
                + cascade_line_bonus * 0.6
                + coord_bonus
                + random.uniform(-0.05, 0.05))

    # Order moves: TT move first, then eats, killers, cascades, moves (sorted by history score)
    def _ordered_actions(self, color: PlayerColor, depth: int, tt_move) -> list:
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

        all_actions = eats + cascades + moves
        if tt_move is not None and tt_move not in all_actions:
            tt_move = None

        killers = [k for k in self._killers[depth] if k is not None]
        non_tt  = lambda lst: [a for a in lst if a != tt_move]

        def hist_score(a):
            return self._history.get(self._action_key(a), 0)

        nc = [a for a in non_tt(cascades) if a not in killers]
        nm = [a for a in non_tt(moves)    if a not in killers]
        nc.sort(key=hist_score, reverse=True)
        nm.sort(key=hist_score, reverse=True)

        ordered = []
        if tt_move is not None:
            ordered.append(tt_move)
        ordered += non_tt(eats)
        ordered += [a for a in killers if a != tt_move and (a in cascades or a in moves)]
        ordered += nc
        ordered += nm
        return ordered

    # Return only capture moves (eats and cascades that hit an enemy) for quiescence search
    def _captures(self, color: PlayerColor) -> list:
        state  = self._board._state
        opp    = color.opponent
        result = []
        for coord, cell in state.items():
            if cell.color != color:
                continue
            for d in CARDINAL_DIRECTIONS:
                try:
                    des = coord + d
                    dst = self._board[des]
                    if dst.color == opp and cell.height >= dst.height:
                        result.append(EatAction(coord, d))
                except ValueError:
                    pass
            if cell.height >= 2:
                for d in CARDINAL_DIRECTIONS:
                    cur = coord
                    for _ in range(cell.height):
                        try:
                            cur = cur + d
                            if cur in state and state[cur].color == opp:
                                result.append(CascadeAction(coord, d))
                                break
                        except ValueError:
                            break
        return result

    # Keep the 2 most recent cutoff moves at this depth
    def _store_killer(self, depth: int, action: Action):
        if action != self._killers[depth][0]:
            self._killers[depth][1] = self._killers[depth][0]
            self._killers[depth][0] = action

    # Unique key for a move used by the history table
    def _action_key(self, action: Action):
        return (type(action).__name__,
                getattr(action, 'coord', None),
                getattr(action, 'direction', None))

    # Reward moves that caused cutoffs — deeper cutoffs score higher
    def _update_history(self, action: Action, depth: int):
        key = self._action_key(action)
        self._history[key] = self._history.get(key, 0) + (1 << depth)

    # Return True if we've exceeded our time budget for this turn
    def _timed_out(self) -> bool:
        return time.time() - self._start_t > self._time_limit

    # Finding all the legal placement
    def _legal_placements(self) -> list:
        actions = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                coord = Coord(r, c)
                if not self._board[coord].is_empty:
                    continue

                # First placement has no restriction since the board is empty
                if self._board._placement_count > 0 and self._adj_opp(coord):
                    continue
                actions.append(PlaceAction(coord))
        return actions

    # Check if any opponent piece is adjacent to the current coord
    def _adj_opp(self, coord: Coord) -> bool:
        for d in CARDINAL_DIRECTIONS:
            try:
                if self._board[coord + d].color == self._opp:
                    return True
            except ValueError:
                pass
        return False
