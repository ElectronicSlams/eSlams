"""Built-in public smoke arenas."""

from eslams.arena import registry
from eslams.arenas.advanced_cards import (
    CribbageArena,
    EuchreArena,
    GinRummyArena,
    HanabiArena,
)
from eslams.arenas.backgammon import BackgammonArena
from eslams.arenas.battleship import BattleshipArena
from eslams.arenas.checkers import CheckersArena
from eslams.arenas.chess import ChessArena
from eslams.arenas.classic_cards import (
    CrazyEightsArena,
    HeartsArena,
    SheddingCardGameArena,
    SpadesArena,
)
from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.control_arcade import (
    AlienShooterArena,
    BoxingStyleArena,
    CartPoleArena,
    IceHockeyStyleArena,
    MountainCarArena,
    PaddleBallArena,
)
from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.gridworld import CliffWalkingArena, FrozenLakeArena, TaxiArena
from eslams.arenas.hex import HexArena
from eslams.arenas.mancala import MancalaArena
from eslams.arenas.matrix_games import PrisonersDilemmaArena, RockPaperScissorsArena
from eslams.arenas.modern_control import (
    BipedalWalkerArena,
    CarRacingArena,
    LunarLanderArena,
)
from eslams.arenas.nine_mens_morris import NineMensMorrisArena
from eslams.arenas.othello import OthelloArena
from eslams.arenas.pentago import PentagoArena
from eslams.arenas.poker import (
    LeducHoldemArena,
    LimitTexasHoldemArena,
    NoLimitTexasHoldemArena,
)
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
registry.register(SheddingCardGameArena)
registry.register(CrazyEightsArena)
registry.register(HeartsArena)
registry.register(SpadesArena)
registry.register(GinRummyArena)
registry.register(EuchreArena)
registry.register(CribbageArena)
registry.register(HanabiArena)
registry.register(BackgammonArena)
registry.register(LeducHoldemArena)
registry.register(LimitTexasHoldemArena)
registry.register(NoLimitTexasHoldemArena)
registry.register(NineMensMorrisArena)
registry.register(CartPoleArena)
registry.register(MountainCarArena)
registry.register(PaddleBallArena)
registry.register(AlienShooterArena)
registry.register(BoxingStyleArena)
registry.register(IceHockeyStyleArena)
registry.register(LunarLanderArena)
registry.register(CarRacingArena)
registry.register(BipedalWalkerArena)
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
    "AlienShooterArena",
    "BackgammonArena",
    "BattleshipArena",
    "BipedalWalkerArena",
    "BlackjackArena",
    "BoxingStyleArena",
    "CarRacingArena",
    "CartPoleArena",
    "CheckersArena",
    "ChessArena",
    "CliffWalkingArena",
    "ConnectFourArena",
    "CribbageArena",
    "CrazyEightsArena",
    "EuchreArena",
    "FirstPriceSealedBidAuctionArena",
    "FrozenLakeArena",
    "GomokuArena",
    "GoofspielArena",
    "GinRummyArena",
    "HanabiArena",
    "HeartsArena",
    "HexArena",
    "IceHockeyStyleArena",
    "LeducHoldemArena",
    "LiarsDiceArena",
    "LimitTexasHoldemArena",
    "LunarLanderArena",
    "MancalaArena",
    "MountainCarArena",
    "NegotiationArena",
    "NineMensMorrisArena",
    "NoLimitTexasHoldemArena",
    "OthelloArena",
    "PaddleBallArena",
    "PentagoArena",
    "PrisonersDilemmaArena",
    "RockPaperScissorsArena",
    "SheddingCardGameArena",
    "SpadesArena",
    "TaxiArena",
    "TicTacToeArena",
    "UltimateTicTacToeArena",
    "registry",
]
