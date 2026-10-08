import asyncio
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import FunctionAgent, ModelProviderAgent, _provider_semaphore
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.deadlines import action_deadline
from eslams.http_io import TotalTimeout, bounded_post
from eslams.runner import RunConfig, Runner


@contextmanager
def _server(mode):
    disconnected = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", "0")))
            body = b'{"action":0}'
            try:
                if mode == "headers":
                    time.sleep(0.7)
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                if mode == "trickle":
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.08)
                else:
                    self.wfile.write(body)
                    self.wfile.flush()
                if self.rfile.read(1) == b"":
                    disconnected.set()
            except (BrokenPipeError, ConnectionResetError):
                disconnected.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", disconnected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


@pytest.mark.parametrize("mode", ["headers", "trickle"])
def test_total_http_deadline_cancels_slow_headers_and_trickled_body_in_worker(mode):
    with _server(mode) as (url, disconnected):
        failures = []

        def invoke():
            start = time.monotonic()
            timeout = TotalTimeout(0.25, connect=2, read=2, deadline=start + 0.25)
            try:
                bounded_post(url, headers={}, json={}, timeout=timeout)
            except httpx.TimeoutException:
                failures.append(time.monotonic() - start)

        worker = threading.Thread(target=invoke)
        worker.start()
        worker.join(timeout=1)
        assert not worker.is_alive() and len(failures) == 1
        assert failures[0] < 0.8
        # Cancellation closes the socket rather than just abandoning a read thread.
        assert disconnected.wait(1.5)


def test_http_bridge_works_inside_an_existing_event_loop_and_after_cancelled_calls():
    with _server("fast") as (url, _):

        async def invoke():
            return bounded_post(url, headers={}, json={}, timeout=1).json()

        assert asyncio.run(invoke()) == {"action": 0}
        assert bounded_post(url, headers={}, json={}, timeout=1).json() == {"action": 0}


def test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-local-key")
    with _server("trickle") as (url, _):
        agent = ModelProviderAgent(
            "openai",
            "gpt-test",
            "OPENAI_API_KEY",
            runtime_config=ProviderRuntimeConfig(
                timeout_ms=250,
                read_timeout_ms=2000,
                gateway_base_url=url,
                gateway_mode="generic_base_url",
            ),
        )
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            agent.act(_request())
        assert time.monotonic() - start < 0.8
        assert agent.last_receipt["outcome"] == "provider_timeout"
        assert len(agent.attempt_receipts) == 1
    # A full concurrency slot cannot wait beyond the same elapsed attempt deadline.
    agent = ModelProviderAgent(
        "openai",
        "queue-fixture",
        "OPENAI_API_KEY",
        runtime_config=ProviderRuntimeConfig(timeout_ms=50),
    )
    semaphore = _provider_semaphore(agent.runtime_config, "openai:queue-fixture")
    semaphore.acquire()
    try:
        monkeypatch.setattr(
            "eslams.agents.bounded_post",
            lambda *a, **k: pytest.fail("queue should not issue a request"),
        )
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            agent.act(_request())
        assert time.monotonic() - start < 0.4
        assert agent.last_receipt["outcome"] == "provider_timeout"
    finally:
        semaphore.release()
    from eslams.agents import _sleep_before_retry

    with action_deadline(50), pytest.raises(TimeoutError, match="action deadline"):
        _sleep_before_retry(ProviderRuntimeConfig(retry_backoff_ms=100))


@pytest.mark.parametrize("worker_context", [True, False])
def test_runner_bounds_worker_and_no_alarm_calls_quarantines_late_actions(
    tmp_path, monkeypatch, worker_context
):
    release = threading.Event()
    entered = threading.Event()
    finished = threading.Event()
    calls = []

    def slow(request):
        calls.append(1)
        entered.set()
        try:
            release.wait(2)
            request.observation["late-mutated"] = True
            return request.legal_actions[0]
        finally:
            finished.set()

    agent = FunctionAgent(slow)
    if not worker_context:
        monkeypatch.setattr("eslams.runner._alarm_supported", lambda: False)
    results = []

    def run():
        start = time.monotonic()
        results.append(
            (
                Runner().run(
                    RunConfig(
                        arena_id="tic-tac-toe",
                        agent_1=agent,
                        time_budget_ms=50,
                        output_dir=tmp_path / "first",
                    )
                ),
                time.monotonic() - start,
            )
        )

    try:
        if worker_context:
            worker = threading.Thread(target=run)
            worker.start()
            worker.join(timeout=1)
            assert not worker.is_alive()
        else:
            run()
        assert entered.is_set() and len(results) == 1
        result, elapsed = results[0]
        assert elapsed < 0.8 and "provider_timeout" in result.score.invalid_reason
        assert result.score.match_valid_for_scoring is False
        assert ArtifactValidator().validate_report(result.artifact_path).valid
        files = {
            path: path.read_bytes() for path in result.artifact_path.rglob("*") if path.is_file()
        }
        # Reusing an unfinished callback must not start another concurrent call.
        next_result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                agent_1=agent,
                time_budget_ms=50,
                output_dir=tmp_path / "second",
            )
        )
        assert "provider_timeout" in next_result.score.invalid_reason and len(calls) == 1
        release.set()
        assert finished.wait(1)
        assert files == {path: path.read_bytes() for path in files}
        assert all(
            "late-mutated" not in text.decode("utf-8", errors="ignore") for text in files.values()
        )
        score = json.loads((result.artifact_path / "scores/score.json").read_text())
        assert not score["match_valid_for_scoring"]
    finally:
        release.set()
