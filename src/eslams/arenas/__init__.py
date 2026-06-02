"""Built-in public smoke arenas."""

from eslams.arena import registry
from eslams.arenas.checkers import CheckersArena
from eslams.arenas.chess import ChessArena
from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.hex import HexArena
from eslams.arenas.mancala import MancalaArena
from eslams.arenas.matrix_games import PrisonersDilemmaArena, RockPaperScissorsArena
from eslams.arenas.othello import OthelloArena
from eslams.arenas.pentago import PentagoArena
from eslams.arenas.tic_tac_toe import TicTacToeArena
from eslams.arenas.ultimate_tic_tac_toe import UltimateTicTacToeArena

registry.register(ConnectFourArena)
registry.register(TicTacToeArena)
registry.register(ChessArena)
registry.register(OthelloArena)
registry.register(GomokuArena)
registry.register(HexArena)
registry.register(CheckersArena)
registry.register(MancalaArena)
registry.register(PentagoArena)
registry.register(UltimateTicTacToeArena)
registry.register(RockPaperScissorsArena)
registry.register(PrisonersDilemmaArena)

__all__ = [
    "CheckersArena",
    "ChessArena",
    "ConnectFourArena",
    "GomokuArena",
    "HexArena",
    "MancalaArena",
    "OthelloArena",
    "PentagoArena",
    "PrisonersDilemmaArena",
    "RockPaperScissorsArena",
    "TicTacToeArena",
    "UltimateTicTacToeArena",
    "registry",
]
