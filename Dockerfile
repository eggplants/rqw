FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder

ARG VERSION
ENV VERSION=${VERSION:-master}

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
RUN /opt/venv/bin/pip install --no-cache-dir \
    "git+https://github.com/eggplants/rqw@${VERSION}"

FROM al3xos/python-distroless:3.14-debian13@sha256:421a2331f5bf33de9ef3073759f3674ae6765f09e23bf83152998e870d44a836
COPY --from=builder /opt/venv /opt/venv
# Nothing in here launches a venv, so the interpreter is called directly and told
# where the packages landed.
ENV PYTHONPATH="/opt/venv/lib/python3.14/site-packages"

ENTRYPOINT ["python", "/opt/venv/bin/rqw"]
