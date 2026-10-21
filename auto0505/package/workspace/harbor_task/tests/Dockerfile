ARG RFSTEPS_RUNTIME_IMAGE=rfsteps-numerical:3.5.0-a100
FROM ${RFSTEPS_RUNTIME_IMAGE}
USER root
COPY . /tests/
RUN chmod -R go-rwx /tests && chmod 755 /tests/test.sh
WORKDIR /workspace
CMD ["/bin/bash"]
