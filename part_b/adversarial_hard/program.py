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

MAX_DEPTH      = 8   # maximum search depth for IDDFS
QDEPTH         = 2   # extra depth for captures after the horizon
TIME_LIMIT_MAX = 5.0   # hard ceiling per move (seconds)
TIME_LIMIT_MIN = 0.5   # floor so we always do at least 1 full depth
TT_SIZE        = 1 << 18   # 256 K slots

# TT flags: EXACT = true value, UPPER = we failed low (upper bound), LOWER = we failed high (lower bound)
EXACT = 0
LOWER = 1
UPPER = 2

# Zobrist table: seeded so it's the same every run
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


# Fixed-size direct-mapped transposition table using arrays for speed
class _TTable:
    __slots__ = ('_k', '_v', '_d', '_f', '_m')

    def __init__(self):
        n = TT_SIZE
        # k=key, v=value, d=depth, f=flag, m=best move
        self._k = [0]     * n   
        self._v = [0.0]   * n
        self._d = [-1]    * n
        self._f = [EXACT] * n
        self._m = [None]  * n

    # Look up a position: return (val, depth, flag, move) or None if not found
    def probe(self, key: int):
        i = key & (TT_SIZE - 1)
        if self._k[i] == key and self._d[i] >= 0:
            return self._v[i], self._d[i], self._f[i], self._m[i]
        return None

    def store(self, key: int, val: float, depth: int, flag: int, move):
        i = key & (TT_SIZE - 1)
        # Only overwrite if new result is from a deeper (more reliable) search
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
        self._tt = _TTable()                                                    # transposition table
        self._killers = [[None, None] for _ in range(MAX_DEPTH + QDEPTH + 2)]  # 2 killer moves per depth slot
        self._history = {}   # action_key -> cutoff score
        self._pos_hist = []  # Zobrist hashes of real-game positions (last 16)
        self._start_t = 0.0
        self._time_limit = TIME_LIMIT_MAX   # per-turn time budget (seconds)
        self._turns_played = 0


    def action(self, **referee: dict) -> Action:
        if self._board.phase == GamePhase.PLACEMENT:
            return self._best_placement()

        # Time management: less time per turn as the gaem progesses
        time_rem = referee.get('time_remaining', 60.0)
        self._turns_played += 1
        turns_left = max(20, 150 - self._turns_played)
        self._time_limit = max(TIME_LIMIT_MIN,
                               min(TIME_LIMIT_MAX, time_rem / turns_left * 0.85))

        self._start_t = time.time()
        best = None
        prev_score = 0

        # Iterative deepening: search depth 1 -> 2 -> 3 until time runs out
        for depth in range(1, MAX_DEPTH + 1):
            if self._timed_out():
                break

            if depth <= 2:
                move, score = self._root(depth, -math.inf, math.inf)
            else:
                # Aspiration window: search with narrow window first, re-search if it fails
                delta = 30
                move, score = self._root(depth, prev_score - delta, prev_score + delta)
                if (abs(score) < math.inf and
                        (score <= prev_score - delta or score >= prev_score + delta)):
                    move, score = self._root(depth, -math.inf, math.inf)

            if move is not None:
                best = move
            prev_score = score
            if abs(score) >= math.inf:
                break   # forced win or loss

        return best

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        self._board.apply_action(action)
        zh = _hash_state(self._board._state)
        self._pos_hist.append(zh)
        if len(self._pos_hist) > 16:
            self._pos_hist.pop(0)

    # Pick the highest scoring legal placement cell
    def _best_placement(self) -> PlaceAction:
        best_score = -math.inf
        best_place = None
        for action in self._legal_placements():
            s = self._score_placement(action.coord)
            if s > best_score:
                best_score = s
                best_place = action
        return best_place

    # Score a candidate placement cell based on centre, spread from teammates, and cascade reach
    def _score_placement(self, coord: Coord) -> float:
        state = self._board._state
        color = self._color
        team_count = sum(1 for c in state.values() if c.color == color)

        # Center score
        center = -(abs(coord.r - 3.5) + abs(coord.c - 3.5))

        # minimum distance to closest teammate (0 if first piece)
        spread = math.inf
        for tc, cell in state.items():
            if cell.color == color:
                spread = min(spread, _mhdist(tc, coord))
        if spread == math.inf:
            spread = 0

        # count cells reachable in each direction within 3 steps (edges score lower)
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

    # Root search: always searches all moves to guarantee a best move is returned
    def _root(self, depth: int, alpha: float, beta: float):
        best_move = None
        zh = _hash_state(self._board._state)

        # Use TT move from previous iteration as first move to search
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

        # Store result in TT for future lookups
        self._tt.store(zh, alpha, depth, EXACT, best_move)
        return best_move, alpha

    def _minimax(self, depth: int, alpha: float, beta: float, is_max: bool) -> float:
        # Terminal state: return win/loss/draw immediately
        if self._board.game_over:
            if self._board.winner_color == self._color:          return  math.inf
            if self._board.winner_color == self._color.opponent: return -math.inf
            return 0.0

        # Base case: run quiescence search instead of static eval to avoid horizon effect
        if depth == 0:
            return self._quiescence(alpha, beta, QDEPTH, is_max)

        zh = _hash_state(self._board._state)

        # Positions seen 2+ times in real game: treat as draw to avoid repetition
        if self._pos_hist.count(zh) >= 2:
            return 0.0

        # Check TT: if we've seen this position before at sufficient depth, reuse the result
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

            # Late move reduction: search later moves at reduced depth, they're unlikely to be best
            reduce = (
                depth >= 3 and
                move_idx >= 4 and
                not isinstance(action, EatAction) and
                action not in (self._killers[depth][0], self._killers[depth][1])
            )
            val = self._minimax(depth - 1 - (1 if reduce else 0), alpha, beta, not is_max)

            # If reduced search looks promising, re-search at full depth to confirm
            if reduce:
                if (is_max and val > alpha) or (not is_max and val < beta):
                    val = self._minimax(depth - 1, alpha, beta, not is_max)

            self._board.undo_action()

            # Max (us): pick highest value
            if is_max:
                if val > best:
                    best = val
                    best_move = action
                alpha = max(alpha, val)
            # Min (opp): pick lowest value
            else:
                if val < best:
                    best = val
                    best_move = action
                beta = min(beta, val)

            # Pruning -> no need for further search
            if beta <= alpha:
                self._store_killer(depth, action)
                self._update_history(action, depth)
                break

        if not moves:
            return self._evaluate()

        if   best <= orig_a: flag = UPPER
        elif best >= orig_b: flag = LOWER
        else:                flag = EXACT

        # Store result in TT for future lookups
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

    # board evaluation: returns +inf for win, -inf for loss
    def _evaluate(self) -> float:
        state = self._board._state
        color = self._color
        opp = self._opp

        my_towers  = {coord: cell for coord, cell in state.items() if cell.color == color and cell.height > 0}
        opp_towers = {coord: cell for coord, cell in state.items() if cell.color == opp   and cell.height > 0}

        # if either side has no towers it's game over
        if not my_towers:  return -math.inf
        if not opp_towers: return  math.inf

        my_h  = sum(cell.height for cell in my_towers.values())
        opp_h = sum(cell.height for cell in opp_towers.values())

        # token count gap
        token_diff = (my_h - opp_h) * 2.0

        # score how well each enemy tower can be threatened
        my_threat = sum(
            max((min(my_cell.height, opp_cell.height) / (_mhdist(my_coord, opp_coord) + 1)
                 for my_coord, my_cell in my_towers.items() if my_cell.height >= opp_cell.height),
                default=0.0)
            for opp_coord, opp_cell in opp_towers.items()
        )
        opp_threat = sum(
            max((min(opp_cell.height, my_cell.height) / (_mhdist(my_coord, opp_coord) + 1)
                 for opp_coord, opp_cell in opp_towers.items() if opp_cell.height >= my_cell.height),
                default=0.0)
            for my_coord, my_cell in my_towers.items()
        )

        # match our best attacker to each enemy tower
        assigned = {}
        for opp_coord, opp_cell in opp_towers.items():
            best_q, best_my_coord = 0.0, None
            for my_coord, my_cell in my_towers.items():
                if my_cell.height >= opp_cell.height and my_cell.height >= 3:
                    q = my_cell.height / (_mhdist(my_coord, opp_coord) + 1)
                    if q > best_q:
                        best_q, best_my_coord = q, my_coord
            if best_my_coord is not None:
                assigned[opp_coord] = best_my_coord
        multi_attack = len(set(assigned.values())) * 2.0

        # being in the same row/col as an enemy is a potential cascade
        cascade_pressure = 0.0
        for opp_coord, opp_cell in opp_towers.items():
            for my_coord, my_cell in my_towers.items():
                if my_cell.height < opp_cell.height:
                    continue
                if my_coord.r == opp_coord.r and my_coord.c != opp_coord.c:
                    edge_exp = (7 - opp_coord.c) if my_coord.c < opp_coord.c else opp_coord.c
                    cascade_pressure += 1.0 / ((abs(my_coord.c - opp_coord.c) + 1) * (edge_exp + 1))
                elif my_coord.c == opp_coord.c and my_coord.r != opp_coord.r:
                    edge_exp = (7 - opp_coord.r) if my_coord.r < opp_coord.r else opp_coord.r
                    cascade_pressure += 1.0 / ((abs(my_coord.r - opp_coord.r) + 1) * (edge_exp + 1))

        # how many moves each side has
        my_mob = opp_mob = 0
        for my_coord, my_cell in my_towers.items():
            for d in CARDINAL_DIRECTIONS:
                try:
                    nc = self._board[my_coord + d]
                    if nc.is_empty or nc.color == color or (nc.color == opp and my_cell.height >= nc.height):
                        my_mob += 1
                except ValueError:
                    pass
        for opp_coord, opp_cell in opp_towers.items():
            for d in CARDINAL_DIRECTIONS:
                try:
                    nc = self._board[opp_coord + d]
                    if nc.is_empty or nc.color == opp or (nc.color == color and opp_cell.height >= nc.height):
                        opp_mob += 1
                except ValueError:
                    pass

        return (token_diff
                + (my_threat - opp_threat) * 1.5
                + multi_attack
                + cascade_pressure * 1.0
                + (my_mob - opp_mob) * 0.2
                + random.uniform(-0.1, 0.1))

    # Order moves: TT move first, then eats, killers, cascades, moves (sorted by history score)
    def _ordered_actions(self, color: PlayerColor, depth: int, tt_move) -> list:
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

    # Return only capture moves (eats and cascades that hit an enemy) for quiescence search
    def _captures(self, color: PlayerColor) -> list:
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


# Manhattan distance between two coordinates
def _mhdist(a: Coord, b: Coord) -> int:
    return abs(a.r - b.r) + abs(a.c - b.c)