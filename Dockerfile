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

WORKDIR /workspace/universal-logger
RUN CGO_ENABLED=1 CGO_CFLAGS="-D_GNU_SOURCE -std=gnu11" GOWORK=off go build -v -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

# === PYTHON RUNTIME STAGE ===
FROM python:3.12-slim-bookworm

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/squad-agent-brain"

# Install system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install compiled libunilog.so system-wide
COPY --from=go-builder /workspace/libunilog.so /usr/local/lib/libunilog.so
RUN ldconfig

# Clone & install microservice-toolbox python package
RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /tmp/microservice-toolbox && \
    pip install --no-cache-dir /tmp/microservice-toolbox/python && \
    rm -rf /tmp/microservice-toolbox

# Install service dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source code
COPY . .

# Set entrypoint
ENTRYPOINT ["python", "main.py"]
CMD ["squad-agent", "--daemon"]
