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
CENTER = (3.5, 3.5)

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
            maxEval = -Math.inf
            bestPlace = None
            for action in self._legal_placements():
                eval = self.placement_evaluation(action.coord)
                if (eval > maxEval):
                    maxEval = eval
                    bestPlace = action
            
            return bestPlace

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
    
    def _find_merge_action(self):
        state = self._board._state
        color = self._color
        for team_coord, cell in state.items():
            if cell.color == color:
                for d in CARDINAL_DIRECTIONS:
                    try:
                        des = team_coord + d
                        if self._board[des].color == color:
                            return MoveAction(team_coord, d)
                    except ValueError:
                        pass
        return None

    def _minimax(self,depth: int, alpha: float, beta: float) -> float:

        if(depth == DEPTH_LIM):
            return self._evaluation_cascade()                                  

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
        
    def _evaluation_cascade(self) -> float:
        my_towers = {}
        opp_towers = {}
        for coord, cell in self._board._state.items():
            if cell.height == 0:
                continue
            if cell.color == self._color:
                my_towers[coord] = cell
            else:
                opp_towers[coord] = cell
        if not my_towers:
            return -Math.inf
        if not opp_towers:
            return Math.inf
        
        # Add the token to the score to better evaluate
        my_token = 0
        opp_token = 0
        for cell in my_towers.values():
            my_token += cell.height
        for cell in opp_towers.values():
            opp_token += cell.height
        

        my_attack_score = self._attack_evaluation(my_towers, opp_towers)
        opp_attack_score = self._attack_evaluation(opp_towers, my_towers)

        return opp_attack_score - my_attack_score + my_token - opp_token
        
    def _attack_evaluation(self, attackers, targets):
        attackers = dict(attackers)
        total_cost = 0
        for target_coord, target_cell in targets.items():
            min_dist = Math.inf
            closest_coord = None
            if not attackers:
                break
            for attacker_coord, attacker_cell in attackers.items():
                # Only higher tower can attack
                if attacker_cell.height < target_cell.height:
                    continue
                dist = self.manhattan(target_coord, attacker_coord)
                if dist < min_dist:
                    min_dist = dist
                    closest_coord = attacker_coord
            
            # No attacker tall enough to eat this target — heavy penalty
            if closest_coord is None:
                total_cost += 100
                continue

            height = attackers[closest_coord].height
            cost = -(-min_dist // height)   # Ceiling division
            total_cost += cost
            attackers[target_coord] = attackers.pop(closest_coord)
        return total_cost


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
    
    def placement_evaluation(self, coord) -> float:
        # 4 Placing move for 4 towers
        state = self._board._state
        color = self._color
        team_count = 0
        for cell in state.values():
            if cell.color == color:
                team_count += 1

        # Score = center_score + spread_score + cascade_score
        # Center_score = distance to the middle (3.5, 3.5)
        center_score = -(abs(coord.r - 3.5) + abs(coord.c - 3.5))

        # Spread_score = how far from the closest team tower
        spread_score = Math.inf
        # Look for team tower
        for team_coord, cell in state.items():
            if cell.color == color:
                dist = self.manhattan(team_coord, coord)
                spread_score = min(spread_score, dist)
        if spread_score == Math.inf:
            spread_score = 0
        
        # Cascade_score = highest at exactly 3 cells from edge, lower when closer, 0 if further
        cascade_score = 0
        for d in CARDINAL_DIRECTIONS:
            if d == Direction.Right:
                count = 7 - coord.c
                if count <= 3:
                    cascade_score += count
            elif d == Direction.Down:
                count = 7 - coord.r
                if count <= 3:
                    cascade_score += count
            elif d == Direction.Left:
                count = coord.c
                if count <= 3:
                    cascade_score += count
            else:
                count = coord.r
                if count <= 3:
                    cascade_score += count

        # 1st, 3rd or 4th -> same logic (center, spread, cascade)
        # 2nd tower -> place next to the first
        if team_count == 1:
            # Find the first tower
            for tower_coord, cell in state.items():
                if cell.color == color:
                    # Check if it is next to the first tower
                    if self.manhattan(tower_coord, coord) == 1:
                        return center_score + 100
                    
        return 2 * center_score + spread_score + 1.5 * cascade_score
    
    def manhattan(self, coord_1, coord_2) -> float:
        return abs(coord_1.r-coord_2.r)+abs(coord_1.c-coord_2.c)

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