"""Built-in public smoke arenas."""

from eslams.arena import registry
from eslams.arenas.battleship import BattleshipArena
from eslams.arenas.checkers import CheckersArena
from eslams.arenas.chess import ChessArena
from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.gridworld import CliffWalkingArena, FrozenLakeArena, TaxiArena
from eslams.arenas.hex import HexArena
from eslams.arenas.mancala import MancalaArena
from eslams.arenas.matrix_games import PrisonersDilemmaArena, RockPaperScissorsArena
from eslams.arenas.othello import OthelloArena
from eslams.arenas.pentago import PentagoArena
from eslams.arenas.strategic_games import (
    BargainingArena,
    BlackjackArena,
    FirstPriceSealedBidAuctionArena,
    GoofspielArena,
    LiarsDiceArena,
    NegotiationArena,
)
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
registry.register(BattleshipArena)
registry.register(FrozenLakeArena)
registry.register(CliffWalkingArena)
registry.register(TaxiArena)
registry.register(RockPaperScissorsArena)
registry.register(PrisonersDilemmaArena)
registry.register(BlackjackArena)
registry.register(FirstPriceSealedBidAuctionArena)
registry.register(GoofspielArena)
registry.register(LiarsDiceArena)
registry.register(BargainingArena)
registry.register(NegotiationArena)

__all__ = [
    "BargainingArena",
    "BattleshipArena",
    "BlackjackArena",
    "CheckersArena",
    "ChessArena",
    "CliffWalkingArena",
    "ConnectFourArena",
    "FirstPriceSealedBidAuctionArena",
    "FrozenLakeArena",
    "GomokuArena",
    "GoofspielArena",
    "HexArena",
    "LiarsDiceArena",
    "MancalaArena",
    "NegotiationArena",
    "OthelloArena",
    "PentagoArena",
    "PrisonersDilemmaArena",
    "RockPaperScissorsArena",
    "TaxiArena",
    "TicTacToeArena",
    "UltimateTicTacToeArena",
    "registry",
]
