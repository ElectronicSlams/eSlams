"""Keep `.env.example` aligned with environment names read under `src/`.

Draft https://github.com/ElectronicSlams/eSlams/pull/40 adds `.env.example` and is
still open, so this file does not add a second copy (that would conflict).
Until that file is on the tree, the coverage test skips. The scanner test runs
on `main` and checks the names #40 documents are actually read in `src/`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# String literals treated as environment names. RUNNER_* here is the signing
# names passed to os.environ in this tree, not runner version constants.
TRACKED_ENV_NAME = re.compile(
    r"^(?:ESLAMS_[A-Z0-9_]+"
    r"|OPENAI_API_KEY"
    r"|ANTHROPIC_API_KEY"
    r"|GEMINI_API_KEY"
    r"|OPENROUTER_API_KEY"
    r"|AWS_BEARER_TOKEN_BEDROCK"
    r"|RUNNER_[A-Z0-9_]+)$"
)

# Names #40 lists, and that this tree reads. Update this when `src/` starts
# reading another tracked name, and list that name in `.env.example` too.
EXPECTED_ENV_NAMES = frozenset(
    {
        "ESLAMS_ARENA_SESSION_SECRET",
        "ESLAMS_ARENA_SESSION_KEY_ID",
        "ESLAMS_ENABLE_DEBUG_OBSERVATION",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "AWS_BEARER_TOKEN_BEDROCK",
        "RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY",
        "RUNNER_ARTIFACT_SIGNING_KEY_ID",
        "RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY",
        "RUNNER_SIGNING_KEY",
    }
)

# Discovered names that are test-only monkeypatches and must not be required in
# the contributor example. Empty today: src/eslams/fixtures.py sets the real
# RUNNER_ARTIFACT_SIGNING_* names, which contributors do configure. Names such
# as MISSING_PROVIDER_KEY are monkeypatched under tests/ and are not scanned.
TEST_ONLY_ENV_ALLOWLIST: frozenset[str] = frozenset()

_ENVIRON_METHODS = frozenset({"get", "pop", "setdefault"})
_PLACEHOLDER = re.compile(
    r"^(?:|your[-_a-z0-9]*|changeme|placeholder|todo|replace[-_]?me"
    r"|\.\.\.|<[^>]*>|x{3,}|example)$",
    re.IGNORECASE,
)
_SECRET_LIKE = re.compile(
    r"(?:sk-[A-Za-z0-9]|sk-ant-|AIza[0-9A-Za-z\-_]{10,}|AKIA[0-9A-Z]{16}"
    r"|ASIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]|github_pat_"
    r"|xox[baprs]-|base64:[A-Za-z0-9+/=]{8,}|hex:[0-9a-fA-F]{16,})"
)
_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def test_src_environ_names_match_documented_set() -> None:
    discovered = _discover_env_names(SRC_ROOT)
    stray_allowance = sorted(TEST_ONLY_ENV_ALLOWLIST - discovered)
    assert not stray_allowance, f"allowlist names are not read in src/: {stray_allowance}"
    required = discovered - TEST_ONLY_ENV_ALLOWLIST
    missing = sorted(EXPECTED_ENV_NAMES - required)
    extra = sorted(required - EXPECTED_ENV_NAMES)
    assert not missing, f"scanner missed environment names: {missing}"
    assert not extra, (
        "src/ reads environment names that are not in the documented set "
        f"(add them to .env.example and EXPECTED_ENV_NAMES): {extra}"
    )


def test_env_example_lists_discovered_names_without_secrets() -> None:
    if not ENV_EXAMPLE.is_file():
        pytest.skip(
            ".env.example is not in this tree. Draft #40 "
            "(https://github.com/ElectronicSlams/eSlams/pull/40) adds it and is "
            "still open, so this check skips instead of committing a second copy "
            "that would conflict with that PR. Once the file is present, every "
            "tracked name read in src/ must be listed with an empty or "
            "placeholder value."
        )

    declared = _parse_env_example(ENV_EXAMPLE)
    required = _discover_env_names(SRC_ROOT) - TEST_ONLY_ENV_ALLOWLIST
    assert required, "expected to find tracked environment names under src/"
    missing = sorted(required - declared.keys())
    assert not missing, ".env.example is missing environment names read in src/: " + ", ".join(
        missing
    )
    rejected = [
        f"{key}={value!r}"
        for key, value in sorted(declared.items())
        if not _is_empty_or_placeholder(value)
    ]
    assert not rejected, (
        ".env.example values must be empty or placeholders, with no secrets: "
        + ", ".join(rejected)
    )


def _discover_env_names(src_root: Path) -> set[str]:
    """Environment names read via os.environ / os.getenv / environ[ under src/."""
    found: set[str] = set()
    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bindings = _string_bindings(tree)
        for name, values in bindings.items():
            if name.endswith("_ENV"):
                found.update(value for value in values if TRACKED_ENV_NAME.fullmatch(value))
        dynamic = False
        for key_expr in _environ_key_exprs(tree):
            literal = _literal_string(key_expr)
            if literal is not None:
                if TRACKED_ENV_NAME.fullmatch(literal):
                    found.add(literal)
                continue
            if isinstance(key_expr, ast.Name):
                bound = {
                    value
                    for value in bindings.get(key_expr.id, ())
                    if TRACKED_ENV_NAME.fullmatch(value)
                }
                followed = _tracked_from_dict_lookup(tree, key_expr.id)
                if bound or followed:
                    found.update(bound)
                    found.update(followed)
                    continue
            dynamic = True
        if dynamic:
            found.update(_container_tracked_strings(tree))
    return found


def _string_bindings(tree: ast.AST) -> dict[str, set[str]]:
    bindings: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        literal = _literal_string(value) if value is not None else None
        if isinstance(target, ast.Name) and literal is not None:
            bindings.setdefault(target.id, set()).add(literal)
    return bindings


def _environ_key_exprs(tree: ast.AST) -> list[ast.expr]:
    keys: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if _is_os_getenv(func) and node.args:
                keys.append(node.args[0])
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in _ENVIRON_METHODS
                and _is_environ_receiver(func.value)
                and node.args
            ):
                keys.append(node.args[0])
        elif isinstance(node, ast.Subscript) and _is_environ_receiver(node.value):
            slice_node = node.slice
            if isinstance(slice_node, ast.expr):
                keys.append(slice_node)
    return keys


def _is_os_getenv(func: ast.AST) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )


def _is_environ_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name) and node.id == "environ":
        return True
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _tracked_from_dict_lookup(tree: ast.AST, name: str) -> set[str]:
    """Follow `name = SOME_DICT.get(...)` / `name = SOME_DICT[...]` to string values."""
    found: set[str] = set()
    for node in ast.walk(tree):
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
        dict_name = _dict_name_from_lookup(value) if value is not None else None
        if dict_name is not None:
            found.update(_tracked_strings_assigned_to(tree, dict_name))
    return found


def _dict_name_from_lookup(value: ast.expr) -> str | None:
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        if value.func.attr == "get" and isinstance(value.func.value, ast.Name):
            return value.func.value.id
    if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
        return value.value.id
    return None


def _tracked_strings_assigned_to(tree: ast.AST, name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
        if value is not None:
            found.update(_container_tracked_strings(value))
    return found


def _container_tracked_strings(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        elements: list[ast.expr] = []
        if isinstance(node, ast.Dict):
            elements.extend(value for value in node.values if value is not None)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elements.extend(node.elts)
        else:
            continue
        for element in elements:
            _collect_tracked_constant(element, found)
            if isinstance(element, (ast.List, ast.Tuple, ast.Set)):
                for nested in element.elts:
                    _collect_tracked_constant(nested, found)
    return found


def _collect_tracked_constant(node: ast.expr, found: set[str]) -> None:
    literal = _literal_string(node)
    if literal is not None and TRACKED_ENV_NAME.fullmatch(literal):
        found.add(literal)


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _parse_env_example(path: Path) -> dict[str, str]:
    """KEY=VALUE lines. Comments and blank lines are ignored."""
    declared: dict[str, str] = {}
    text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise AssertionError(f"{path}:{line_no}: expected KEY=VALUE, got {raw!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_inline_comment(value).strip()
        if not _KEY_RE.fullmatch(key):
            raise AssertionError(f"{path}:{line_no}: invalid environment name {key!r}")
        if key in declared:
            raise AssertionError(f"{path}:{line_no}: duplicate environment name {key}")
        declared[key] = value
    return declared


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return value[:index]
    return value


def _is_empty_or_placeholder(value: str) -> bool:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if _SECRET_LIKE.search(text):
        return False
    return _PLACEHOLDER.fullmatch(text) is not None
