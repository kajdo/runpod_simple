# 1. Use the NVIDIA CUDA base for GPU acceleration
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

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
ENV WEBUI_AUTH=True
ENV ENABLE_API_KEYS=True
ENV WEBUI_ADMIN_EMAIL=admin@runpod.local
ENV WEBUI_ADMIN_PASSWORD=admin
ENV DATA_DIR=/workspace/openwebui/data
ENV OLLAMA_BASE_URL=http://127.0.0.1:11434
ENV ENABLE_WEB_SEARCH=True
ENV WEB_SEARCH_ENGINE=searxng
ENV SEARXNG_QUERY_URL=http://127.0.0.1:8888/search?q=<query>
ENV WEB_LOADER_CONCURRENT_REQUESTS=10
ENV WEB_LOADER_ENGINE=external
ENV EXTERNAL_WEB_LOADER_URL=http://127.0.0.1:9999/crawl
ENV EXTERNAL_WEB_LOADER_API_KEY=123


# 4. Install Python 3.11 and system tools
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    python3.11-venv \
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
    libxslt-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 5. Install pip for Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# 6. Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# 7. Install Open WebUI
RUN python3.11 -m pip install --no-cache-dir open-webui

# 8. Install SearXNG
RUN git clone --depth 1 https://github.com/searxng/searxng.git /usr/local/searxng/searxng-src && \
    cd /usr/local/searxng/searxng-src && \
    python3.11 -m venv "/usr/local/searxng/searx-pyenv" && \
    . "/usr/local/searxng/searx-pyenv/bin/activate" && \
    pip install --no-cache-dir -U pip setuptools wheel pyyaml msgspec typing_extensions && \
    pip install --no-cache-dir --use-pep517 --no-build-isolation -e .

# 9. Configure SearXNG
RUN mkdir -p /etc/searxng && \
    cp /usr/local/searxng/searxng-src/utils/templates/etc/searxng/settings.yml /etc/searxng/settings.yml && \
    sed -i "s/ultrasecretkey/$(openssl rand -hex 16)/g" /etc/searxng/settings.yml && \
    sed -i "s/debug: false/debug: false/g" /etc/searxng/settings.yml && \
    sed -i "s/bind_address: \"127.0.0.1\"/bind_address: \"0.0.0.0\"/g" /etc/searxng/settings.yml && \
    sed -i "s|url: valkey://localhost:6379/0|url: false|g" /etc/searxng/settings.yml && \
    sed -i "s/limiter: true/limiter: false/g" /etc/searxng/settings.yml && \
    sed -i "s/  formats:/  formats:\n    - json/g" /etc/searxng/settings.yml

# 9.1. Install Crawl4ai
RUN mkdir -p /root/git && \
    cd /root/git && \
    git clone --depth 1 https://github.com/unclecode/crawl4ai.git /root/git/crawl4ai && \
    cd crawl4ai && \
    python3.11 -m venv venv && \
    . venv/bin/activate && \
    pip install -e ".[all]" && \
    pip install -r deploy/docker/requirements.txt && \
    crawl4ai-setup && \
    playwright install-deps 

# 9.2. Install Crawl4ai Py Proxy
RUN mkdir -p /root/git && \
    cd /root/git && \
    git clone --depth 1 https://github.com/kajdo/crawl4ai-py-proxy.git /root/git/crawl4ai-py-proxy && \
    cd crawl4ai-py-proxy && \
    python3.11 -m venv venv && \
    . venv/bin/activate && \
    pip install -r requirements.txt

# 10. Setup SSH Configuration (Password & Forwarding)
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

# 11. Create the workspace and startup script
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
    echo "Starting SearXNG..."\n\
    export SEARXNG_SETTINGS_PATH="/etc/searxng/settings.yml"\n\
    (cd /usr/local/searxng/searxng-src && /usr/local/searxng/searx-pyenv/bin/python searx/webapp.py) &\n\
    echo "Starting crawl4ai..."\n\
    (cd /root/git/crawl4ai/deploy/docker && export PYTHONPATH=$PYTHONPATH:/root/git/crawl4ai && /root/git/crawl4ai/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 11235) &\n\
    \n\
    echo "Starting crawl4ai python proxy ..."\n\
    (cd /root/git/crawl4ai-py-proxy && export PYTHONPATH=$PYTHONPATH:/root/git/crawl4ai-py-proxy && /root/git/crawl4ai-py-proxy/venv/bin/python main.py) &\n\
    \n\
    echo "Starting Open WebUI..."\n\
    exec open-webui serve' > /start.sh && chmod +x /start.sh

# 12. Expose necessary ports
# EXPOSE 11434
# EXPOSE 8080
# EXPOSE 8888
EXPOSE 22

CMD ["/start.sh"]
