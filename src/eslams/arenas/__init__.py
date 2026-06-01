"""Built-in public smoke arenas."""

from eslams.arena import registry
from eslams.arenas.chess import ChessArena
from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.tic_tac_toe import TicTacToeArena

registry.register(ConnectFourArena)
registry.register(TicTacToeArena)
registry.register(ChessArena)

__all__ = ["ChessArena", "ConnectFourArena", "TicTacToeArena", "registry"]
