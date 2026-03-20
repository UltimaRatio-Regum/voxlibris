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

# Install PyTorch CPU first (requires a separate index URL), then the rest of
# the inference-only dependencies from requirements.txt.
RUN pip install --no-cache-dir \
    torch==2.3.1 torchaudio==2.3.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy our VoxLibris engine files into the repo root, alongside
# glmtts_inference.py so Python can import it without path manipulation.
COPY app.py .
COPY index.html .

RUN chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 7860

CMD ["sh", "-c", "OMP_NUM_THREADS=4 exec uvicorn app:app --host 0.0.0.0 --port 7860"]
