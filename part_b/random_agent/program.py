# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import random
from referee.game import PlayerColor, Coord, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

class Agent:
    def __init__(self, color: PlayerColor, **referee: dict):
        self._color = color
        self._board = Board()

    def action(self, **referee: dict) -> Action:
        if self._board.phase == GamePhase.PLACEMENT:
            actions = self._legal_placements()
        else:
            actions = self._legal_play_actions()

        return random.choice(actions)

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        self._board.apply_action(action)

    # Finding all the legal placement
    def _legal_placements(self) -> list[PlaceAction]:
        actions = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                coord = Coord(r, c)
                if not self._board[coord].is_empty:
                    continue
                
                # First placement has no restriction since the board is empty
                if self._board._placement_count > 0 and self._adj_opponent(coord):
                    continue

                actions.append(PlaceAction(coord))
        return actions

    # Check if any opponent piece is adjacent to the current coord
    def _adj_opponent(self, coord: Coord) -> bool:
        opp = self._color.opponent
        for d in CARDINAL_DIRECTIONS:
            try:
                if self._board[coord + d].color == opp:
                    return True
            except ValueError:
                pass
        return False
    
    # Find all the legal play action - Eat/Move/Cascade
    def _legal_play_actions(self) -> list[Action]:
        state = self._board._state
        color = self._color
        opp = color.opponent

        eat_actions = []
        cascade_actions = []
        move_actions = []

        for coord, cell in state.items():
            if cell.color != color:
                continue

            # Move type actions
            for d in CARDINAL_DIRECTIONS:
                try:
                    des = coord + d
                    # Normal move to empty spot
                    if self._board[des].is_empty:
                        move_actions.append(MoveAction(coord, d))

                    # Move to teammate -> Merge
                    elif self._board[des].color == color:
                        move_actions.append(MoveAction(coord, d))
                    
                    # Move to opponent -> Eat
                    elif self._board[des].color == opp:
                        if (cell.height >= self._board[des].height):
                            eat_actions.append(EatAction(coord, d))
                
                # Off the board -> pass
                except ValueError:
                    pass
            
            # Cascade actions
            if cell.height >= 2:
                for d in CARDINAL_DIRECTIONS:
                    cascade_actions.append(CascadeAction(coord, d))
        
        return eat_actions + cascade_actions + move_actions