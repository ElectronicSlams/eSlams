"""Built-in public smoke arenas."""

from eslams.arena import registry
from eslams.arenas.chess import ChessArena
from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.hex import HexArena
from eslams.arenas.othello import OthelloArena
from eslams.arenas.tic_tac_toe import TicTacToeArena

registry.register(ConnectFourArena)
registry.register(TicTacToeArena)
registry.register(ChessArena)
registry.register(OthelloArena)
registry.register(GomokuArena)
registry.register(HexArena)

__all__ = [
    "ChessArena",
    "ConnectFourArena",
    "GomokuArena",
    "HexArena",
    "OthelloArena",
    "TicTacToeArena",
    "registry",
]
