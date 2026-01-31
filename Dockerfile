# 1. Use the NVIDIA CUDA base for GPU acceleration
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

# 2. Set non-interactive and environment defaults
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 3. Opinionated Defaults
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_MODELS=/workspace/ollama
ENV OLLAMA_KEEP_ALIVE=-1
ENV OLLAMA_CONTEXT_LENGTH=65536
ENV OLLAMA_MAX_LOADED_MODELS=1
ENV OLLAMA_KV_CACHE_TYPE=q8_0
ENV WEBUI_HOST=0.0.0.0
ENV WEBUI_PORT=8080
ENV WEBUI_AUTH=False
ENV DATA_DIR=/workspace/openwebui/data
ENV OLLAMA_BASE_URL=http://127.0.0.1:11434

# 4. Install Python 3.11 and system tools
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    curl \
    git \
    ffmpeg \
    libsm6 \
    libxext6 \
    zstd \
    psmisc \
    openssh-server \
    net-tools \
    nvtop \
    && rm -rf /var/lib/apt/lists/*

# 5. Install pip for Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# 6. Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# 7. Install Open WebUI
RUN python3.11 -m pip install --no-cache-dir open-webui

# 8. Setup SSH Configuration (Password & Forwarding)
RUN mkdir /var/run/sshd && \
    # Set a temporary password for testing
    echo 'root:ollamatesting' | chpasswd && \
    # Allow Root Login and Password Auth
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    # Crucial for the tunnel: Enable Forwarding
    echo "AllowTcpForwarding yes" >> /etc/ssh/sshd_config && \
    echo "GatewayPorts yes" >> /etc/ssh/sshd_config && \
    echo "UseDNS no" >> /etc/ssh/sshd_config && \
    echo "TCPKeepAlive yes" >> /etc/ssh/sshd_config

# 9. Create the workspace and startup script
WORKDIR /workspace
RUN echo '#!/bin/bash\n\
    # Start SSH service\n\
    service ssh start\n\
    \n\
    # Setup SSH Key if provided via Environment Variable (for future use)\n\
    if [ ! -z "$PUBLIC_KEY" ]; then\n\
    mkdir -p /root/.ssh\n\
    echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys\n\
    chmod 700 /root/.ssh\n\
    chmod 600 /root/.ssh/authorized_keys\n\
    fi\n\
    \n\
    # GPU Cleanup\n\
    fuser -k /dev/nvidia0 || true\n\
    sleep 1\n\
    \n\
    mkdir -p $OLLAMA_MODELS\n\
    mkdir -p $DATA_DIR\n\
    \n\
    echo "Starting Ollama..."\n\
    ollama serve &\n\
    \n\
    until curl -s http://127.0.0.1:11434/api/tags > /dev/null; do\n\
    echo "Waiting for Ollama API..."\n\
    sleep 2\n\
    done\n\
    \n\
    echo "Starting Open WebUI..."\n\
    open-webui serve' > /start.sh && chmod +x /start.sh

# 10. Expose necessary ports
# EXPOSE 11434
# EXPOSE 8080
EXPOSE 22

CMD ["/start.sh"]
