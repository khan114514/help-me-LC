FROM python:3.12-slim-bookworm
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends python3 libseccomp2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /validation
COPY canary.txt /private-canary/readable-secret
CMD ["python3", "/validation/test_candidate_boundary.py"]
