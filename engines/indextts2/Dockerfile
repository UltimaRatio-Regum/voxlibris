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
WORKDIR /app

RUN pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0

ENV GIT_LFS_SKIP_SMUDGE=1
RUN pip install --no-cache-dir "indextts[webui] @ git+https://github.com/index-tts/index-tts.git@main"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p checkpoints && \
    python -c "from huggingface_hub import snapshot_download; snapshot_download('IndexTeam/IndexTTS-2', local_dir='checkpoints')" \
    || echo "Model download deferred to runtime startup"

COPY . .

RUN chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface
ENV MODEL_DIR=/app/checkpoints

EXPOSE 7860

CMD ["sh", "-c", "OMP_NUM_THREADS=4 exec uvicorn app:app --host 0.0.0.0 --port 7860"]
