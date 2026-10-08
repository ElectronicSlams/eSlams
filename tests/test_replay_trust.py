import pytest

from eslams.artifacts import ArtifactValidator
from eslams.cli import main
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner


def test_normal_replay_refuses_tampering_and_diagnostic_output_is_visibly_untrusted(tmp_path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    with (result.artifact_path / "traces/public_trace.jsonl").open(
        "a", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write('{"unexpected":"<script>untrusted</script>"}\n')
    assert ArtifactValidator().validate_report(result.artifact_path).valid is False
    output = tmp_path / "replay.html"
    with pytest.raises(ValueError, match="hash mismatch"):
        render_replay_html(result.artifact_path, output)
    assert not output.exists()
    assert main(["replay", str(result.artifact_path), "--output", str(output)]) == 1
    assert not output.exists()
    render_replay_html(result.artifact_path, output, diagnostic=True)
    text = output.read_text(encoding="utf-8")
    assert 'role="status" id="artifactTrust"' in text
    assert "DIAGNOSTIC — UNTRUSTED REPLAY" in text
    assert "hash mismatch" in text


def test_unsigned_content_is_validated_without_claiming_signature_authentication(tmp_path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path, archive=True))
    output = render_replay_html(result.artifact_path)
    assert "Content validated. Signature: unsigned." in output.read_text(encoding="utf-8")
    embedded = (result.expanded_path / "replay/index.html").read_text(encoding="utf-8")
    assert "validate the complete artifact before trusting it" in embedded


def test_signed_replay_requires_the_verification_key(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", "hex:" + "01" * 32)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    monkeypatch.delenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY")
    monkeypatch.delenv("RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY", raising=False)
    with pytest.raises(ValueError, match="runner_signature_unverified"):
        render_replay_html(result.artifact_path)
    assert not result.artifact_path.with_name(result.artifact_path.name + ".html").exists()


def test_replay_keeps_latest_aliases_usable(tmp_path):
    Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path, archive=True))
    output = render_replay_html(tmp_path / "latest.eslams", tmp_path / "latest.html")
    assert output.is_file()
