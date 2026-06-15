# Shared image for both the API and the GPU worker (same code, different
# command). Base already ships CUDA + torch + torchvision, so we only add
# the OCR/service deps on top.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/hf-cache

# System libs: OpenCV needs libGL + glib; the rest are small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
# torch/torchvision are already in the base image, so pip skips them.
RUN pip install -r requirements.txt

COPY app ./app

# API default; the worker service overrides this command in compose.
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
