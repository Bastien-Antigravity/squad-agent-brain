# === BUILD STAGE (Compile CGO libunilog.so) ===
FROM golang:1.25-bookworm AS go-builder

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends git gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger

WORKDIR /workspace
RUN go work init ./microservice-toolbox ./distributed-config ./safe-socket ./universal-logger ./flexible-logger && \
    cd /workspace/universal-logger && \
    CGO_ENABLED=1 CGO_CFLAGS="-D_GNU_SOURCE -std=gnu11" go build -v -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

# === PYTHON RUNTIME STAGE ===
FROM python:3.12-slim-bookworm

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/squad-agent-brain"

# Install system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install compiled libunilog.so and ecosystem Python packages from builder stage
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so
RUN ldconfig

COPY --from=go-builder /workspace/microservice-toolbox/python /tmp/microservice-toolbox-python
COPY --from=go-builder /workspace/universal-logger/unilog/python /tmp/unilog-python

# Install service dependencies (filter private git URLs) and local ecosystem packages
COPY requirements.txt .
RUN grep -v "git+https://github.com/Bastien-Antigravity" requirements.txt > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir /tmp/microservice-toolbox-python /tmp/unilog-python && \
    rm -rf /tmp/requirements.txt /tmp/microservice-toolbox-python /tmp/unilog-python

# Copy service source code
COPY . .

# Preload libunilog.so to prevent static TLS block exhaustion in glibc dlopen
ENV LD_PRELOAD=/usr/local/lib/libunilog.so
ENV LIBUNILOG_PATH=/usr/local/lib/libunilog.so

# Set entrypoint
ENTRYPOINT ["python", "main.py"]
CMD ["squad-agent", "--daemon"]
