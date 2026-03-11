FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    git \
    rubberband-cli \
    librubberband-dev \
    wget \
    unzip \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --no-deps "myshell-openvoice @ git+https://github.com/myshell-ai/OpenVoice.git"
RUN pip install --no-cache-dir --no-deps "MeloTTS @ git+https://github.com/myshell-ai/MeloTTS.git"
RUN pip install --no-cache-dir \
    fugashi protobuf pykakasi mecab-python3 transformers librosa \
    cn2an pypinyin jieba eng_to_ipa inflect unidic unidic-lite \
    gruut unidecode pydub langid \
    txtsplit cached_path num2words g2p_en anyascii jamo g2pkk \
    tqdm tensorboard loguru \
    faster-whisper wavmark whisper-timestamped
RUN python -m unidic download || true
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/local/nltk_data'); nltk.download('averaged_perceptron_tagger', download_dir='/usr/local/nltk_data'); nltk.download('cmudict', download_dir='/usr/local/nltk_data')"

RUN wget -q https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip -O /tmp/ckpt.zip && \
    unzip -q /tmp/ckpt.zip -d /tmp/ckpt_extract && \
    mv /tmp/ckpt_extract/checkpoints_v2 checkpoints_v2 || mv /tmp/ckpt_extract checkpoints_v2 && \
    rm -f /tmp/ckpt.zip && \
    ls -la checkpoints_v2/

COPY . .

RUN chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/.cache/huggingface
ENV OMP_NUM_THREADS=4

EXPOSE 7860

CMD ["sh", "-c", "OMP_NUM_THREADS=4 uvicorn app:app --host 0.0.0.0 --port 7860"]
