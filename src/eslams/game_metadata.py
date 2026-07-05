"""Core 0.5 game topology, surface, help, render, and animation metadata."""

from __future__ import annotations

from typing import Any

from eslams.contracts.animation import GameAnimationSpec, validate_animation_spec
from eslams.contracts.help import GameHelp, validate_help
from eslams.contracts.render import GameRenderSpec, validate_render_spec
from eslams.contracts.result import result_contract_for_topology
from eslams.contracts.surface import GameSurface, validate_surface
from eslams.contracts.topology import (
    GameTopology,
    head_to_head_topology,
    multi_seat_topology,
    solo_score_topology,
    validate_topology,
)
from eslams.public_catalogue import PublicGameMetadata

SOLO_SCORE_GAMES = {
    "blackjack",
    "taxi",
    "frozen-lake",
    "cliff-walking",
    "cartpole",
    "mountain-car",
    "lunar-lander",
    "car-racing",
    "bipedal-walker",
    "paddle-ball",
    "alien-shooter",
    "boxing-style-arena",
    "ice-hockey-style-arena",
}

MAIN_ARENA_GAMES = {
    "tic-tac-toe",
    "connect-four",
    "othello",
    "chess",
    "go",
    "gomoku",
    "hex",
    "ultimate-tic-tac-toe",
    "battleship",
    "goofspiel",
    "rock-paper-scissors",
    "prisoners-dilemma",
    "first-price-sealed-bid-auction",
}

ADVANCED_HEAD_TO_HEAD_GAMES = {
    "checkers",
    "shogi",
    "xiangqi",
    "mancala",
    "nine-mens-morris",
    "pentago",
    "backgammon",
    "gin-rummy",
    "cribbage",
    "liars-dice",
    "bargaining",
    "negotiation",
    "crazy-eights",
    "euchre",
    "hanabi",
    "hearts",
    "shedding-card-game",
    "spades",
}

MULTI_SEAT_GAMES = {
    "leduc-holdem",
    "limit-texas-holdem",
    "no-limit-texas-holdem",
    "mahjong",
    "dou-dizhu",
    "bridge",
}

HIDDEN_INFO_GAMES = {
    "battleship",
    "goofspiel",
    "rock-paper-scissors",
    "first-price-sealed-bid-auction",
    "blackjack",
    "gin-rummy",
    "cribbage",
    "liars-dice",
    "leduc-holdem",
    "limit-texas-holdem",
    "no-limit-texas-holdem",
    "mahjong",
    "dou-dizhu",
    "bridge",
    "hearts",
    "spades",
    "euchre",
    "crazy-eights",
    "hanabi",
    "shedding-card-game",
}

BOARD_SIZES: dict[str, dict[str, int]] = {
    "tic-tac-toe": {"rows": 3, "cols": 3},
    "connect-four": {"rows": 6, "cols": 7},
    "othello": {"rows": 8, "cols": 8},
    "chess": {"rows": 8, "cols": 8},
    "go": {"rows": 9, "cols": 9},
    "gomoku": {"rows": 15, "cols": 15},
    "ultimate-tic-tac-toe": {"rows": 9, "cols": 9},
    "checkers": {"rows": 8, "cols": 8},
    "shogi": {"rows": 9, "cols": 9},
    "xiangqi": {"rows": 10, "cols": 9},
}

RENDER_FAMILY_BY_GAME = {
    "tic-tac-toe": "grid_3x3",
    "connect-four": "connect_four",
    "othello": "square_board",
    "chess": "square_board",
    "go": "go_board",
    "gomoku": "go_board",
    "hex": "hex_board",
    "ultimate-tic-tac-toe": "grid_3x3",
    "battleship": "square_board",
    "prisoners-dilemma": "payoff_matrix",
    "rock-paper-scissors": "payoff_matrix",
    "first-price-sealed-bid-auction": "auction_panel",
    "liars-dice": "dice_table",
}

CARD_TABLE_RENDERERS = {
    "blackjack",
    "gin-rummy",
    "cribbage",
    "goofspiel",
    "leduc-holdem",
    "limit-texas-holdem",
    "no-limit-texas-holdem",
    "mahjong",
    "dou-dizhu",
    "bridge",
    "hearts",
    "spades",
    "euchre",
    "crazy-eights",
    "hanabi",
    "shedding-card-game",
}


