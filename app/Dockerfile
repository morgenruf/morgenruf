FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/morgenruf/morgenruf"
LABEL org.opencontainers.image.description="Slack standup bot — structured daily standups"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY migrations/ ./migrations/
COPY teams.yaml.example ./teams.yaml

ENV PYTHONUNBUFFERED=1
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')"

RUN useradd -m -u 1000 -s /bin/sh morgenruf && chown -R morgenruf:morgenruf /app
USER morgenruf

CMD ["python", "src/main.py"]
