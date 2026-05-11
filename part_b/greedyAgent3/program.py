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
        self.seen_states = {}

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


         # record the state we're moving into
        self._board.apply_action(bestMove)
        key = self._board_hash()
        self.seen_states[key] = self.seen_states.get(key, 0) + 1
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

        eval += 2*self._number_being_threatned()

        eval += 0.5*self._proximity()

        state_key = self._board_hash()
        visits = self.seen_states.get(state_key, 0)
        eval -= visits * 15

        return eval
    

    def _proximity(self):
        
        ourTowers  = [(k,v) for k,v in self._board._state.items() if v.color == self._color]
        enemyTowers = [(k,v) for k,v in self._board._state.items() if v.color == self._color.opponent]

        bonus = 0
        for oppCoord, oppVal in enemyTowers:
            killable_dists = [
                self.manhattan_distance(myCoord, oppCoord)
                for myCoord, myVal in ourTowers
                if myVal.height >= oppVal.height
            ]
            if killable_dists:
                bonus -= min(killable_dists) 

        return bonus

        

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
        
        
    def _number_being_threatned(self):
        
        ourTowers = [(key,value) for key,value in self._board._state.items() if value.color == self._color ]
        enemyTowers = [(key,value)for key,value in self._board._state.items() if value.color == self._color.opponent]
        
        numOurThreats = 0
        for i in ourTowers:
            for j in enemyTowers:
                if i[1].height >= j[1].height and self.manhattan_distance(i[0],j[0]) == 1:
                    numOurThreats+= j[1].height

        numEnemyThreats = 0
        for i in enemyTowers:
            for j in ourTowers:
                dist = self.manhattan_distance(i[0],j[0])
                if i[1].height >= j[1].height and dist == 1:
                    numEnemyThreats+=j[1].height
                elif(i[0].r == j[0].r):
                    if(i[0].c<j[0].c):
                        if(i[0].c+i[1].height>=BOARD_N):
                            numEnemyThreats+=j[1].height
                    elif(i[0].c>j[0].c):
                        if(i[0].c-i[1].height<=0):
                            numEnemyThreats+=j[1].height
                elif(i[0].c == j[0].c):
                    if(i[0].r<j[0].r):
                        if(i[0].r+i[1].height>=BOARD_N):
                            numEnemyThreats+=j[1].height
                    elif(i[0].r>j[0].r):
                        if(i[0].r-i[1].height<=0):
                            numEnemyThreats+=j[1].height
        
        
        return -numEnemyThreats
        
        
    def manhattan_distance(self, a: Coord, b: Coord):
        return abs(a.r - b.r) + abs(a.c - b.c)        


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
    
    
    def _board_hash(self) -> str:
        # hash the current board state as a frozenset of occupied positions
        return frozenset(
            (coord, val.color, val.height)
            for coord, val in self._board._state.items()
            if not val.is_empty
        )