def core_0_5_metadata(
    public: PublicGameMetadata,
    *,
    renderer_family: str,
    replay_available: bool,
) -> dict[str, Any]:
    topology = topology_for_game(public).to_dict()
    surface = surface_for_game(public.game_id).to_dict()
    result_contract = result_contract_for_topology(topology).to_dict()
    help_payload = help_for_game(public, topology).to_dict()
    render_spec = render_spec_for_game(
        public, topology, replay_available=replay_available
    ).to_dict()
    animation_spec = animation_spec_for_game(public, render_spec, renderer_family).to_dict()
    return {
        "topology": topology,
        "surface": surface,
        "resultContract": result_contract,
        "help": help_payload,
        "renderSpec": render_spec,
        "animationSpec": animation_spec,
        "validationErrors": validate_core_0_5_metadata(
            topology=topology,
            surface=surface,
            help=help_payload,
            render_spec=render_spec,
            animation_spec=animation_spec,
        ),
    }


def topology_for_game(public: PublicGameMetadata) -> GameTopology:
    if public.game_id in SOLO_SCORE_GAMES:
        survival_games = {"cartpole", "mountain-car", "bipedal-walker"}
        score_type = "survival" if public.game_id in survival_games else "reward"
        return solo_score_topology(score_type=score_type)
    if public.game_id in MULTI_SEAT_GAMES:
        return multi_seat_topology(
            default_players=public.players,
            score_type=_multi_seat_score_type(public.game_id),
        )
    return head_to_head_topology(
        draw_allowed=_draw_allowed(public.game_id),
        score_type=_head_to_head_score_type(public.game_id),
    )


def surface_for_game(game_id: str) -> GameSurface:
    if game_id in SOLO_SCORE_GAMES:
        return GameSurface(
            arena="disabled",
            battlefield="solo_benchmark",
            benchmark="enabled",
            official="eligible",
            public_reason="This game is a solo score benchmark, not a human-vs-model Arena match.",
        )
    if game_id in MAIN_ARENA_GAMES:
        return GameSurface(
            arena="main_arena",
            battlefield="head_to_head",
            benchmark="disabled",
            official="eligible",
        )
    if game_id in ADVANCED_HEAD_TO_HEAD_GAMES:
        return GameSurface(
            arena="advanced_arena",
            battlefield="head_to_head",
            benchmark="disabled",
            official="eligible",
            public_reason=(
                "Advanced Arena game; rules and interaction polish are required before "
                "default placement."
            ),
        )
    return GameSurface(
        arena="table_mode_pending",
        battlefield="multi_seat",
        benchmark="disabled",
        official="eligible",
    )


def help_for_game(public: PublicGameMetadata, topology: dict[str, Any]) -> GameHelp:
    override = _HELP_OVERRIDES.get(public.game_id)
    if override is not None:
        return override
    mode = str(topology["mode"])
    hidden = (
        "Some information is hidden until actions reveal it."
        if public.game_id in HIDDEN_INFO_GAMES
        else None
    )
    if mode == "solo_score":
        return GameHelp(
            objective=f"Control the agent in {public.name} to maximize the benchmark score.",
            turn_rules=("One evaluated player chooses actions against the environment.",),
            legal_action_summary="Choose one legal control action from the current state.",
            scoring_summary="The primary score is the episode reward or task completion score.",
            win_loss_draw_summary=(
                "There is no opponent and no winner; results are reported as scores."
            ),
            hidden_info_summary=hidden,
            first_move_tip="Prefer actions that keep the episode stable and gather reward.",
            example_actions=(
                {
                    "token": "0",
                    "label": "Action 0",
                    "explanation": "Applies the first legal environment control action.",
                },
            ),
        )
    if mode == "multi_seat":
        return GameHelp(
            objective=(
                f"Play {public.name} from an explicit table seat and finish with the "
                "best placement or score."
            ),
            turn_rules=("Seats act in table order according to the variant rules.",),
            legal_action_summary="Choose a legal table action for the active seat.",
            scoring_summary=(
                "Final placements, points, chips, or role results are reported by the "
                "result contract."
            ),
            win_loss_draw_summary=(
                "Multi-seat results name the winning seat and placement order when available."
            ),
            hidden_info_summary=hidden,
            first_move_tip=(
                "Check your seat, role, and visible table state before choosing an action."
            ),
            example_actions=(
                {
                    "token": "pass",
                    "label": "Pass",
                    "explanation": "Declines the current opportunity when the rules allow it.",
                },
            ),
        )
    return GameHelp(
        objective=f"Win {public.name} by making legal moves that satisfy the game objective.",
        turn_rules=(
            "Player 1 and Player 2 alternate or commit actions according to the "
            "variant rules.",
        ),
        legal_action_summary="Choose one legal action shown by the current game state.",
        scoring_summary="The result contract reports winner, draw, points, and final scores.",
        win_loss_draw_summary="A winner is reported unless the game rules allow a draw.",
        hidden_info_summary=hidden,
        first_move_tip=(
            "Start with a central, flexible, or information-gathering action when available."
        ),
        example_actions=(
            {
                "token": "0",
                "label": "First legal action",
                "explanation": "Applies a legal action token from the current state.",
            },
        ),
    )


