# === BUILD STAGE (Compile CGO libunilog.so) ===
FROM golang:1.25-bookworm AS go-builder

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends git gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git /workspace/microservice-toolbox && \
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/distributed-config.git /workspace/distributed-config && \
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/safe-socket.git /workspace/safe-socket && \
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/universal-logger.git /workspace/universal-logger && \
    git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/flexible-logger.git /workspace/flexible-logger && \
    printf "go 1.25.8\n\nuse (\n\t./distributed-config\n\t./flexible-logger\n\t./microservice-toolbox\n\t./safe-socket\n\t./universal-logger\n)\n\nreplace github.com/Bastien-Antigravity/microservice-toolbox/go => ./microservice-toolbox\n" > /workspace/go.work && \
    cd /workspace/universal-logger && \
    go build -buildmode=c-shared -o /workspace/libunilog.so ./src/cgo_bridge

# === PYTHON RUNTIME STAGE ===
FROM python:3.12-slim-bookworm

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/obsidian-brain"

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
CMD ["start-squad", "--daemon"]
