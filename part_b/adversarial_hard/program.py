# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import math
import time
import random
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

MAX_DEPTH      = 8
QDEPTH         = 2
TIME_LIMIT_MAX = 5.0   # hard ceiling per move (seconds)
TIME_LIMIT_MIN = 0.5   # floor so we always do at least 1 full depth
TT_SIZE        = 1 << 18   # 256 K slots

EXACT = 0
LOWER = 1
UPPER = 2

# Zobrist table — seeded so it's the same every run
_rng = random.Random(0xDEADC0DE)
_ZOB = [[[_rng.getrandbits(64) for _ in range(13)]
          for _ in range(2)]
         for _ in range(64)]

def _hash_state(state: dict) -> int:
    h = 0
    for coord, cell in state.items():
        ci = 0 if cell.color == PlayerColor.RED else 1
        h ^= _ZOB[coord.r * 8 + coord.c][ci][min(cell.height, 12)]
    return h


class _TTable:
    __slots__ = ('_k', '_v', '_d', '_f', '_m')

    def __init__(self):
        n = TT_SIZE
        self._k = [0]     * n
        self._v = [0.0]   * n
        self._d = [-1]    * n
        self._f = [EXACT] * n
        self._m = [None]  * n

    def probe(self, key: int):
        i = key & (TT_SIZE - 1)
        if self._k[i] == key and self._d[i] >= 0:
            return self._v[i], self._d[i], self._f[i], self._m[i]
        return None

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
        self._opp = color.opponent
        self._board = Board()
        self._tt = _TTable()
        self._killers = [[None, None] for _ in range(MAX_DEPTH + QDEPTH + 2)]
        self._history = {}   # action_key -> cutoff score
        self._pos_hist = []  # Zobrist hashes of real-game positions (last 16)
        self._start_t = 0.0
        self._time_limit = TIME_LIMIT_MAX
        self._turns_played = 0


    def action(self, **referee: dict) -> Action:
        if self._board.phase == GamePhase.PLACEMENT:
            return self._best_placement()

        # Spread remaining time evenly across remaining turns
        time_rem = referee.get('time_remaining', 60.0)
        self._turns_played += 1
        turns_left = max(20, 150 - self._turns_played)
        self._time_limit = max(TIME_LIMIT_MIN,
                               min(TIME_LIMIT_MAX, time_rem / turns_left * 0.85))

        self._start_t = time.time()
        best = None
        prev_score = 0

        # Iterative deepening with aspiration windows
        for depth in range(1, MAX_DEPTH + 1):
            if self._timed_out():
                break

            if depth <= 2:
                move, score = self._root(depth, -math.inf, math.inf)
            else:
                delta = 30
                move, score = self._root(depth, prev_score - delta, prev_score + delta)
                # Re-search with full window if result fell outside aspiration window
                if (abs(score) < math.inf and
                        (score <= prev_score - delta or score >= prev_score + delta)):
                    move, score = self._root(depth, -math.inf, math.inf)

            if move is not None:
                best = move
            prev_score = score
            if abs(score) >= math.inf:
                break   # forced win or loss — no point searching deeper

        return best

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        self._board.apply_action(action)
        zh = _hash_state(self._board._state)
        self._pos_hist.append(zh)
        if len(self._pos_hist) > 16:
            self._pos_hist.pop(0)

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
        state = self._board._state
        color = self._color
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

        # 2nd tower: place adjacent to 1st to enable immediate merge to height-6
        if team_count == 1:
            for tc, cell in state.items():
                if cell.color == color and _mhdist(tc, coord) == 1:
                    return center + 100

        return 2 * center + spread + 1.5 * cascade

    def _root(self, depth: int, alpha: float, beta: float):
        best_move = None
        zh = _hash_state(self._board._state)

        tt_move = None
        hit = self._tt.probe(zh)
        if hit:
            tt_move = hit[3]

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
        if self._board.game_over:
            if self._board.winner_color == self._color:          return  math.inf
            if self._board.winner_color == self._color.opponent: return -math.inf
            return 0.0

        if depth == 0:
            return self._quiescence(alpha, beta, QDEPTH, is_max)

        zh = _hash_state(self._board._state)

        # Positions seen 2+ times in real game: treat as draw to avoid repetition
        if self._pos_hist.count(zh) >= 2:
            return 0.0

        hit = self._tt.probe(zh)
        tt_move = None
        if hit:
            tt_val, tt_depth, tt_flag, tt_move = hit
            if tt_depth >= depth:
                if tt_flag == EXACT:                     return tt_val
                if tt_flag == LOWER: alpha = max(alpha, tt_val)
                if tt_flag == UPPER: beta  = min(beta,  tt_val)
                if alpha >= beta:                        return tt_val

        color = self._color if is_max else self._opp
        moves = self._ordered_actions(color, depth, tt_move)
        orig_a = alpha
        orig_b = beta
        best = -math.inf if is_max else math.inf
        best_move = tt_move

        for move_idx, action in enumerate(moves):
            self._board.apply_action(action)

            # Late move reductions: search quiet late moves at shallower depth
            reduce = (
                depth >= 3 and
                move_idx >= 4 and
                not isinstance(action, EatAction) and
                action not in (self._killers[depth][0], self._killers[depth][1])
            )
            val = self._minimax(depth - 1 - (1 if reduce else 0), alpha, beta, not is_max)

            # Re-search at full depth if the reduced result looks promising
            if reduce:
                if (is_max and val > alpha) or (not is_max and val < beta):
                    val = self._minimax(depth - 1, alpha, beta, not is_max)

            self._board.undo_action()

            if is_max:
                if val > best:
                    best = val
                    best_move = action
                alpha = max(alpha, val)
            else:
                if val < best:
                    best = val
                    best_move = action
                beta = min(beta, val)

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

    def _quiescence(self, alpha: float, beta: float, qdepth: int, is_max: bool) -> float:
        stand_pat = self._evaluate()

        if qdepth == 0:
            return stand_pat

        if is_max:
            if stand_pat >= beta:  return beta
            alpha = max(alpha, stand_pat)
            for action in self._captures(self._color):
                self._board.apply_action(action)
                score = self._quiescence(alpha, beta, qdepth - 1, False)
                self._board.undo_action()
                alpha = max(alpha, score)
                if alpha >= beta:
                    break
            return alpha
        else:
            if stand_pat <= alpha: return alpha
            beta = min(beta, stand_pat)
            for action in self._captures(self._opp):
                self._board.apply_action(action)
                score = self._quiescence(alpha, beta, qdepth - 1, True)
                self._board.undo_action()
                beta = min(beta, score)
                if beta <= alpha:
                    break
            return beta

    def _evaluate(self) -> float:
        state = self._board._state
        color = self._color
        opp = self._opp

        my_towers  = {c: v for c, v in state.items() if v.color == color and v.height > 0}
        opp_towers = {c: v for c, v in state.items() if v.color == opp   and v.height > 0}

        if not my_towers:  return -math.inf
        if not opp_towers: return  math.inf

        my_h  = sum(v.height for v in my_towers.values())
        opp_h = sum(v.height for v in opp_towers.values())

        # Token count — endgame win condition, highest weight
        token_diff = (my_h - opp_h) * 2.0

        # Threat quality: for each enemy find our best eligible attacker scored as
        # height/(dist+1) — tall towers close to weak enemies score highest.
        # This gives a smooth gradient for distance AND height in one term,
        # so a merge that creates R6 close to an enemy beats scattered H1 debris.
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

        # Multi-attack: count distinct my towers (h>=3) that are the highest-quality
        # threat to DIFFERENT enemies — two towers each owning a separate enemy > one tower
        assigned = {}
        for tc, tv in opp_towers.items():
            best_q, best_mc = 0.0, None
            for mc, mv in my_towers.items():
                if mv.height >= tv.height and mv.height >= 3:
                    q = mv.height / (_mhdist(mc, tc) + 1)
                    if q > best_q:
                        best_q, best_mc = q, mc
            if best_mc is not None:
                assigned[tc] = best_mc
        multi_attack = len(set(assigned.values())) * 2.0

        # Directional cascade pressure: aligned + pushing enemy toward nearest edge
        cascade_pressure = 0.0
        for tc, tv in opp_towers.items():
            for mc, mv in my_towers.items():
                if mv.height < tv.height:
                    continue
                if mc.r == tc.r and mc.c != tc.c:
                    edge_exp = (7 - tc.c) if mc.c < tc.c else tc.c
                    cascade_pressure += 1.0 / ((abs(mc.c - tc.c) + 1) * (edge_exp + 1))
                elif mc.c == tc.c and mc.r != tc.r:
                    edge_exp = (7 - tc.r) if mc.r < tc.r else tc.r
                    cascade_pressure += 1.0 / ((abs(mc.r - tc.r) + 1) * (edge_exp + 1))

        # Mobility balance: (my escape routes - opp escape routes)
        my_mob = opp_mob = 0
        for mc, mv in my_towers.items():
            for d in CARDINAL_DIRECTIONS:
                try:
                    nc = self._board[mc + d]
                    if nc.is_empty or nc.color == color or (nc.color == opp and mv.height >= nc.height):
                        my_mob += 1
                except ValueError:
                    pass
        for tc, tv in opp_towers.items():
            for d in CARDINAL_DIRECTIONS:
                try:
                    nc = self._board[tc + d]
                    if nc.is_empty or nc.color == opp or (nc.color == color and tv.height >= nc.height):
                        opp_mob += 1
                except ValueError:
                    pass

        return (token_diff
                + (my_threat - opp_threat) * 1.5
                + multi_attack
                + cascade_pressure * 1.0
                + (my_mob - opp_mob) * 0.2
                + random.uniform(-0.1, 0.1))

    def _attack_cost(self, attackers: dict, targets: dict) -> float:
        # Greedy chain: after eating a target, the attacker moves to that cell
        # so it can chain into the next target from a closer position
        attackers = dict(attackers)   # shallow copy — we mutate positions
        total = 0
        for tc, tv in targets.items():
            if not attackers:
                break
            min_dist = math.inf
            best_ac = None
            for ac, av in attackers.items():
                if av.height < tv.height:
                    continue
                d = _mhdist(ac, tc)
                if d < min_dist:
                    min_dist = d
                    best_ac = ac
            if best_ac is None:
                total += 100   # no valid attacker for this target
                continue
            total += min_dist / attackers[best_ac].height
            attackers[tc] = attackers.pop(best_ac)
        return total

    def _ordered_actions(self, color: PlayerColor, depth: int, tt_move) -> list:
        # Order: TT move -> eats -> killers -> cascades (by history) -> moves (by history)
        state = self._board._state
        opp = color.opponent
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

    def _captures(self, color: PlayerColor) -> list:
        # Eat + cascade-through-enemy actions for quiescence search
        state = self._board._state
        opp = color.opponent
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

    def _store_killer(self, depth: int, action: Action):
        if action != self._killers[depth][0]:
            self._killers[depth][1] = self._killers[depth][0]
            self._killers[depth][0] = action

    def _action_key(self, action: Action):
        return (type(action).__name__,
                getattr(action, 'coord', None),
                getattr(action, 'direction', None))

    def _update_history(self, action: Action, depth: int):
        key = self._action_key(action)
        self._history[key] = self._history.get(key, 0) + (1 << depth)

    def _timed_out(self) -> bool:
        return time.time() - self._start_t > self._time_limit

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


def _mhdist(a: Coord, b: Coord) -> int:
    return abs(a.r - b.r) + abs(a.c - b.c)