FROM node:22.16.0-bookworm-slim AS node_runtime
FROM ubuntu:22.04
ENV EVFI_TASK_ROOT=/workspace PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN node /usr/local/lib/node_modules/npm/bin/npm-cli.js install -g @openai/codex@0.160.0 \
    && codex --version
WORKDIR /workspace
COPY instruction.md /workspace/instruction.md
COPY starter /workspace/environment/starter
COPY public_assets /workspace/environment/public_assets
COPY public_eval /workspace/environment/public_eval
RUN mkdir -p /installed-agent /workspace/solution /workspace/agent-output && cp /workspace/environment/starter/method.py /workspace/solution/method.py && cp /workspace/environment/public_eval/solve.sh /workspace/solution/solve.sh
COPY bootstrap.sh /usr/local/bin/rfsteps-bootstrap
ENTRYPOINT ["/usr/local/bin/rfsteps-bootstrap"]
CMD ["/bin/bash"]
