FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/morgenruf/morgenruf"
LABEL org.opencontainers.image.description="Slack standup bot — structured daily standups"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY teams.yaml.example ./teams.yaml

ENV PYTHONUNBUFFERED=1
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')"

CMD ["python", "src/main.py"]
