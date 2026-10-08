"""Generate real public replay pages for browser regression checks, without keys."""

import argparse
from pathlib import Path

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in registry.list():
        arena = registry.create(name)
        result = Runner().run(
            RunConfig(
                arena_id=name,
                seed=5,
                run_id=f"browser-{name}",
                agents=dict.fromkeys(arena.players, "first-legal"),
                output_dir=args.output / "artifacts" / name,
            )
        )
        render_replay_html(result.artifact_path, args.output / f"{name}.html")
    print("Generated 50 validated public replay pages")


if __name__ == "__main__":
    main()
