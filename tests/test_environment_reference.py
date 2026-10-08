"""The reference covers real source configuration names without carrying values."""

import ast
from pathlib import Path


def test_environment_reference_covers_literals_and_named_environment_constants():
    root = Path(__file__).resolve().parents[1]
    names = set()
    for path in (root / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and any(
                    isinstance(target, ast.Name) and target.id.endswith("_ENV")
                    for target in node.targets
                )
                and isinstance(node.value.value, str)
            ):
                names.add(node.value.value)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("getenv", "get", "pop", "setdefault")
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                argument = node.args[0].value
                if isinstance(argument, str) and argument.startswith(("ESLAMS_", "RUNNER_")):
                    names.add(argument)
    assignments = [
        line.split("=", 1)
        for line in (root / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert all(value == "" for _, value in assignments)
    assert names <= {name for name, _ in assignments}
    assert len(assignments) == len({name for name, _ in assignments})
