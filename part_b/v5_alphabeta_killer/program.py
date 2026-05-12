# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import random
import math as Math
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N

DEPTH_LIM = 4

class Agent:

    

    def __init__(self, color: PlayerColor, **referee: dict):
        
        self._color = color
        self._board = Board()
        self.node_count = 0

        # create list of killers for killer heuristic
        self.killers = [None] * (DEPTH_LIM + 1) 
    
        match color:
            case PlayerColor.RED:
            case PlayerColor.BLUE:

    def action(self, **referee: dict) -> Action:
        
        if self._board.phase == GamePhase.PLACEMENT:
            maxEval = -Math.inf
            bestPlace = None
            for action in self._legal_placements():
                score = self.placement_evaluation(action.coord)
                if score > maxEval:
                    maxEval = score
                    bestPlace = action
            return bestPlace

        self.node_count = 0
        alpha = -Math.inf
        bestMove = None
        for action in self._legal_play_actions(self._color):
            self._board.apply_action(action)
            eval = self._minimax(0, alpha, Math.inf)
            self._board.undo_action()
            if bestMove is None or eval > alpha:
                bestMove = action
                alpha = eval

        return bestMove

    def _minimax(self,depth: int, alpha: float, beta: float) -> float:

        self.node_count+=1
        if(depth == DEPTH_LIM):
            return self._evaluation()

        elif(self._board.turn_color == self._color):
            highest = -Math.inf
            moves = self._legal_play_actions(self._color)
            if self.killers[depth] in moves:
                moves.remove(self.killers[depth])
                moves.insert(0, self.killers[depth])

            for action in moves:
                self._board.apply_action(action)
                value = self._minimax(depth+1,alpha,beta)
                self._board.undo_action()
                
                if(value>highest):
                    highest = value
                    self.killers[depth] = action
                alpha = max(value,alpha)
                if(beta <= alpha):
                    break
            return highest
        elif(self._board.turn_color == self._color.opponent):

            lowest = Math.inf
            moves = self._legal_play_actions(self._color.opponent)
            if self.killers[depth] in moves:
                moves.remove(self.killers[depth])
                moves.insert(0, self.killers[depth])
        
            for action in moves:
                    self._board.apply_action(action)
                    value = self._minimax(depth+1,alpha,beta)
                    self._board.undo_action()
                    if(value<lowest):
                        lowest = value
                        self.killers[depth] = action
                    beta = min(value,beta)
                    if(beta <= alpha):
                        break
            return lowest

    def _evaluation(self) -> float:

        if(self._board.game_over):
            if(self._board.winner_color == self._color): return Math.inf
            elif(self._board.winner_color == self._color.opponent): return -Math.inf
            else: return 0

        eval = 0

        ourTowers  = [(k,v) for k,v in self._board._state.items() if v.color == self._color]
        enemyTowers = [(k,v) for k,v in self._board._state.items() if v.color == self._color.opponent]


        if(self._color == PlayerColor.RED):
            eval +=  10*(self._board.red_tokens - self._board.blue_tokens)
        else:
            eval += -10*(self._board.red_tokens - self._board.blue_tokens)

        eval += self._attacking_power(ourTowers, enemyTowers)

        eval += 2*self._number_being_threatned(ourTowers,enemyTowers)

        eval += 0.5*self._proximity(ourTowers,enemyTowers)
        return eval
    
    def _proximity(self, ourTowers, enemyTowers):
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
        

    def _attacking_power(self, ourTowers, enemyTowers):
        ourAttackingPower = 0
        for myCoord, myVal in ourTowers:
            for oppCoord, oppVal in enemyTowers:
                if myVal.height >= oppVal.height:
                    ourAttackingPower += 1

        enemyAttackingPower = 0
        for oppCoord, oppVal in enemyTowers:
            for myCoord, myVal in ourTowers:
                if oppVal.height >= myVal.height: 
                    enemyAttackingPower += 1

        return ourAttackingPower - enemyAttackingPower
        
        
    def _number_being_threatned(self,ourTowers,enemyTowers):
        
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
        

        
    def placement_evaluation(self, coord) -> float:
        state = self._board._state
        color = self._color
        team_count = sum(1 for cell in state.values() if cell.color == color)

        center_score = -(abs(coord.r - 3.5) + abs(coord.c - 3.5))

        spread_score = Math.inf
        for team_coord, cell in state.items():
            if cell.color == color:
                spread_score = min(spread_score, self.manhattan_distance(team_coord, coord))
        if spread_score == Math.inf:
            spread_score = 0

        cascade_score = 0
        for d in CARDINAL_DIRECTIONS:
            if d == Direction.Right:
                count = 7 - coord.c
            elif d == Direction.Down:
                count = 7 - coord.r
            elif d == Direction.Left:
                count = coord.c
            else:
                count = coord.r
            if count <= 3:
                cascade_score += count

        if team_count == 1:
            for tower_coord, cell in state.items():
                if cell.color == color:
                    if self.manhattan_distance(tower_coord, coord) == 1:
                        return center_score + 100

        return 2 * center_score + spread_score + 1.5 * cascade_score

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