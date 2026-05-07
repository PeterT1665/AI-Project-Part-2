# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import random
import math as Math
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

DEPTH_LIM = 3   # odd means we calculate the eval at this agents turn


class Agent:
    

    def __init__(self, color: PlayerColor, **referee: dict):
        
        self._color = color
        self._board = Board()

        match color:
            case PlayerColor.RED:
            case PlayerColor.BLUE:

    def action(self, **referee: dict) -> Action:
        
        value: dict[Action,float] = {}

        if self._board.phase == GamePhase.PLACEMENT:
            return random.choice(self._legal_placements())

        alpha = -Math.inf
        bestMove = None
        for action in self._legal_play_actions(self._color):
            self._board.apply_action(action)
            eval = self._minimax(0,alpha,Math.inf)
            
            if(eval> alpha):
                bestMove = action 
                alpha = eval
            self._board.undo_action()
        return bestMove

    def _minimax(self,depth: int, alpha: float, beta: float) -> float:

        if(depth == DEPTH_LIM):
            return self._evaluation()                                  

        elif(self._board.turn_color == self._color):
            highest = -Math.inf
            for action in self._legal_play_actions(self._color):
                self._board.apply_action(action)
                value = self._minimax(depth+1,alpha,beta)
                self._board.undo_action()
                highest = max(value,highest)
                alpha = max(value,alpha)
                if(beta <= alpha):
                    break
            return highest
        elif(self._board.turn_color == self._color.opponent):
            lowest = Math.inf
            for action in self._legal_play_actions(self._color.opponent):
                self._board.apply_action(action)
                value = self._minimax(depth+1,alpha,beta)
                self._board.undo_action()
                lowest = min(value,lowest)
                beta = min(value,beta)
                if(beta <= alpha):
                    break
            return lowest

    def _evaluation(self) -> float:
        if(self._color == PlayerColor.RED):
            return self._board.red_tokens - self._board.blue_tokens
        else:
            return -(self._board.red_tokens - self._board.blue_tokens)
        
    def _evaluation1(self) -> float:
        if(self._color == PlayerColor.RED):
            return self._board.red_tokens - self._board.blue_tokens
        else:
            return -(self._board.red_tokens - self._board.blue_tokens)


    def update(self, color: PlayerColor, action: Action, **referee: dict):
        """
        This method is called by the referee after a player has taken their
        turn. You should use it to update the agent's internal game state.
        """
        self._board.apply_action(action)


        '''
        match action:
            case PlaceAction(coord):
            case MoveAction(coord, direction):
            case EatAction(coord, direction):
            case CascadeAction(coord, direction):
            case _:
                raise ValueError(f"Unknown action type: {action}")
        '''

    def _legal_placements(self) -> list[PlaceAction]:
        """
        Returns a list of all legal placement actions for the current board state.
        """
        actions = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                coord = Coord(r, c)
                
                # Skip occupied cells
                if not self._board[coord].is_empty:
                    continue

                # Skip cells adjacent to opponent's pieces if it's not the first placement
                if self._board._placement_count > 0 and self._adj_opponent(coord):
                    continue

                actions.append(PlaceAction(coord))
        return actions

    def _adj_opponent(self, coord: Coord) -> bool:
        """
        Return True if the given coordinate is adjacent to an opponent's piece, False otherwise.
        """
        opp = self._color.opponent
        for d in CARDINAL_DIRECTIONS:
            try:
                if self._board[coord + d].color == opp:
                    return True
            except ValueError:
                pass
        return False
    

    def _legal_play_actions(self, color : PlayerColor) -> list[Action]:
        """
        Returns a list of all legal play actions (MOVE, EAT, CASCADE) for the current board state.
        """
        state = self._board._state
        opp = color.opponent

        eat_actions = []
        cascade_actions = []
        move_actions = []

        for coord, cell in state.items():
            if cell.color != color:
                continue
            
            # Check all 4 dir for possible move or eat actions
            for d in CARDINAL_DIRECTIONS:
                try:
                    des = coord + d
                    if self._board[des].is_empty:
                        move_actions.append(MoveAction(coord, d))
                    elif self._board[des].color == color:
                        move_actions.append(MoveAction(coord, d))
                    elif self._board[des].color == opp:
                        if (cell.height >= self._board[des].height):
                            eat_actions.append(EatAction(coord, d))
                except ValueError:
                    pass
            
            # Check for possible cascade actions
            if cell.height >= 2:
                for d in CARDINAL_DIRECTIONS:
                    cascade_actions.append(CascadeAction(coord, d))
        
        return eat_actions + cascade_actions + move_actions