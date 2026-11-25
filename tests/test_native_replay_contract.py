from __future__ import annotations

import json
import runpy
from pathlib import Path
from zipfile import ZipFile

import pytest
from jsonschema import Draft202012Validator

from eslams.contracts.json_schema import export_schemas, no_secret_examples, schema_for_version
from eslams.contracts.versions import NATIVE_EVENT_SCHEMA_VERSION, NATIVE_MANIFEST_SCHEMA_VERSION
from eslams.native_artifact import verify_native_replay
from eslams.native_runner import NativeProfile, run_local_native
from eslams.native_scope_demo import NATIVE_SCOPE

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("game", sorted(NATIVE_SCOPE))
def test_native_source_all_arenas_validate_against_exported_public_shape(game):
    opts = ({"auction_authority": bytes(range(32))}
            if game == "first-price-sealed-bid-auction" else {})
    out = run_local_native(NativeProfile(game), "schema-compatibility", **opts)
    proof = verify_native_replay(out.contents)
    Draft202012Validator(schema_for_version(NATIVE_MANIFEST_SCHEMA_VERSION)).validate(proof.manifest)
    event = Draft202012Validator(schema_for_version(NATIVE_EVENT_SCHEMA_VERSION))
    for frame in proof.events:
        event.validate(frame)


def test_native_generated_types_and_full_example_use_public_shape(tmp_path):
    generated = runpy.run_path(str(_ROOT / "scripts/generate_native_replay_types.py"))
    assert generated["TYPES"].read_text() == generated["generated_typescript"]()
    assert generated["EXAMPLE"].read_text() == generated["generated_example"]()
    example = json.loads(generated["EXAMPLE"].read_text())
    one = tmp_path / "one"
    two = tmp_path / "two"
    assert [p.name for p in export_schemas(one)] == [p.name for p in export_schemas(two)]
    assert all(p.read_bytes() == (two / p.name).read_bytes() for p in one.iterdir())
    examples = no_secret_examples()
    assert examples[NATIVE_MANIFEST_SCHEMA_VERSION] == example["manifest"]
    assert examples[NATIVE_EVENT_SCHEMA_VERSION] == example["events"][0]
    draft = Draft202012Validator(schema_for_version(NATIVE_EVENT_SCHEMA_VERSION))
    sealed = next(row for row in example["events"] if row["kind"] == "sealed_action")
    assert not draft.is_valid({**sealed, "private_extra": "no"})
    assert not draft.is_valid({**sealed, "game_facts": {"pot": 0}})


def test_native_manifest_shape_does_not_accept_legacy_manifest():
    schema = Draft202012Validator(schema_for_version(NATIVE_MANIFEST_SCHEMA_VERSION))
    fixture = _ROOT / "fixtures/artifacts/local_tic_tac_toe.eslams"
    with ZipFile(fixture) as public:
        legacy = json.loads(public.read("manifest.json"))
    assert not schema.is_valid(legacy)
    with pytest.raises(ValueError, match="native replay contract"):
        verify_native_replay(fixture.read_bytes())
