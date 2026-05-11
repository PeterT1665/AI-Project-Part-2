# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import random
import math as Math
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N


class Agent:
    

    def __init__(self, color: PlayerColor, **referee: dict):
        
        self._color = color
        self._board = Board()

        match color:
            case PlayerColor.RED:
            case PlayerColor.BLUE:

    def action(self, **referee: dict) -> Action:
        

        if self._board.phase == GamePhase.PLACEMENT:
            return random.choice(self._legal_placements())


        # """""REMOVE LATER THIS IS FOR RANDOM INJECTION TO AVOID TIES"""
        # EPSILON = 0.1  # 10% chance of random move

        # if random.random() < EPSILON:
        #     return random.choice(self._legal_play_actions(self._color))
        

        value = -Math.inf
        bestMove = None
        for action in self._legal_play_actions(self._color):
            self._board.apply_action(action)
            eval = self._evaluation()
            if(eval > value):
                value = eval
                bestMove = action
            self._board.undo_action()
        return bestMove

    def _evaluation(self) -> float:

        if(self._board.game_over):
            if(self._board.winner_color == self._color): return Math.inf
            elif(self._board.winner_color == self._color.opponent): return -Math.inf
            else: return 0

        # If we have more towers we are doing better
        eval = 0
        if(self._color == PlayerColor.RED):
            eval +=  10*(self._board.red_tokens - self._board.blue_tokens)
        else:
            eval += -10*(self._board.red_tokens - self._board.blue_tokens)

        eval += self._attacking_power()
        return eval
    
    def _attacking_power(self):
        
        ourTowers = [value.height for key,value in self._board._state.items() if value.color == self._color ]
        enemyTowers = [value.height for key,value in self._board._state.items() if value.color == self._color.opponent]
        
        ourAttackingPower = 0
        for i in ourTowers:
            for j in enemyTowers:
                if i>=j:
                    ourAttackingPower+=1

        enemyAttackingPower = 0
        for i in enemyTowers:
            for j in ourTowers:
                if i>=j:
                    enemyAttackingPower+=1
        
        return ourAttackingPower-enemyAttackingPower
        
        

            


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