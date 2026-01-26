# 1. Use the NVIDIA CUDA base for GPU acceleration
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

# 2. Set non-interactive and environment defaults
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 3. Opinionated Defaults (Baking them into the image)
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_MODELS=/workspace/ollama
ENV OLLAMA_KEEP_ALIVE=-1
ENV WEBUI_HOST=0.0.0.0
ENV WEBUI_PORT=8080
ENV DATA_DIR=/workspace/openwebui/data
# Tells WebUI where to find the Ollama API
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
    && rm -rf /var/lib/apt/lists/*

# 5. Install pip for Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# 6. Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# 7. Install Open WebUI
RUN python3.11 -m pip install --no-cache-dir open-webui

# 8. Create the workspace and startup script
WORKDIR /workspace
RUN echo '#!/bin/bash\n\
    # Ensure directories exist for persistence\n\
    mkdir -p $OLLAMA_MODELS\n\
    mkdir -p $DATA_DIR\n\
    \n\
    echo "Starting Ollama..."\n\
    ollama serve &\n\
    \n\
    # Wait for Ollama to be ready\n\
    until curl -s http://127.0.0.1:11434/api/tags > /dev/null; do\n\
    echo "Waiting for Ollama API..."\n\
    sleep 2\n\
    done\n\
    \n\
    echo "Starting Open WebUI..."\n\
    python3.11 -m open_webui serve' > /start.sh && chmod +x /start.sh

# 9. Expose necessary ports
EXPOSE 11434
EXPOSE 8080

CMD ["/start.sh"]
