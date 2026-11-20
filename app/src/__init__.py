import os

# OpenTelemetry tracing. Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set. Runs when the
# package is first imported, before the web framework and clients are, so the
# instrumentors can patch them. All other settings are OTEL_* env.
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry.instrumentation.auto_instrumentation import initialize

    initialize()
