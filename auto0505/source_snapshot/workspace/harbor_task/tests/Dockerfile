FROM ubuntu:22.04
ENV EVFI_TASK_ROOT=/workspace PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY . /tests/
COPY candidate_worker.py /usr/local/lib/rfsteps/candidate_worker.py
RUN chmod 700 /tests && chmod -R go-rwx /tests && chmod 644 /usr/local/lib/rfsteps/candidate_worker.py
COPY bootstrap.sh /usr/local/bin/rfsteps-bootstrap
ENTRYPOINT ["/usr/local/bin/rfsteps-bootstrap"]
CMD ["/bin/bash"]
