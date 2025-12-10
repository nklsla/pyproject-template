# ===== Base Image Selection =====
# Set BASE_IMAGE to one of the following:

# Option 1: Minimal CPU-only
# ARG BASE_IMAGE=python:3.14-slim-bookworm
ARG BASE_IMAGE=ubuntu:24.04

# Option 2: NVIDIA CUDA with Python (runtime only, smallest GPU image)
# ARG BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Option 3: PyTorch Official (includes PyTorch pre-installed)
# ARG BASE_IMAGE=pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Option 4: TensorFlow Official
# ARG BASE_IMAGE=tensorflow/tensorflow:2.18.0-gpu

# Option 5: NVIDIA NGC (largest, most optimized)
# ARG BASE_IMAGE=nvcr.io/nvidia/pytorch:24.11-py3

# Python version (only used for non-Python base images)
ARG PYTHON_VERSION=3.14

# ===== Builder Stage =====
FROM ${BASE_IMAGE} AS builder

ARG PYTHON_VERSION

# Install Python if base image doesn't have it
RUN if ! command -v python3 &> /dev/null; then \
    apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python3-pip && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi


ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/usr/.venv
ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:$PATH"

# Install build dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
    build-essential \
    curl \
    # Numpy/Scipy dependencies
    gfortran libopenblas-dev liblapack-dev \
    # Uncomment for OpenCV
    # libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.14 /uv /uvx /bin/

WORKDIR /app

COPY ./pyproject.toml .
COPY uv.lock .

RUN uv sync --frozen

# ===== Runtime Stage =====
FROM ${BASE_IMAGE} AS production

ARG PYTHON_VERSION

# Install Python if base image doesn't have it
RUN if ! command -v python3 &> /dev/null; then \
    apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_PROJECT_ENVIRONMENT=/usr/.venv
ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:$PATH"
ENV PORT=8000

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
    # Numpy/Scipy runtime
    libopenblas0 libgomp1 \
    # Uncomment for OpenCV runtime
    # libgl1 libglib2.0-0 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment and source code
COPY --from=builder ${UV_PROJECT_ENVIRONMENT} ${UV_PROJECT_ENVIRONMENT}
COPY src src

EXPOSE ${PORT}

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]







# # ===== Base Image Options =====
# # Uncomment one based on your project needs:

# # 1. Minimal - Basic Python packages (numpy, pandas, etc.)
# ARG PYTHON_VERSION=3.14-slim-bookworm

# # 2. CUDA 12.1 - For PyTorch/TensorFlow GPU support
# # ARG PYTHON_VERSION=3.14-bookworm
# # FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 AS builder
# # RUN apt-get update && apt-get install -y python3.14 python3-pip

# # 3. PyTorch Official - Pre-built PyTorch with CUDA
# # FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime AS builder

# # 4. TensorFlow Official - Pre-built TensorFlow with CUDA
# # FROM tensorflow/tensorflow:2.17.0-gpu AS builder

# # 5. NVIDIA NGC - Optimized PyTorch + everything
# # FROM nvcr.io/nvidia/pytorch:24.10-py3 AS builder

# # 6. Full Debian - When you need many system dependencies
# # ARG PYTHON_VERSION=3.12-bookworm

# # ---- Builder Stage ----
# FROM python:${PYTHON_VERSION} AS builder

# ENV PYTHONUNBUFFERED=1
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV UV_LINK_MODE=copy
# ENV UV_PROJECT_ENVIRONMENT=/usr/.venv
# ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:$PATH"

# RUN apt-get update && \
#     apt-get install --no-install-recommends -y \
#     build-essential && \
#     # # For OpenCV etc...
#     # libgl1 libglib2.0-0 \
#     # Minimize image size, it is recommended refresh the package cache as follows
#     apt-get clean && \
#     rm -rf /var/lib/apt/lists/*

# COPY --from=ghcr.io/astral-sh/uv:0.7.14 /uv /uvx /bin/

# WORKDIR /app

# COPY ./pyproject.toml .
# COPY uv.lock .

# RUN uv sync --frozen

# # ---- Production Stage ----
# FROM python:${PYTHON_VERSION} AS production

# ENV PYTHONUNBUFFERED=1
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV UV_PROJECT_ENVIRONMENT=/usr/.venv
# ENV PATH="${UV_PROJECT_ENVIRONMENT}/bin:$PATH"
# ENV PORT=8000

# WORKDIR /app

# COPY --from=builder ${UV_PROJECT_ENVIRONMENT} ${UV_PROJECT_ENVIRONMENT}
# COPY src src

# EXPOSE ${PORT}

# CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
