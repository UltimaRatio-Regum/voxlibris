FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    git \
    espeak-ng \
    rubberband-cli \
    librubberband-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -c "import nltk; nltk.download('punkt', download_dir='/usr/local/share/nltk_data'); nltk.download('punkt_tab', download_dir='/usr/local/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/local/share/nltk_data')" || true

RUN python -c "\
import torch; \
torch.serialization.add_safe_globals([]); \
from styletts2 import tts as stts; \
engine = stts.StyleTTS2(); \
print('Model downloaded successfully')" || echo "Model pre-download attempted"

COPY . .

RUN chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 7860

CMD ["sh", "-c", "OMP_NUM_THREADS=4 exec uvicorn app:app --host 0.0.0.0 --port 7860"]
