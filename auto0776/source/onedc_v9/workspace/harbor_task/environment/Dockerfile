# Native Harbor environment context; Harbor 0.23.0.
# Build with --build-context model_assets=<verified asset directory>.
# Also supply --build-context agent_tools=<verified Codex tool directory>.
# Final image embeds all model assets and runs offline.
FROM nvidia/cuda@sha256:f4d8e1264366940438f0353da6f289c7bef069d993d111f8106086ccd18c4a30 AS deps
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-dev cmake g++ git curl xz-utils sudo libseccomp2 bubblewrap && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
COPY requirements-lock.txt /tmp/requirements-lock.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip3 install --no-cache-dir -r /tmp/requirements-lock.txt && pip3 check
COPY repo /workspace/repo
RUN apt-get update && apt-get install -y --no-install-recommends make && rm -rf /var/lib/apt/lists/* && cd /workspace/repo/onedc/src && mkdir -p build && cd build && cmake ../cpp -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)" && make -j4 && test -n "$(find ../modules/entropy -name 'MLCodec_rans*.so' -print -quit)" && test -n "$(find ../modules/entropy -name 'MLCodec_CXX*.so' -print -quit)" && rm -rf /workspace/repo/onedc/src/build
FROM deps AS runtime
COPY --from=model_assets / /opt/onedc/weights/
COPY --from=agent_tools /bin/codex /usr/local/bin/codex
COPY --from=agent_tools /bin/codex-code-mode-host /usr/local/bin/codex-code-mode-host
COPY grader /opt/onedc/grader
COPY metric_assets /opt/onedc/metric_weights
COPY public_assets /workspace/public_assets
COPY task_instruction.md /workspace/instruction.md
COPY starter /workspace/environment/starter
COPY starter/method.py /workspace/solution/method.py
COPY solve.sh /workspace/solution/solve.sh
COPY evaluate.sh /workspace/evaluate.sh
COPY requirements-runtime-extra.txt /tmp/requirements-runtime-extra.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip3 check && cd /workspace/repo/onedc/src && python3 -c "from inference import Evaluator; from modules.entropy import MLCodec_CXX, MLCodec_rans; print('Official evaluator import preflight passed')"
RUN ln -s /opt/onedc/metric_weights/dists.pt /usr/weights.pt && TORCH_HOME=/opt/onedc/weights/torch python3 -c "import lpips; from DISTS_pytorch import DISTS; lpips.LPIPS(net='alex'); DISTS(); print('Offline metric weights import passed')"
RUN useradd -u 25000 -m -s /bin/bash onedc-agent && useradd -u 25001 -M -s /usr/sbin/nologin onedc-worker && mkdir -p /workspace/.git /workspace/.codex /workspace/.agents /workspace/public-results /workspace/eval-requests /opt/onedc/locks /logs/artifacts /logs/agent && chown root:onedc-agent /workspace && chmod 1775 /workspace && touch /opt/onedc/locks/gpu.lock && chown onedc-agent:onedc-agent /workspace/solution/method.py && chown -R onedc-agent:onedc-agent /home/onedc-agent && chown root:onedc-agent /workspace/eval-requests && chmod 1775 /workspace/eval-requests && chmod 755 /opt/onedc/grader/entrypoint.sh && chmod 755 /workspace/evaluate.sh /workspace/solution/solve.sh /opt/onedc/grader/public_eval.py && chmod 600 /opt/onedc/locks/gpu.lock && bash /opt/onedc/grader/protect_runtime.sh && find /workspace/repo /opt/onedc/grader -type d -name __pycache__ -prune -exec rm -rf {} + && python3 /opt/onedc/grader/build_integrity.py
ENV ONEDC_REPO_SRC=/workspace/repo/onedc/src ONEDC_CHECKPOINT=/opt/onedc/weights/lambda4.6
ENV HF_HOME=/opt/onedc/weights/hf TORCH_HOME=/opt/onedc/weights/torch
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /workspace
ENTRYPOINT ["/opt/onedc/grader/entrypoint.sh"]
CMD ["/bin/bash"]
