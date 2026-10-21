ARG RFSTEPS_RUNTIME_IMAGE=rfsteps-numerical:3.5.0-a100
FROM ${RFSTEPS_RUNTIME_IMAGE}
USER root
COPY starter /workspace/starter
COPY instruction.md /workspace/instruction.md
COPY public_assets /workspace/environment/public_assets
COPY public_eval /opt/rfsteps/public
COPY public_eval/evaluate.sh /workspace/environment/public_eval/evaluate.sh
COPY bootstrap.sh /usr/local/bin/rfsteps-bootstrap
RUN useradd --uid 1000 --create-home solver \
    && mkdir -p /workspace/solution /workspace/agent-output \
    && cp /workspace/starter/method.py /workspace/solution/method.py \
    && cp /workspace/starter/solve.sh /workspace/solution/solve.sh \
    && chown -R 1000:1000 /workspace/solution /workspace/agent-output \
    && chmod -R a+rX /workspace/starter /workspace/environment /opt/rfsteps/public /opt/rfsteps/repo /opt/rfsteps/weights \
    && chmod -R a-w /workspace/starter /workspace/environment/public_assets /opt/rfsteps/public /opt/rfsteps/repo /opt/rfsteps/weights \
    && chmod 755 /usr/local/bin/rfsteps-bootstrap /workspace/environment/public_eval/evaluate.sh
USER 1000
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/rfsteps-bootstrap"]
CMD ["/bin/bash"]
