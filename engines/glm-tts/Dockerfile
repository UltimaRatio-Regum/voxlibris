FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    git \
    rubberband-cli \
    librubberband-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user

# Clone the GLM-TTS repository — our app.py is placed alongside
# glmtts_inference.py so imports resolve correctly, and the hardcoded
# "ckpt/" checkpoint paths work relative to this directory.
RUN git clone https://github.com/zai-org/GLM-TTS.git /app

WORKDIR /app

# Install PyTorch with CUDA 12.1 support — glmtts_inference.py calls .cuda()
# unconditionally so a CUDA-enabled build is required. cu121 is the standard
# CUDA version for HuggingFace GPU Spaces (T4/A10G).
RUN pip install --no-cache-dir \
    torch==2.3.1 torchaudio==2.3.1 \
    --index-url https://download.pytorch.org/whl/cu121

COPY requirements.txt .

# openai-whisper uses a legacy setup.py that imports pkg_resources, which
# newer setuptools no longer expose inside pip's isolated build environments.
# Installing it with --no-build-isolation bypasses that isolation so it can
# use the system setuptools where pkg_resources is available.
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20231117 && \
    pip install --no-cache-dir -r requirements.txt

# Copy our TomeVox engine files into the repo root, alongside
# glmtts_inference.py so Python can import it without path manipulation.
COPY app.py .
COPY index.html .

# WeTextProcessing (tn) compiles FST files on first import and writes them back
# into its site-packages directory. Pre-build them now while still running as
# root so the files exist and are readable when the app runs as the user.
RUN python -c "from tn.chinese.normalizer import Normalizer; Normalizer()" && \
    python -c "from tn.english.normalizer import Normalizer; Normalizer()" && \
    chmod -R a+w /usr/local/lib/python3.11/site-packages/tn/

RUN chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 7860

CMD ["sh", "-c", "OMP_NUM_THREADS=4 exec uvicorn app:app --host 0.0.0.0 --port 7860"]
