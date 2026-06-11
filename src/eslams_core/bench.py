"""Compatibility entrypoint for ``python -m eslams_core.bench``."""

from __future__ import annotations

from eslams.bench import main

if __name__ == "__main__":
    raise SystemExit(main())
