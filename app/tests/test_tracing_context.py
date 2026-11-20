"""Log lines carry the active trace id, and each scheduled job run is one trace."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from src.core import logjson

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
_tracer = _provider.get_tracer("test")


def _line() -> dict:
    record = logging.getLogger("t").makeRecord("t", logging.INFO, __file__, 1, "hi", (), None)
    return json.loads(logjson.JsonFormatter().format(record))


def test_no_trace_id_outside_a_span():
    assert "trace_id" not in _line()


def test_log_line_has_the_active_trace_id():
    with _tracer.start_as_current_span("req") as span:
        out = _line()
    ctx = span.get_span_context()
    assert out["trace_id"] == format(ctx.trace_id, "032x")
    assert out["span_id"] == format(ctx.span_id, "016x")


def test_job_run_is_a_span_with_its_work_as_children():
    _exporter.clear()
    job = MagicMock(id="connect:T01:round:7")

    def fake_run_job(*_a):  # a DB query made by the job
        with _tracer.start_as_current_span("SELECT"):
            pass
        return []

    with patch.object(trace, "get_tracer", lambda *_a, **_k: _tracer), patch.object(sched_mod, "run_job", fake_run_job):
        sched_mod._metered_run_job(job, "default", [], "apscheduler")

    spans = {s.name: s for s in _exporter.get_finished_spans()}
    root = spans["job connect:round"]
    assert root.attributes["job.id"] == "connect:T01:round:7"
    assert spans["SELECT"].parent.span_id == root.context.span_id
