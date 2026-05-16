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
QDEPTH         = 2       # extra depth for captures after horizon
TIME_LIMIT_MAX = 5.0
TIME_LIMIT_MIN = 0.5
TT_SIZE        = 1 << 18  # transposition table slots

EXACT = 0
LOWER = 1
UPPER = 2

# Zobrist hashing — fixed seed so it is the same every run
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


def _mhdist(a: Coord, b: Coord) -> int:
    return abs(a.r - b.r) + abs(a.c - b.c)


def _cascade_reach(coord: Coord, height: int) -> int:
    # number of cells reachable by cascade in 4 directions, capped at h6
    h = min(height, 6)
    r, c = coord.r, coord.c
    return min(h, r) + min(h, 7 - r) + min(h, c) + min(h, 7 - c)


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
        self._opp   = color.opponent
        self._board = Board()
        self._tt    = _TTable()
        self._killers    = [[None, None] for _ in range(MAX_DEPTH + QDEPTH + 2)]
        self._history    = {}
        self._pos_hist   = []
        self._start_t    = 0.0
        self._time_limit = TIME_LIMIT_MAX
        self._turns_played = 0

    def action(self, **referee: dict) -> Action:
        # placement phase has its own logic
        if self._board.phase == GamePhase.PLACEMENT:
            return self._best_placement()

        # spread time budget evenly across remaining turns
        time_rem = referee.get('time_remaining', 60.0)
        self._turns_played += 1
        turns_left = max(20, 150 - self._turns_played)
        self._time_limit = max(TIME_LIMIT_MIN,
                               min(TIME_LIMIT_MAX, time_rem / turns_left * 0.85))

        self._start_t = time.time()
        best       = None
        prev_score = 0

        # iterative deepening with aspiration windows
        for depth in range(1, MAX_DEPTH + 1):
            if self._timed_out():
                break

            if depth <= 2:
                move, score = self._root(depth, -math.inf, math.inf)
            else:
                delta = 30
                move, score = self._root(depth, prev_score - delta, prev_score + delta)
                # re-search with full window if result fell outside aspiration window
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
        # track position hashes to detect repetition
        zh = _hash_state(self._board._state)
        self._pos_hist.append(zh)
        if len(self._pos_hist) > 16:
            self._pos_hist.pop(0)

    # ---- placement phase -------------------------------------------------------

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
        # 1. prefer center — more cascade reach and escape routes
        # 2. pick cells that give good coverage (cascade range)
        # 3. place next to existing friendly towers for merge potential
        # 4. pressure opponent by placing nearby
        state  = self._board._state
        color  = self._color
        opp    = self._opp
        r, c   = coord.r, coord.c

        center_score = -(abs(r - 3.5) + abs(c - 3.5))
        coverage     = _cascade_reach(coord, 3)

        # score based on proximity to friendly towers
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

        # limit opponent's available placement cells
        opp_pressure = 0.0
        for tc, cell in state.items():
            if cell.color != opp:
                continue
            d = _mhdist(tc, coord)
            if d == 1:
                opp_pressure += 3.0
            elif d <= 3:
                opp_pressure += 1.0

        # place second piece adjacent to first so they can merge immediately in play phase
        if my_count == 1:
            for tc, cell in state.items():
                if cell.color == color and _mhdist(tc, coord) == 1:
                    return 200.0

        return 2.0 * center_score + 0.8 * coverage + support + opp_pressure

    # ---- search ----------------------------------------------------------------

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
        if self._board.game_over:
            if self._board.winner_color == self._color:          return  math.inf
            if self._board.winner_color == self._color.opponent: return -math.inf
            return 0.0

        if depth == 0:
            return self._quiescence(alpha, beta, QDEPTH, is_max)

        zh = _hash_state(self._board._state)

        # treat repeated positions as draws to avoid loops
        if self._pos_hist.count(zh) >= 2:
            return 0.0

        # transposition table lookup
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

            # late move reduction — search quiet late moves at shallower depth
            reduce = (
                depth >= 3 and
                move_idx >= 4 and
                not isinstance(action, EatAction) and
                action not in (self._killers[depth][0], self._killers[depth][1])
            )
            val = self._minimax(depth - 1 - (1 if reduce else 0), alpha, beta, not is_max)

            # re-search at full depth if reduced result looks promising
            if reduce and ((is_max and val > alpha) or (not is_max and val < beta)):
                val = self._minimax(depth - 1, alpha, beta, not is_max)

            self._board.undo_action()

            if is_max:
                if val > best:
                    best      = val
                    best_move = action
                alpha = max(alpha, val)
            else:
                if val < best:
                    best      = val
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
        # evaluate captures only to avoid horizon effect
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

    # ---- evaluation ------------------------------------------------------------

    def _evaluate(self) -> float:
        state = self._board._state
        color = self._color
        opp   = self._opp

        # get all active towers for each side
        my_towers  = {c: v for c, v in state.items() if v.color == color and v.height > 0}
        opp_towers = {c: v for c, v in state.items() if v.color == opp   and v.height > 0}

        if not my_towers:  return -math.inf
        if not opp_towers: return  math.inf

        my_h  = sum(v.height for v in my_towers.values())
        opp_h = sum(v.height for v in opp_towers.values())

        # token count is the win condition so it gets the highest weight
        token_diff = (my_h - opp_h) * 2.0

        # penalise towers above h6 — merging past 6 just concentrates tokens
        # without gaining new reach (cascade can already hit any height)
        height_penalty = 0.0
        for v in my_towers.values():
            if v.height > 6:
                height_penalty -= (v.height - 6) * 2.0
        for v in opp_towers.values():
            if v.height > 6:
                height_penalty += (v.height - 6) * 2.0

        # cell control — sum of cascade reach for each tower
        my_ctrl  = sum(_cascade_reach(mc, mv.height) for mc, mv in my_towers.items())
        opp_ctrl = sum(_cascade_reach(tc, tv.height) for tc, tv in opp_towers.items())
        control_diff = (my_ctrl - opp_ctrl) * 0.3

        # edge pressure — we want our towers central and opponent towers on the edge
        # min(r, 7-r, c, 7-c) is 0 on the edge and up to 3 at the centre
        my_edge_val  = sum(min(mc.r, 7 - mc.r, mc.c, 7 - mc.c) for mc in my_towers) * 0.2
        opp_edge_val = sum(min(tc.r, 7 - tc.r, tc.c, 7 - tc.c) for tc in opp_towers) * 0.4
        edge_pressure = my_edge_val - opp_edge_val

        # threat quality — for each enemy find our closest eligible attacker
        # cap at min(attacker, target) so there is no incentive to over-merge
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

        # pairing bonus — count distinct friendly towers each hunting a different enemy
        # two separate hunters > one merged hunter
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

        return (token_diff
                + height_penalty
                + control_diff
                + edge_pressure
                + (my_threat - opp_threat) * 1.5
                + pairing
                + random.uniform(-0.05, 0.05))

    # ---- move ordering ---------------------------------------------------------

    def _ordered_actions(self, color: PlayerColor, depth: int, tt_move) -> list:
        # order: TT move -> eats -> killers -> cascades -> moves
        # (all sorted by history score within their group)
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

    def _captures(self, color: PlayerColor) -> list:
        # eat and cascade-through-enemy actions for quiescence search
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

    # ---- helpers ---------------------------------------------------------------

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
