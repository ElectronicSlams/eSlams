import pytest

from eslams.agents import FunctionAgent
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("key_id", ["", " ", "bad id", "newline\n", "x" * 129])
def test_invalid_signing_key_id_fails_before_calling_agents_or_creating_output(
    tmp_path, monkeypatch, key_id
):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", "hex:" + "01" * 32)
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_KEY_ID", key_id)
    agent = FunctionAgent(lambda _: pytest.fail("must not call an agent"))
    with pytest.raises(ValueError, match="SIGNING_KEY_ID must be a nonempty token"):
        Runner().run(RunConfig(arena_id="tic-tac-toe", agent_1=agent, output_dir=tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_valid_explicit_key_id_and_default_produce_verifiable_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", "hex:" + "01" * 32)
    for key_id in ["local-valid-key", None]:
        if key_id is None:
            monkeypatch.delenv("RUNNER_ARTIFACT_SIGNING_KEY_ID")
        else:
            monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_KEY_ID", key_id)
        result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
        report = ArtifactValidator().validate_report(result.artifact_path)
        assert report.valid
        assert report.signature.verified
        assert report.signature.key_id == (key_id or "runner-artifact-env-key")