def render_spec_for_game(
    public: PublicGameMetadata,
    topology: dict[str, Any],
    *,
    replay_available: bool,
) -> GameRenderSpec:
    if public.game_id in RENDER_FAMILY_BY_GAME:
        renderer_family = RENDER_FAMILY_BY_GAME[public.game_id]
    elif public.game_id in SOLO_SCORE_GAMES:
        renderer_family = "control_benchmark"
    elif public.game_id in CARD_TABLE_RENDERERS:
        renderer_family = "card_table"
    elif public.category == "gametheory":
        renderer_family = "economic_panel"
    else:
        renderer_family = "square_board"
    mode = str(topology["mode"])
    seat_layout = (
        "solo_panel"
        if mode == "solo_score"
        else "table_ring"
        if mode == "multi_seat"
        else "two_sides"
    )
    if public.game_id == "bridge":
        seat_layout = "compass"
    return GameRenderSpec(
        renderer_family=renderer_family,
        board_size=BOARD_SIZES.get(public.game_id),
        seat_layout=seat_layout,
        hidden_info=public.game_id in HIDDEN_INFO_GAMES,
        supports_replay=replay_available,
        supports_live_frame=mode != "solo_score" or public.game_id in SOLO_SCORE_GAMES,
    )


def animation_spec_for_game(
    public: PublicGameMetadata,
    render_spec: dict[str, Any],
    core_renderer_family: str,
) -> GameAnimationSpec:
    family = _ANIMATION_FAMILY_BY_GAME.get(public.game_id)
    if family is None:
        family = str(render_spec.get("rendererFamily") or core_renderer_family).replace("_", "-")
    return GameAnimationSpec(
        family=family,
        default_move_ms=320 if public.game_id == "connect-four" else 220,
        default_reveal_ms=300 if public.game_id in HIDDEN_INFO_GAMES else 180,
        default_result_ms=520,
        reduced_motion_behavior="static_final_state",
        events={"move": {"kind": family}, "result": {"kind": "result_summary"}},
    )


def validate_core_0_5_metadata(
    *,
    topology: dict[str, Any],
    surface: dict[str, Any],
    help: dict[str, Any],
    render_spec: dict[str, Any],
    animation_spec: dict[str, Any],
) -> list[str]:
    return [
        *validate_topology(topology),
        *validate_surface(surface),
        *validate_help(help),
        *validate_render_spec(render_spec),
        *validate_animation_spec(animation_spec),
    ]


def _draw_allowed(game_id: str) -> bool:
    return game_id not in {"hex", "goofspiel", "first-price-sealed-bid-auction"}


def _head_to_head_score_type(game_id: str) -> str:
    if game_id in {"goofspiel", "first-price-sealed-bid-auction", "bargaining", "negotiation"}:
        return "points"
    return "win_loss_draw"


def _multi_seat_score_type(game_id: str) -> str:
    if game_id in {"leduc-holdem", "limit-texas-holdem", "no-limit-texas-holdem"}:
        return "chips"
    if game_id in {"bridge", "hearts", "spades", "euchre"}:
        return "points"
    return "placement"


_ANIMATION_FAMILY_BY_GAME = {
    "tic-tac-toe": "tic_tac_toe_mark",
    "connect-four": "connect_four_drop",
    "othello": "othello_flip",
    "chess": "chess_piece_move",
    "go": "go_stone_place",
    "gomoku": "gomoku_line",
    "hex": "hex_path",
    "ultimate-tic-tac-toe": "ultimate_tic_tac_toe_board",
    "battleship": "battleship_shot",
    "goofspiel": "goofspiel_reveal",
    "rock-paper-scissors": "simultaneous_reveal",
    "prisoners-dilemma": "payoff_matrix_reveal",
    "first-price-sealed-bid-auction": "sealed_bid_reveal",
}

