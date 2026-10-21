FROM node:22.16.0-bookworm-slim AS node_runtime
FROM python:3.12.13-slim-bookworm
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends python3 libseccomp2 libgomp1 libgl1 libglib2.0-0 ca-certificates git ripgrep coreutils \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN node /usr/local/lib/node_modules/npm/bin/npm-cli.js install -g @openai/codex@0.160.0
RUN pip install --no-cache-dir torch==2.12.1+cu130 --index-url https://download.pytorch.org/whl/cu130 \
    && pip install --no-cache-dir -r /tmp/requirements.lock
COPY repo /opt/rfsteps/repo/
COPY weights /opt/rfsteps/weights/
COPY worker /opt/rfsteps/worker/
RUN chmod 755 /opt/rfsteps/worker && chmod 644 /opt/rfsteps/worker/*.py
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
