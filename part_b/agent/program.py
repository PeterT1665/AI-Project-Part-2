# COMP30024 Artificial Intelligence, Semester 1 2026
# Project Part B: Game Playing Agent

from referee.game import PlayerColor, Coord, Direction, \
    Action, PlaceAction, MoveAction, EatAction, CascadeAction


class Agent:
    

    def __init__(self, color: PlayerColor, **referee: dict):
        
        self._color = color
        self._turn_count = 0
        match color:
            case PlayerColor.RED:
            case PlayerColor.BLUE:

    def action(self, **referee: dict) -> Action:
        

        # Below we have hardcoded actions to be played depending on whether
        # the agent is playing as BLUE or RED. Obviously this won't work beyond
        # the initial moves of the game, so you should use some game playing
        # technique(s) to determine the best action to take.

        # During placement phase (first 8 turns total, 4 per player)
        if self._turn_count < 4:
            match self._color:
                case PlayerColor.RED:
                    return PlaceAction(Coord(0, self._turn_count))
                case PlayerColor.BLUE:
                    return PlaceAction(Coord(7, self._turn_count))

        # During play phase
        match self._color:
            case PlayerColor.RED:
                return MoveAction(Coord(0, 0), Direction.Down)
            case PlayerColor.BLUE:
                return MoveAction(Coord(7, 0), Direction.Up)

    def update(self, color: PlayerColor, action: Action, **referee: dict):
        """
        This method is called by the referee after a player has taken their
        turn. You should use it to update the agent's internal game state.
        """
        if color == self._color:
            self._turn_count += 1

        match action:
            case PlaceAction(coord):
            case MoveAction(coord, direction):
            case EatAction(coord, direction):
            case CascadeAction(coord, direction):
            case _:
                raise ValueError(f"Unknown action type: {action}")