_HELP_OVERRIDES: dict[str, GameHelp] = {
    "tic-tac-toe": GameHelp(
        objective="Place three marks in a row before the opponent does.",
        turn_rules=("Players alternate placing one mark in an empty cell.",),
        legal_action_summary="Choose any empty cell.",
        scoring_summary="Three in a row wins; a full board without three is a draw.",
        win_loss_draw_summary="The result is a win, loss, or draw.",
        hidden_info_summary=None,
        first_move_tip="The center and corners give the most future lines.",
        example_actions=(
            {
                "token": "4",
                "label": "Center cell",
                "explanation": "Places your mark in the center cell.",
            },
        ),
    ),
    "connect-four": GameHelp(
        objective="Connect four discs in a row before the opponent does.",
        turn_rules=("Players alternate dropping one disc into a non-full column.",),
        legal_action_summary="Choose a column where a disc can fall.",
        scoring_summary="First four-in-a-row wins; a full board without four is a draw.",
        win_loss_draw_summary="The result is a win, loss, or draw.",
        hidden_info_summary=None,
        first_move_tip="Center columns usually create more threats.",
        example_actions=(
            {
                "token": "3",
                "label": "Drop in column 4",
                "explanation": "Drops a disc into the fourth column.",
            },
        ),
    ),
    "othello": GameHelp(
        objective="Finish with more discs than the opponent by flipping bracketed lines.",
        turn_rules=("Players alternate placing discs that flip at least one opponent disc.",),
        legal_action_summary="Choose a legal empty square that brackets opponent discs.",
        scoring_summary="Final disc counts decide the winner.",
        win_loss_draw_summary="Higher final disc count wins; equal counts draw.",
        hidden_info_summary=None,
        first_move_tip="Corners are stable; avoid giving them away early.",
        example_actions=(
            {
                "token": "d3",
                "label": "Place at d3",
                "explanation": "Places a disc and flips any bracketed line.",
            },
        ),
    ),
    "battleship": GameHelp(
        objective="Sink all opponent ships before yours are sunk.",
        turn_rules=("Players alternate firing at an unshot target cell.",),
        legal_action_summary="Choose a target coordinate that has not been fired on.",
        scoring_summary="The first player to sink every enemy ship wins.",
        win_loss_draw_summary="The result names the surviving fleet or terminal reason.",
        hidden_info_summary="Ship locations are hidden until hits reveal them.",
        first_move_tip="After a hit, probe neighboring cells.",
        example_actions=(
            {
                "token": "fire:B4",
                "label": "Fire at B4",
                "explanation": "Attacks the B4 target cell.",
            },
        ),
    ),
    "prisoners-dilemma": GameHelp(
        objective="Choose a strategy that maximizes payoff against the opponent's choice.",
        turn_rules=("Both players commit a choice, then the payoff cell is revealed.",),
        legal_action_summary="Choose cooperate or defect.",
        scoring_summary="The payoff matrix determines each player's points.",
        win_loss_draw_summary="Higher payoff wins for the round; equal payoff is a draw.",
        hidden_info_summary="The opponent's choice is hidden until simultaneous reveal.",
        first_move_tip="Think about whether the opponent is likely to cooperate.",
        example_actions=(
            {
                "token": "cooperate",
                "label": "Cooperate",
                "explanation": "Commits to the cooperative action.",
            },
        ),
    ),
    "first-price-sealed-bid-auction": GameHelp(
        objective="Bid for the item without paying more than its value to you.",
        turn_rules=("Both bidders submit sealed bids, then bids reveal together.",),
        legal_action_summary="Choose a legal bid amount.",
        scoring_summary="Highest bid wins and utility is value minus bid.",
        win_loss_draw_summary=(
            "Highest utility or winning bid determines the result according to the variant."
        ),
        hidden_info_summary="Private values and bids are hidden until reveal.",
        first_move_tip="Shade your bid below private value when possible.",
        example_actions=(
            {"token": "bid:5", "label": "Bid 5", "explanation": "Submits a sealed bid of 5."},
        ),
    ),
}
