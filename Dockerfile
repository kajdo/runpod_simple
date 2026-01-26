# Example: Start with a PyTorch base
FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6  && rm -rf /var/lib/apt/lists/*

# Install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set working directory
WORKDIR /workspace
