# The build receipt verifies that this local offline tag resolves to the exact
# digest pinned in task.toml before Docker evaluates this file.
FROM onedc-env:v8

USER root
WORKDIR /tests

# Harbor builds the verifier from tests/ as an independent context.  Hidden
# images are injected by the trusted runner after this image is built.
COPY . /tests
COPY --chmod=0755 test.sh protect_runtime.sh /tests/

ENTRYPOINT []
CMD ["/bin/bash"]
