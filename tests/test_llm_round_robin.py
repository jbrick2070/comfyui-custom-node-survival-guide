"""Tests for the llm_round_robin addon.

Coverage:
  - YAML config loader (with PyYAML and the stdlib fallback)
  - Cross-platform env var resolver (POSIX-fallback path)
  - Probe parsers (OpenAI / Gemini / NVIDIA-compatible bodies)
  - Probe-first prune (intersect ladder with live ids)
  - Capability filter (--needs)
  - Provider call adapters with stubbed fetcher
  - Typed error classification (model_not_found vs endpoint_mismatch
    vs permission vs rate_limit vs transport)
  - Ladder-staleness warning
  - End-to-end runner with all-stub HTTP

These tests are pure-Python: no real network calls, no API keys, no
file fixtures outside this repo.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from llm_round_robin import config, env, errors, probe, providers, runner


REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────
# Config / YAML loader
# ─────────────────────────────────────────────────────────────────


class TestConfigLoader:
    def test_bundled_ladders_yaml_loads(self):
        """The shipped config must parse cleanly."""
        ladders, warnings = config.load_ladders(
            REPO_ROOT / "llm_round_robin" / "config" / "ladders.yaml"
        )
        assert "openai" in ladders
        assert "gemini" in ladders
        assert "nvidia" in ladders
        # Every provider has at least one model, and the first OpenAI
        # rung is on /v1/responses
        assert ladders["openai"].models[0].endpoint == "responses"
        # warnings list shouldn't include the staleness warning unless
        # the bundled date is >60 days old
        for w in warnings:
            assert "unknown capability" not in w

    def test_missing_config_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            config.load_ladders(tmp_path / "nope.yaml")

    def test_stale_ladder_emits_warning(self, tmp_path):
        cfg = tmp_path / "stale.yaml"
        cfg.write_text(
            "last_reviewed: 2020-01-01\n"
            "providers:\n"
            "  openai:\n"
            "    endpoint_default: responses\n"
            "    models:\n"
            "      - id: gpt-old\n"
            "        capabilities: [text]\n",
            encoding="utf-8",
        )
        ladders, warnings = config.load_ladders(cfg, staleness_days=60)
        assert any("stale" in w.lower() or "days old" in w for w in warnings), (
            f"expected staleness warning, got: {warnings}"
        )

    def test_unknown_capability_warns_but_keeps_model(self, tmp_path):
        cfg = tmp_path / "unknown_cap.yaml"
        cfg.write_text(
            "last_reviewed: 2026-05-01\n"
            "providers:\n"
            "  openai:\n"
            "    endpoint_default: chat\n"
            "    models:\n"
            "      - id: gpt-test\n"
            "        capabilities: [text, telepathy]\n",
            encoding="utf-8",
        )
        ladders, warnings = config.load_ladders(cfg)
        assert ladders["openai"].models[0].id == "gpt-test"
        assert any("telepathy" in w for w in warnings)

    def test_mini_yaml_parser_handles_documented_shape(self):
        """The bundled stdlib-fallback parser should handle our shape
        even if PyYAML is absent. We exercise it directly so the test
        passes regardless of pyyaml availability."""
        text = (
            "last_reviewed: 2026-05-01\n"
            "providers:\n"
            "  openai:\n"
            "    endpoint_default: responses\n"
            "    models:\n"
            "      - id: gpt-x\n"
            "        endpoint: responses\n"
            "        capabilities: [text, tools]\n"
            "      - id: gpt-y\n"
            "        endpoint: chat\n"
            "        capabilities: [text]\n"
        )
        parsed = config._mini_yaml_parse(text)
        assert isinstance(parsed["last_reviewed"], datetime.date)
        assert parsed["providers"]["openai"]["endpoint_default"] == "responses"
        models = parsed["providers"]["openai"]["models"]
        assert len(models) == 2
        assert models[0]["id"] == "gpt-x"
        assert models[0]["capabilities"] == ["text", "tools"]


# ─────────────────────────────────────────────────────────────────
# Capability filter
# ─────────────────────────────────────────────────────────────────


class TestNeedsFilter:
    def _ladder(self):
        return config.Ladder(
            provider="openai",
            endpoint_default="responses",
            models=(
                config.ModelEntry(
                    id="text-only",
                    endpoint="chat",
                    capabilities=("text",),
                ),
                config.ModelEntry(
                    id="reasoning-pro",
                    endpoint="responses",
                    capabilities=("text", "reasoning"),
                ),
                config.ModelEntry(
                    id="full-mm",
                    endpoint="responses",
                    capabilities=("text", "vision", "tools", "reasoning"),
                ),
            ),
        )

    def test_no_needs_returns_unchanged(self):
        lad = self._ladder()
        assert lad.filter_for_needs(None) is lad
        assert lad.filter_for_needs([]).models == lad.models

    def test_single_need_filters(self):
        lad = self._ladder()
        kept = lad.filter_for_needs(["reasoning"])
        assert [m.id for m in kept.models] == ["reasoning-pro", "full-mm"]

    def test_multi_need_filters(self):
        lad = self._ladder()
        kept = lad.filter_for_needs(["reasoning", "vision"])
        assert [m.id for m in kept.models] == ["full-mm"]

    def test_unsatisfiable_filter_yields_empty(self):
        lad = self._ladder()
        kept = lad.filter_for_needs(["reasoning", "vision", "tools", "telepathy"])
        assert kept.models == ()


# ─────────────────────────────────────────────────────────────────
# Env var resolver
# ─────────────────────────────────────────────────────────────────


class TestEnvVar:
    def test_posix_fallback_reads_environ(self, monkeypatch):
        monkeypatch.setenv("MY_ROUND_ROBIN_TEST_KEY", "sk-deadbeef")
        # Force the POSIX path by monkey-patching sys.platform — the
        # winreg call would fail on a non-Windows host anyway, but the
        # explicit override makes the test deterministic on Windows
        # too.
        monkeypatch.setattr("llm_round_robin.env.sys.platform", "linux")
        value = env.read_env_var(
            "MY_ROUND_ROBIN_TEST_KEY", expected_prefix="sk-"
        )
        assert value == "sk-deadbeef"

    def test_missing_var_raises_with_help(self, monkeypatch):
        monkeypatch.delenv("MY_ROUND_ROBIN_TEST_NOPE", raising=False)
        monkeypatch.setattr("llm_round_robin.env.sys.platform", "linux")
        with pytest.raises(RuntimeError) as ei:
            env.read_env_var("MY_ROUND_ROBIN_TEST_NOPE")
        assert "not set" in str(ei.value)
        assert "export" in str(ei.value).lower()

    def test_prefix_mismatch_raises(self, monkeypatch):
        monkeypatch.setenv("MY_RR_KEY", "wrongprefix-zzz")
        monkeypatch.setattr("llm_round_robin.env.sys.platform", "linux")
        with pytest.raises(RuntimeError) as ei:
            env.read_env_var("MY_RR_KEY", expected_prefix="sk-")
        assert "prefix" in str(ei.value).lower()


# ─────────────────────────────────────────────────────────────────
# Probe parsing + ladder pruning
# ─────────────────────────────────────────────────────────────────


def _stub_fetcher(body_bytes: bytes):
    def f(req):
        return body_bytes
    return f


def _http_error(code: int, body: str = ""):
    def f(req):
        # Construct a minimal HTTPError with a readable body
        fp = io.BytesIO(body.encode("utf-8"))
        raise urllib.error.HTTPError(
            req.full_url, code, "Test", hdrs={}, fp=fp
        )
    return f


class TestProbe:
    def test_openai_probe_parses_data_array(self):
        body = json.dumps(
            {"data": [{"id": "gpt-5.5"}, {"id": "gpt-4o-mini"}]}
        ).encode("utf-8")
        ladder = config.Ladder("openai", "responses", ())
        out = probe.probe_provider(
            ladder, api_key="sk-x", fetcher=_stub_fetcher(body)
        )
        assert out.ok is True
        assert "gpt-5.5" in out.live_ids
        assert "gpt-4o-mini" in out.live_ids

    def test_gemini_probe_strips_models_prefix(self):
        body = json.dumps(
            {
                "models": [
                    {"name": "models/gemini-3.1-pro-preview"},
                    {"name": "models/gemini-3-flash-preview"},
                ]
            }
        ).encode("utf-8")
        ladder = config.Ladder("gemini", "generate_content", ())
        out = probe.probe_provider(
            ladder, api_key="x", fetcher=_stub_fetcher(body)
        )
        assert out.ok
        assert "gemini-3.1-pro-preview" in out.live_ids
        assert "models/gemini-3-flash-preview" not in out.live_ids

    def test_nvidia_probe_uses_openai_compatible_shape(self):
        body = json.dumps(
            {"data": [{"id": "nvidia/llama-3.3-nemotron-super-49b-v1.5"}]}
        ).encode("utf-8")
        ladder = config.Ladder("nvidia", "chat", ())
        out = probe.probe_provider(
            ladder, api_key="x", fetcher=_stub_fetcher(body)
        )
        assert out.ok
        assert "nvidia/llama-3.3-nemotron-super-49b-v1.5" in out.live_ids

    def test_probe_http_error_marks_not_ok(self):
        ladder = config.Ladder("openai", "responses", ())
        out = probe.probe_provider(
            ladder, api_key="sk-x", fetcher=_http_error(401, "bad key")
        )
        assert out.ok is False
        assert "401" in out.error

    def test_prune_keeps_only_live(self):
        ladder = config.Ladder(
            provider="openai",
            endpoint_default="responses",
            models=(
                config.ModelEntry("gpt-5.5", "responses", ("text",)),
                config.ModelEntry("gpt-deprecated", "responses", ("text",)),
                config.ModelEntry("gpt-4o-mini", "chat", ("text",)),
            ),
        )
        live = probe.LiveProbe(
            provider="openai",
            ok=True,
            live_ids=frozenset({"gpt-5.5", "gpt-4o-mini"}),
        )
        pruned, dropped = probe.prune_ladder(ladder, live)
        assert [m.id for m in pruned.models] == ["gpt-5.5", "gpt-4o-mini"]
        assert [m.id for m in dropped] == ["gpt-deprecated"]

    def test_prune_with_failed_probe_returns_unchanged(self):
        ladder = config.Ladder(
            provider="openai",
            endpoint_default="responses",
            models=(
                config.ModelEntry("gpt-5.5", "responses", ("text",)),
            ),
        )
        bad = probe.LiveProbe("openai", False, frozenset(), error="x")
        pruned, dropped = probe.prune_ladder(ladder, bad)
        assert pruned.models == ladder.models
        assert dropped == []


# ─────────────────────────────────────────────────────────────────
# Provider calls + typed errors
# ─────────────────────────────────────────────────────────────────


class TestOpenAIClassification:
    def _rung(self, endpoint="responses"):
        return config.ModelEntry(
            id="gpt-test", endpoint=endpoint, capabilities=("text", "reasoning")
        )

    def test_404_model_not_found_falls_through(self):
        # First rung 404s (ModelNotFound), second succeeds.
        responses_ok = json.dumps(
            {"output_text": "the answer"}
        ).encode("utf-8")
        calls = []

        def fetcher(req):
            calls.append(req.full_url)
            if len(calls) == 1:
                fp = io.BytesIO(b'{"error": {"message": "model not_found"}}')
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", hdrs={}, fp=fp
                )
            return responses_ok

        rungs = [
            self._rung(),
            config.ModelEntry("gpt-good", "responses", ("text", "reasoning")),
        ]
        model_id, text, attempts = providers.call_openai(
            rungs, "q", "sys", "sk-x", fetcher=fetcher
        )
        assert model_id == "gpt-good"
        assert text == "the answer"
        assert len(attempts) == 1
        assert isinstance(attempts[0], errors.ModelNotFound)

    def test_400_endpoint_mismatch_falls_through(self):
        responses_ok = json.dumps({"output_text": "ok"}).encode("utf-8")
        calls = []

        def fetcher(req):
            calls.append(req.full_url)
            if len(calls) == 1:
                fp = io.BytesIO(
                    b'{"error": {"message": "this model is not '
                    b'supported on the chat/completions endpoint"}}'
                )
                raise urllib.error.HTTPError(
                    req.full_url, 400, "Bad Request", hdrs={}, fp=fp
                )
            return responses_ok

        rungs = [
            config.ModelEntry("gpt-pro", "chat", ("text",)),
            config.ModelEntry("gpt-fallback", "responses", ("text",)),
        ]
        model_id, text, attempts = providers.call_openai(
            rungs, "q", "sys", "sk-x", fetcher=fetcher
        )
        assert model_id == "gpt-fallback"
        assert isinstance(attempts[0], errors.EndpointMismatch)

    def test_403_permission_denied_falls_through(self):
        responses_ok = json.dumps({"output_text": "ok"}).encode("utf-8")
        calls = []

        def fetcher(req):
            calls.append(req.full_url)
            if len(calls) == 1:
                fp = io.BytesIO(b'{"error": "forbidden"}')
                raise urllib.error.HTTPError(
                    req.full_url, 403, "Forbidden", hdrs={}, fp=fp
                )
            return responses_ok

        rungs = [
            config.ModelEntry("gpt-locked", "responses", ("text",)),
            config.ModelEntry("gpt-open", "responses", ("text",)),
        ]
        _, _, attempts = providers.call_openai(
            rungs, "q", "sys", "sk-x", fetcher=fetcher
        )
        assert isinstance(attempts[0], errors.PermissionDenied)

    def test_429_rate_limited_falls_through(self):
        responses_ok = json.dumps({"output_text": "ok"}).encode("utf-8")
        calls = []

        def fetcher(req):
            calls.append(req.full_url)
            if len(calls) == 1:
                fp = io.BytesIO(b'{"error": "rate_limit"}')
                raise urllib.error.HTTPError(
                    req.full_url, 429, "Too Many Requests", hdrs={}, fp=fp
                )
            return responses_ok

        rungs = [
            config.ModelEntry("gpt-pro", "responses", ("text",)),
            config.ModelEntry("gpt-cheap", "responses", ("text",)),
        ]
        _, _, attempts = providers.call_openai(
            rungs, "q", "sys", "sk-x", fetcher=fetcher
        )
        assert isinstance(attempts[0], errors.RateLimited)

    def test_401_auth_error_does_not_fall_through(self):
        def fetcher(req):
            fp = io.BytesIO(b'{"error": "Invalid API key"}')
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized", hdrs={}, fp=fp
            )

        rungs = [
            config.ModelEntry("gpt-1", "responses", ("text",)),
            config.ModelEntry("gpt-2", "responses", ("text",)),
        ]
        with pytest.raises(errors.AuthError):
            providers.call_openai(
                rungs, "q", "sys", "sk-bad", fetcher=fetcher
            )

    def test_transport_error_does_not_fall_through(self):
        def fetcher(req):
            raise urllib.error.URLError("name resolution failure")

        rungs = [
            config.ModelEntry("gpt-1", "responses", ("text",)),
            config.ModelEntry("gpt-2", "responses", ("text",)),
        ]
        with pytest.raises(errors.TransportError):
            providers.call_openai(
                rungs, "q", "sys", "sk-x", fetcher=fetcher
            )

    def test_ladder_exhausted_when_all_rungs_fail(self):
        def fetcher(req):
            fp = io.BytesIO(b'{"error": "model not_found"}')
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", hdrs={}, fp=fp
            )

        rungs = [
            config.ModelEntry("gpt-1", "responses", ("text",)),
            config.ModelEntry("gpt-2", "responses", ("text",)),
        ]
        with pytest.raises(errors.LadderExhausted):
            providers.call_openai(
                rungs, "q", "sys", "sk-x", fetcher=fetcher
            )

    def test_responses_endpoint_uses_reasoning_effort_for_reasoning_models(self):
        captured = {}

        def fetcher(req):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return json.dumps({"output_text": "ok"}).encode("utf-8")

        rungs = [
            config.ModelEntry(
                "gpt-5.5", "responses", ("text", "reasoning")
            ),
        ]
        providers.call_openai(rungs, "q", "sys", "sk-x", fetcher=fetcher)
        assert captured["url"].endswith("/v1/responses")
        assert captured["body"]["reasoning"]["effort"] == "medium"
        # reasoning models should NOT receive temperature
        assert "temperature" not in captured["body"]

    def test_chat_endpoint_uses_temperature_for_legacy_models(self):
        captured = {}

        def fetcher(req):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode("utf-8")

        rungs = [
            config.ModelEntry("gpt-4o-mini", "chat", ("text",)),
        ]
        providers.call_openai(rungs, "q", "sys", "sk-x", fetcher=fetcher)
        assert captured["url"].endswith("/v1/chat/completions")
        assert captured["body"]["temperature"] == 0.4
        assert "messages" in captured["body"]
        assert "reasoning" not in captured["body"]


# ─────────────────────────────────────────────────────────────────
# End-to-end runner with stub HTTP
# ─────────────────────────────────────────────────────────────────


class TestRunnerEndToEnd:
    def test_single_provider_round_trip_writes_expected_files(self, tmp_path):
        ladder = config.Ladder(
            provider="openai",
            endpoint_default="responses",
            models=(
                config.ModelEntry(
                    "gpt-5.5", "responses", ("text", "reasoning")
                ),
            ),
        )

        # Probe returns a body with the configured model present.
        def probe_fetcher(req):
            return json.dumps({"data": [{"id": "gpt-5.5"}]}).encode("utf-8")

        # Call returns a happy path body.
        def call_fetcher(req):
            return json.dumps(
                {"output_text": "the consult result"}
            ).encode("utf-8")

        log_lines: list[str] = []
        run = runner.RoundRobinRunner(
            ladders={"openai": ladder},
            api_keys={"openai": "sk-stub"},
            output_dir=tmp_path,
            probe_fetcher=probe_fetcher,
            call_fetchers={"openai": call_fetcher},
            log=log_lines.append,
        )
        results = run.run("test q", topic="t")
        assert len(results) == 1
        assert results[0].ok
        assert results[0].model == "gpt-5.5"
        assert results[0].response == "the consult result"
        # Output md files emitted with the expected filename pattern
        files = sorted(p.name for p in tmp_path.iterdir())
        assert any(f.endswith("__00_question.md") for f in files)
        assert any(f.endswith("__01_openai.md") for f in files)
        assert any(f.endswith("_synthesis.md") for f in files)
        assert any(f.endswith("__transcript.json") for f in files)
        # Probe success was logged
        assert any("[probe openai] live=" in line for line in log_lines)
        # Synthesis contains the response
        synth = next(
            tmp_path / f for f in files if f.endswith("_synthesis.md")
        )
        assert "the consult result" in synth.read_text(encoding="utf-8")

    def test_failed_probe_falls_back_to_configured_ladder(self, tmp_path):
        """If /v1/models 4xxs, the runner must NOT throw the ladder
        out — just warn and try the configured rungs."""
        ladder = config.Ladder(
            provider="openai",
            endpoint_default="responses",
            models=(
                config.ModelEntry(
                    "gpt-5.5", "responses", ("text", "reasoning")
                ),
            ),
        )

        def probe_fetcher(req):
            fp = io.BytesIO(b'{"error": "transient"}')
            raise urllib.error.HTTPError(
                req.full_url, 500, "Server", hdrs={}, fp=fp
            )

        def call_fetcher(req):
            return json.dumps({"output_text": "still works"}).encode("utf-8")

        log_lines: list[str] = []
        run = runner.RoundRobinRunner(
            ladders={"openai": ladder},
            api_keys={"openai": "sk-stub"},
            output_dir=tmp_path,
            probe_fetcher=probe_fetcher,
            call_fetchers={"openai": call_fetcher},
            log=log_lines.append,
        )
        results = run.run("q", topic="t")
        assert results[0].ok
        assert any("[probe openai] FAILED" in l for l in log_lines)

    def test_needs_filter_drops_unmatching_rungs(self, tmp_path):
        """A model without ``vision`` should not be tried when
        --needs vision is requested."""
        ladder = config.Ladder(
            provider="gemini",
            endpoint_default="generate_content",
            models=(
                config.ModelEntry(
                    "text-only", "generate_content", ("text",)
                ),
                config.ModelEntry(
                    "vision-too",
                    "generate_content",
                    ("text", "vision"),
                ),
            ),
        )

        # Probe must include both ids so we know the filter (not the
        # probe) is what dropped the text-only entry.
        def probe_fetcher(req):
            return json.dumps(
                {
                    "models": [
                        {"name": "models/text-only"},
                        {"name": "models/vision-too"},
                    ]
                }
            ).encode("utf-8")

        captured = []

        def call_fetcher(req):
            captured.append(req.full_url)
            return json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "got it"}]}}]}
            ).encode("utf-8")

        run = runner.RoundRobinRunner(
            ladders={"gemini": ladder},
            api_keys={"gemini": "stub"},
            output_dir=tmp_path,
            probe_fetcher=probe_fetcher,
            call_fetchers={"gemini": call_fetcher},
            log=lambda _line: None,
        )
        results = run.run("q", topic="t", needs=["vision"])
        assert results[0].ok
        assert results[0].model == "vision-too"
        # Only one HTTP call to the call_fetcher (the vision-too rung)
        assert len(captured) == 1
        assert "vision-too" in captured[0]
