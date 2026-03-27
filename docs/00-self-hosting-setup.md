---
title: Self-Hosting Setup
description: Step-by-step guide to deploying narrate.ink — environment variables, database, API keys, and TTS engines
category: Setup
order: 0
keywords: [setup, self-hosting, docker, postgres, openrouter, huggingface, environment variables, API key]
---

# Self-Hosting Setup

This guide walks through everything needed to run narrate.ink from scratch: obtaining an API key, configuring the environment, deploying the application, and connecting a TTS engine.

---

## 1. Obtain an OpenRouter API Key

narrate.ink uses a language model for two purposes:

- **Text segmentation & speaker detection** — parsing uploaded text into chunks, identifying speakers, and assigning emotions
- **AI voice analysis** — extracting display name, gender, accent, and a speech transcript from voice samples (optional)

Both require an OpenAI-compatible API endpoint. [OpenRouter](https://openrouter.ai) is recommended because it provides access to many models (GPT-4o, Claude, Gemini, Llama, etc.) through a single key with pay-as-you-go pricing.

**Steps:**

1. Go to [openrouter.ai](https://openrouter.ai) and create an account
2. Navigate to **Keys** in your account dashboard
3. Click **Create Key**, give it a name, and copy the generated key — it starts with `sk-or-`
4. Add credits to your account (the LLM calls for a typical novel cost a few cents)

> **Alternative:** Any endpoint that speaks the OpenAI chat-completions format works — a local [Ollama](https://ollama.com) instance, vLLM, LM Studio, or any hosted provider. You will need its base URL and API key (if required).

---

## 2. Set Environment Variables

narrate.ink is configured through environment variables. The simplest approach is a `.env` file in the project root.

Copy the example file:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# --- Database ---
POSTGRES_USER=voxlibris
POSTGRES_PASSWORD=change-me-to-something-strong
POSTGRES_DB=voxlibris

# --- Session security ---
# Generate with: openssl rand -hex 32
SESSION_SECRET=replace-with-a-random-64-char-hex-string

# --- LLM integration (OpenRouter or compatible) ---
AI_INTEGRATIONS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_INTEGRATIONS_OPENROUTER_API_KEY=sk-or-...

# --- Optional: port mapping ---
APP_PORT=5000
DB_PORT=5432
```

### Full variable reference

| Variable | Required | Description |
|---|:---:|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string — set automatically by Docker Compose; set manually if running Postgres separately (see §3b) |
| `SESSION_SECRET` | ✅ | Random string used to sign session cookies. Generate with `openssl rand -hex 32` |
| `AI_INTEGRATIONS_OPENROUTER_BASE_URL` | Recommended | Base URL of the OpenAI-compatible LLM endpoint |
| `AI_INTEGRATIONS_OPENROUTER_API_KEY` | Recommended | API key for the LLM endpoint — required for text segmentation and voice analysis |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Docker Compose only | Credentials for the bundled Postgres container |
| `APP_PORT` | No | Host port narrate.ink listens on (default: `5000`) |
| `DB_PORT` | No | Host port the Postgres container exposes (default: `5432`) |
| `VOICE_ANALYSIS_MODEL` | No | LLM model used for voice analysis (default: `google/gemini-2.5-flash`) |
| `PYTHON_BACKEND_URL` | No | Override the internal Python backend URL (default: `http://127.0.0.1:8000`) |

---

## 3. Run the Application

### 3a. Docker Compose (Recommended)

The bundled `docker-compose.yml` starts both a Postgres container and the narrate.ink app container. This is the easiest way to get everything running.

```bash
docker compose up -d
```

The app will be available at `http://localhost:5000` (or the port you set in `APP_PORT`).

On first start, the database schema is created automatically. Log in with:

- **Username:** `Administrator`
- **Password:** `ChangeMe`

> **Change this password immediately** — click your username in the top-right corner and select **Change Password**.

To stop:

```bash
docker compose down
```

To update to a newer build:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 3b. External Postgres (Advanced)

If you already run Postgres separately (or prefer to manage the database yourself), skip the `db` service and set `DATABASE_URL` directly instead of the `POSTGRES_*` variables:

```env
DATABASE_URL=postgresql://myuser:mypassword@my-postgres-host:5432/voxlibris
```

You can also use the provided `docker-compose.yml` with only the `app` service enabled, or run the app directly with:

```bash
DATABASE_URL=postgresql://... SESSION_SECRET=... docker run -p 5000:5000 voxlibris:latest
```

The schema migration runs automatically at startup regardless of how you deploy.

---

## 4. Connect a TTS Engine

narrate.ink ships with two built-in engines that require no setup:

- **Edge TTS** — Microsoft Azure neural voices, cloud-based, free, no GPU required. Good for testing the full workflow end-to-end before setting up a GPU engine.
- **Soprano** — Ultra-fast local generation for quick previews.

For higher-quality voice cloning and expressive synthesis you will want a GPU-backed engine. The recommended approach is deploying one to a [HuggingFace Space](https://huggingface.co/spaces).

---

## 5. Deploy an Engine to HuggingFace Spaces (Optional)

This section walks through setting up a GPU-accelerated TTS engine on HuggingFace Spaces using the engine code included in the `engines/` directory. **Edge TTS requires no Space — skip to §6 if you just want to verify everything works first.**

### Available engines

| Folder | Engine | Voice cloning |
|---|---|:---:|
| `engines/chatterbox` | Chatterbox (Resemble AI) — recommended for quality | ✅ |
| `engines/xttsv2` | XTTSv2 (Coqui) — multilingual cloning | ✅ |
| `engines/styletts2` | StyleTTS2 — style-transfer synthesis | ✅ |
| `engines/qwen25-tts` | Qwen 2.5 TTS — Chinese/English | ✅ |
| `engines/qwen3-tts` | Qwen 3 TTS — Chinese/English, newer | ✅ |
| `engines/openvoice-v2` | OpenVoice V2 — voice conversion | ✅ |
| `engines/indextts2` | IndexTTS2 | ✅ |

### Step 1 — Create a new Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
2. Give your Space a name (e.g. `my-chatterbox`)
3. Set **Space SDK** to **Docker**
4. Leave everything else at defaults and click **Create Space**

The Space is created with an empty Docker repository.

### Step 2 — Clone the Space repository

```bash
git clone https://huggingface.co/spaces/<your-username>/<your-space-name>
cd <your-space-name>
```

You will need `git-lfs` installed (`brew install git-lfs` / `apt install git-lfs`).

### Step 3 — Copy the engine files

Copy all files from the engine folder in this repository into the cloned Space directory:

```bash
# example for Chatterbox — repeat with the engine folder you chose
cp -r /path/to/narrate.ink/engines/chatterbox/* .
```

Each engine folder contains a `Dockerfile`, `app.py`, `requirements.txt`, and an `index.html`.

### Step 4 — Commit and push

```bash
git add .
git commit -m "Add TTS engine"
git push
```

HuggingFace will automatically build the Docker image and start the Space. The first build takes a few minutes because it downloads model weights; subsequent cold starts are faster.

### Step 5 — Select GPU hardware

1. In your Space, click **Settings**
2. Under **Space hardware**, click **Upgrade**
3. Choose **A10G · Small** — best cost/performance balance for audiobook generation (~$1/hr while active)
4. Click **Save**

The Space will restart on the selected hardware. HuggingFace only bills for time the Space is running (it sleeps after inactivity by default).

### Step 6 — Set an API key to secure the endpoint

By default, a running Space is publicly reachable. Anyone with the URL could use your GPU quota. Protect it with a secret API key:

1. In your Space, go to **Settings → Variables and Secrets**
2. Click **New Secret**
3. Set the name to `API_KEY`
4. Set the value to a randomly generated string — a UUID works well:
   ```bash
   python3 -c "import uuid; print(uuid.uuid4())"
   ```
5. Click **Save**

The engine will now reject requests that do not include this key as a Bearer token.

### Step 7 — Register the engine in narrate.ink

1. Open narrate.ink and go to **Settings → Remote TTS Engines**
2. Click **Add Engine**
3. Fill in:
   - **Name** — a label for the engine (e.g. "Chatterbox - A10G")
   - **Endpoint URL** — the Space URL, which looks like `https://<username>-<space-name>.hf.space`
   - **API Token** — the `API_KEY` secret you set in Step 6
4. Click **Add Engine**

narrate.ink will call `POST /GetEngineDetails` on the Space, verify connectivity, and register the engine. It appears in the engine table with its status and voice count. If the Space is still building or warming up, narrate.ink will show it as **warming up** and poll automatically until it's ready.

---

## 6. Verify the Setup

1. **Log in** at `http://localhost:5000` (or your configured port)
2. Go to **Settings** and confirm your engine appears as **online**
3. Create a project via the **Project Wizard**:
   - Paste a paragraph of text with dialogue
   - Select an LLM model for analysis (requires OpenRouter key)
   - Choose Edge TTS or your registered engine as the TTS engine
4. Complete the wizard and start audio generation from the project editor
5. Monitor progress in the **Jobs** tab — chunks appear as they complete
6. Play back a completed chunk to verify audio quality

---

## 7. First Steps After Setup

- **Change the default admin password** — Settings → top-right user menu → Change Password
- **Disable open registration** — Users tab → Registration mode → Disabled (or Invite Only for shared installs)
- **Set a default engine and voice** — Settings → Default TTS Settings
- **Upload custom voice samples** — Settings → Custom Voices → Add Voice (for voice cloning engines)
- **Run AI voice analysis** — Settings → Voice Library → select voices → Analyze Selected (requires OpenRouter key with a vision-capable model such as `google/gemini-2.5-flash`)

---

## Troubleshooting

### The LLM call fails / no speakers are detected

- Verify `AI_INTEGRATIONS_OPENROUTER_API_KEY` is set correctly in `.env` and the container has been restarted since
- Confirm your OpenRouter account has credits
- Try a different model in the Project Wizard — some cheaper models have lower context windows that truncate long texts

### The TTS engine shows as offline or warming up

- Check the Space is not sleeping — open the Space URL in a browser to wake it
- Confirm the endpoint URL has no trailing slash
- Confirm the API Token in narrate.ink matches the `API_KEY` secret in the Space exactly
- Check the Space build logs for errors (HuggingFace Spaces → Logs tab)

### Database connection errors on startup

- Ensure the `db` container is healthy before the `app` container starts — Docker Compose handles this automatically via `depends_on: condition: service_healthy`
- If using an external Postgres instance, verify `DATABASE_URL` is reachable from inside the container (use the host's LAN IP, not `localhost`)

### Port conflicts

Change `APP_PORT` and/or `DB_PORT` in `.env` and restart:

```bash
docker compose down && docker compose up -d
```
