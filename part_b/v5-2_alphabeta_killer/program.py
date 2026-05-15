# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

import random
import math as Math
from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction
from referee.game.board import Board, GamePhase
from referee.game.coord import CARDINAL_DIRECTIONS
from referee.game.constants import BOARD_N
import sys
import time

MAX_TRANSPOSITIONS = 1_000_000
MAX_TURNS = 300
TIME_LIMIT = 180
PLACEMENT_TURNS = 8


# transposition table flags
EXACT_FLAG = 0 
UPPER_FLAG = 1
LOWER_FLAG = 2


class TimeoutException(Exception):
    pass

class Agent:

    

    def __init__(self, color: PlayerColor, **referee: dict):
        
        self._color = color
        self._board = Board()

        self.node_count = 0
        self.transpositions_added = 0
        self.transpositions_used = 0
        
        self.zobrist_table = {}
        self._init_zobrist_hash()

        self.transposition_table = {}

        self.start = 0
        self.time_budget = 0

        # create list of killers for killer heuristic
        self.killers = [None] * (50) 
    
        match color:
            case PlayerColor.RED:
            case PlayerColor.BLUE:

    def action(self, **referee: dict) -> Action:
        
        self.start=time.time()

        self.time_budget = self._budget_time(referee)

        if self._board.phase == GamePhase.PLACEMENT:
            maxEval = -Math.inf
            bestPlace = None
            for action in self._legal_placements():
                score = self.placement_evaluation(action.coord)
                if score > maxEval:
                    maxEval = score
                    bestPlace = action

            return bestPlace
        
        nodes = self.node_count
        legal_actions = self._legal_play_actions(self._color)
        best_move = None
        for depth_limit in range(1,20):
            if time.time() - self.start > self.time_budget:
                break
            alpha = -Math.inf
            iterations_bestMove = None
            budget_depleted = False

            for action in legal_actions:

                if time.time() - self.start > self.time_budget:
                    budget_depleted = True
                    break

                self._board.apply_action(action)
                try:
                    eval = self._minimax(0, alpha, Math.inf,depth_limit)
                except TimeoutException:
                    budget_depleted = True
                    self._board.undo_action()
                    break
                self._board.undo_action()

                if eval is None:
                    budget_depleted = True
                    break

                if iterations_bestMove is None or eval > alpha:
                    iterations_bestMove = action
                    alpha = eval
            
            if(not budget_depleted and iterations_bestMove is not None):
                best_move = iterations_bestMove
                legal_actions.remove(best_move)
                legal_actions.insert(0,best_move)

            

        return best_move


    def _budget_time(self,referee:dict):
        """
            give this turn an a allocated time
        """
        time_remaining = referee["time_remaining"]
        turns_left = max(1,(MAX_TURNS - PLACEMENT_TURNS - self._board.turn_count)/2)
        time_remaining/turns_left

        # tokens_left = abs(self._board.red_tokens - self._board.blue_tokens)
        # end_game = 1 - (tokens_left/24)

        end_game = 1 - (min(self._board.red_tokens,self._board.blue_tokens)/12)


        # num_towers = 0
        # for val in self._board._state.values():
        #     if(not val.is_empty):
        #         num_towers+=1
        # end_game = 1 -(abs(num_towers)/24)
        # # scale based on if we in end_game?
        scale = 1+2*end_game


        return (time_remaining/turns_left)*scale

        



    def _minimax(self,depth: int, alpha: float, beta: float,depth_lim : int) -> float:

        if(time.time()-self.start > self.time_budget):
            raise TimeoutException()
        
        self.node_count+=1

        key = self._get_hash()
        if key in self.transposition_table:
            t_depth,t_eval,t_flag = self.transposition_table[key]

            remaining_depth = depth_lim - depth

            if(t_depth>= remaining_depth):
                self.transpositions_used+=1
                
                if t_flag == EXACT_FLAG:
                    return t_eval
                elif t_flag == UPPER_FLAG:
                    beta =  min(beta,t_eval)
                elif t_flag == LOWER_FLAG:
                    alpha =  max(alpha,t_eval)
                
                if alpha>=beta:
                    return t_eval

        
        
        if(depth == depth_lim):
            eval = self._evaluation()
            if(len(self.transposition_table)< MAX_TRANSPOSITIONS):
                self.transposition_table[key] = (0,eval,EXACT_FLAG)
                self.transpositions_added+=1

            return eval

        elif(self._board.turn_color == self._color):
            highest = -Math.inf
            prev_alpha = alpha

            moves = self._legal_play_actions(self._color)
            if self.killers[depth] in moves:
                moves.remove(self.killers[depth])
                moves.insert(0, self.killers[depth])

            for action in moves:
                self._board.apply_action(action)
                try:
                    value = self._minimax(depth+1,alpha,beta,depth_lim)
                except TimeoutException:
                    self._board.undo_action()
                    raise
                self._board.undo_action()
                
                if(value>highest):
                    highest = value
                    self.killers[depth] = action
                alpha = max(value,alpha)
                if(beta <= alpha):
                    break

            flag = -1
            if(highest<= prev_alpha):
                flag = UPPER_FLAG
            elif(highest>= beta):
                flag = LOWER_FLAG
            else:
                flag = EXACT_FLAG
            if(len(self.transposition_table)< MAX_TRANSPOSITIONS):
                self.transposition_table[key] = (depth_lim-depth,highest,flag)
                self.transpositions_added+=1

            return highest
        elif(self._board.turn_color == self._color.opponent):
            lowest = Math.inf
            prev_beta = beta
            moves = self._legal_play_actions(self._color.opponent)
            if self.killers[depth] in moves:
                moves.remove(self.killers[depth])
                moves.insert(0, self.killers[depth])
        
            for action in moves:
                    self._board.apply_action(action)
                    try:
                        value = self._minimax(depth+1,alpha,beta,depth_lim)
                    except TimeoutException:
                        self._board.undo_action()
                        raise
                    self._board.undo_action()
                    if(value<lowest):
                        lowest = value
                        self.killers[depth] = action
                    beta = min(value,beta)
                    if(beta <= alpha):
                        break
            
            flag = -1
            if(lowest >= prev_beta):
                flag = UPPER_FLAG
            elif(lowest<= alpha):
                flag = LOWER_FLAG
            else:
                flag = EXACT_FLAG
            if(len(self.transposition_table)< MAX_TRANSPOSITIONS):
                self.transposition_table[key] = (depth_lim-depth,lowest,flag)
                self.transpositions_added+=1

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
        Returns a list of all legal play actions (MOVE, EAT, CASCADE) for the current board state for this player color
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
        
        # sort the eat actions and cascade actions based on how much tokens they take out
        # eat_actions.sort(key=lambda a: self._board._state[a.coord + a.direction].height, reverse=True)
        # if(eat_actions):
        #     print("-------------------------------------------")
        #     print(color)
        #     print(Utils.render(self._board._state,use_color=True))
        #     print(eat_actions)
        #     sys.exit()
        return eat_actions + cascade_actions + move_actions


    def _init_zobrist_hash(self):

        for r in range(BOARD_N):
            for c in range(BOARD_N):
                for color in [PlayerColor.RED,PlayerColor.BLUE]:
                    for height in range(1,13):
                        self.zobrist_table[(r,c,color,height)] = random.getrandbits(64)

        return

    def _get_hash(self):
        hash = 0
        for coord,cell_state in self._board._state.items():
            if not self._board[coord].is_empty:
                hash ^= self.zobrist_table[(coord.r,coord.c,cell_state.color,cell_state.height)]

        return hash
