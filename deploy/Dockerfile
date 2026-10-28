FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive     PIP_NO_CACHE_DIR=1     CONFIGURATOR_HOST=0.0.0.0     CONFIGURATOR_PORT=8787

RUN apt-get update  && apt-get install -y --no-install-recommends git curl ca-certificates  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY deploy/entrypoint.sh /app/deploy/entrypoint.sh
COPY scripts /app/scripts
COPY tools /app/tools
COPY configs /app/configs
COPY Makefile /app/Makefile
RUN chmod +x /app/deploy/entrypoint.sh /app/scripts/*.sh

RUN python3 -m venv /app/build/.venv  && /app/build/.venv/bin/pip install --quiet "platformio==6.1.19"

EXPOSE 8787
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
