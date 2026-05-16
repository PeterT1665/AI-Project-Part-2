import json
import subprocess
from pathlib import Path
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase

_DIR_TO_DI = {
    Direction.Up:    0,
    Direction.Down:  1,
    Direction.Left:  2,
    Direction.Right: 3,
}
_DI_TO_DIR = [Direction.Up, Direction.Down, Direction.Left, Direction.Right]

def _encode(action: Action) -> int:
    if isinstance(action, PlaceAction):
        return action.coord.r * 8 + action.coord.c
    idx = action.coord.r * 8 + action.coord.c
    di  = _DIR_TO_DI[action.direction]
    if isinstance(action, MoveAction):    return 64  + idx * 4 + di
    if isinstance(action, EatAction):     return 320 + idx * 4 + di
    if isinstance(action, CascadeAction): return 576 + idx * 4 + di
    raise ValueError(f"Unknown action {action}")

def _decode(code: int) -> Action:
    if code < 64:
        return PlaceAction(Coord(code // 8, code % 8))
    if code < 320:
        code -= 64;  idx, di = code // 4, code % 4
        return MoveAction(Coord(idx // 8, idx % 8), _DI_TO_DIR[di])
    if code < 576:
        code -= 320; idx, di = code // 4, code % 4
        return EatAction(Coord(idx // 8, idx % 8), _DI_TO_DIR[di])
    code -= 576; idx, di = code // 4, code % 4
    return CascadeAction(Coord(idx // 8, idx % 8), _DI_TO_DIR[di])

def _snapshot(board: Board) -> dict:
    cells = []
    for r in range(8):
        for c in range(8):
            cell = board[Coord(r, c)]
            if cell.is_empty:
                cells.append([2, 0])
            elif cell.color == PlayerColor.RED:
                cells.append([0, cell.height])
            else:
                cells.append([1, cell.height])
    return {
        'cells': cells,
        'turnColor': 0 if board.turn_color == PlayerColor.RED else 1,
        'placementCount': board._placement_count,
        'turnCount': board.turn_count,
    }


class Agent:
    def __init__(self, color: PlayerColor, **referee):
        self._color = color
        self._board = Board()

        here   = Path(__file__).parent
        script = here / 'node_agent.mjs'
        weights = here / 'weights'

        self._proc = subprocess.Popen(
            ['node', str(script), str(weights), '400'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self._send({'type': 'init'})
        resp = self._recv()
        assert resp.get('type') == 'ready', f"bad init: {resp}"

        match color:

    def _send(self, msg):
        self._proc.stdin.write(json.dumps(msg) + '\n')
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        return json.loads(self._proc.stdout.readline())

    def action(self, **referee) -> Action:
        snap = _snapshot(self._board)
        self._send({'type': 'choose', 'snapshot': snap})
        resp = self._recv()
        return _decode(resp['action'])

    def update(self, color: PlayerColor, action: Action, **referee):
        self._board.apply_action(action)
        self._send({'type': 'update', 'action': _encode(action)})
        self._recv()

    def __del__(self):
        try:
            self._proc.terminate()
        except Exception:
            pass
