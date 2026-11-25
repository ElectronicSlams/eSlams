"""Opt-in, keyless native runner. No provider, service or legacy dispatch path."""

from __future__ import annotations

import argparse
import json
import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path

from eslams.hashing import sha256_json
from eslams.native_artifact import (
    read_native_replay,
    render_native_replay,
    write_native_replay,
)
from eslams.native_checkpoint_demo import (
    TrustedBoundary,
    capture_settled_boundary,
    restore_settled_boundary,
)
from eslams.native_observation import PUBLIC_ENTROPY_ARENAS
from eslams.native_rounds_demo import (
    DemoArtifact,
    NativeObservation,
    NativeRoundArena,
    NativeState,
    Policy,
    run_native_match,
)
from eslams.native_rounds_demo import (
    NativeProfile as NativeProfile,
)
from eslams.native_scope_demo import NATIVE_SCOPE


def _first(view: NativeObservation) -> object:
    return view.legal[0]


def run_local_native(
    profile: NativeProfile,
    run_id: str,
    *,
    history: bool = True,
    auction_authority: bytes | None = None,
    private_authority: bytes | None = None,
    seat_policies: Mapping[str, Policy] | None = None,
    policy_ids: Mapping[str, str] | None = None,
    checkpoint_key: bytes | None = None,
    checkpoint: TrustedBoundary | None = None,
    save_checkpoint: Callable[[TrustedBoundary], None] | None = None,
) -> DemoArtifact:
    """One settled match with explicit private continuation custody, if configured."""
    arena = NativeRoundArena(
        profile, run_id, auction_authority=auction_authority, private_authority=private_authority,
    )
    if seat_policies is None:
        if policy_ids is not None:
            raise ValueError("policy identities require explicit native seat policies")
        ids = dict.fromkeys(arena.seats, "eslams.scripted.first-legal.v1")
        policies = dict.fromkeys(arena.seats, _first)
    else:
        if set(seat_policies) != set(arena.seats) or policy_ids is None or (
            set(policy_ids) != set(arena.seats) or any(
                type(v) is not str or not v or len(v) > 128 for v in policy_ids.values()
            )
        ):
            raise ValueError("explicit stable identity required for each native seat policy")
        if (
            profile.arena_id not in PUBLIC_ENTROPY_ARENAS and arena.auction_rules is None
            and private_authority is None
        ):
            raise ValueError("real hidden-information policies require private match authority")
        ids = dict(policy_ids)
        policies = dict(seat_policies)
    binding = sha256_json({
        "domain": "eslams.native.execution-binding.v1",
        "history": history, "agents": ids,
    })
    if (checkpoint is not None or save_checkpoint is not None) and (
        type(checkpoint_key) is not bytes or len(checkpoint_key) < 32
    ):
        raise ValueError("explicit private checkpoint key required")
    state = (
        restore_settled_boundary(arena, checkpoint, checkpoint_key, execution_binding=binding)
        if checkpoint is not None and checkpoint_key is not None else None
    )

    def hold(current: NativeState) -> None:
        if save_checkpoint is not None and checkpoint_key is not None:
            save_checkpoint(capture_settled_boundary(
                arena, current, checkpoint_key, execution_binding=binding,
            ))

    return run_native_match(
        arena, policies, history=history,
        start_state=state, on_boundary=hold if save_checkpoint is not None else None,
    )


def _custody_file(path: Path | None) -> bytes | None:
    if path is None:
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("auction authority requires a regular private local file")
    with path.open("rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or (os.name == "posix" and meta.st_mode & 0o077):
            raise ValueError("auction authority file must be owner-access only")
        raw = stream.read(129)
    if not 32 <= len(raw) <= 128:
        raise ValueError("auction authority must be 32–128 raw bytes")
    return raw


def add_native_cli(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    native = sub.add_parser("native", help="Run and replay opt-in native multi-unit matches.")
    commands = native.add_subparsers(dest="native_command", required=True)
    run = commands.add_parser("run", help="Run one keyless native match with first-legal seats.")
    run.add_argument("--arena", required=True, choices=sorted(NATIVE_SCOPE))
    run.add_argument("--run-id", required=True)
    run.add_argument("--blocks", type=int, default=1, help="Three native units per block.")
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--rotate-positions", action="store_true")
    run.add_argument("--memoryless", action="store_true")
    run.add_argument("--auction-authority-file", type=Path)
    run.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify", help="Validate a versioned native public journal.")
    verify.add_argument("artifact", type=Path)
    replay = commands.add_parser("replay", help="Render an offline native public event journal.")
    replay.add_argument("artifact", type=Path)
    replay.add_argument("--out", type=Path, required=True)


def native_cli(args: argparse.Namespace) -> int:
    if args.native_command == "verify":
        print(json.dumps(read_native_replay(args.artifact).summary(), sort_keys=True))
        return 0
    if args.native_command == "replay":
        print(json.dumps({"replay": str(render_native_replay(args.artifact, args.out))}))
        return 0
    if args.native_command != "run":
        raise ValueError("unrecognized native command")
    if args.out.suffix != ".eslams":
        raise ValueError("native output must end in .eslams")
    authority = _custody_file(args.auction_authority_file)
    artifact = run_local_native(
        NativeProfile(args.arena, args.blocks, args.seed, args.rotate_positions),
        args.run_id, history=not args.memoryless, auction_authority=authority,
    )
    output = write_native_replay(args.out, artifact.contents)
    summary = read_native_replay(output).summary()
    print(json.dumps({"artifact": str(output), **summary}, sort_keys=True))
    return 0 if summary["status"] == "complete" else 1
