FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/morgenruf/morgenruf"
LABEL org.opencontainers.image.description="Slack standup bot — structured daily standups"
LABEL org.opencontainers.image.licenses="MIT"

# The base image lags Debian security updates by days. Pull them in at build
# time so a fixed CVE in a system library (OpenSSL, for one) does not fail the
# release scan or ship in the image.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# pip is only needed to install. Its vendored msgpack and pkg_resources (from
# setuptools) carry CVEs the scanner reports against the image, and nothing
# runs pip at runtime, so remove it and the ensurepip wheel that bundles it.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall -y pip \
 && rm -f /usr/local/lib/python*/ensurepip/_bundled/*.whl

COPY src/ ./src/
COPY teams.yaml.example ./teams.yaml

# The release version, passed by the release workflow. The index route and
# the MCP server report it.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

ENV PYTHONUNBUFFERED=1
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')"

RUN useradd -m -u 1000 -s /bin/sh morgenruf && chown -R morgenruf:morgenruf /app
USER morgenruf

CMD ["python", "-m", "src.main"]
