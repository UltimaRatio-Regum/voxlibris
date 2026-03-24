# TomeVox TTS Engine API Contract

**Version:** 1.0
**Last Updated:** 2026-03-21

## Overview

This document defines the REST API contract that any TTS (Text-to-Speech) engine must implement to integrate with the TomeVox audiobook generator. TomeVox uses a dependency-injection model: engine implementors expose two HTTP endpoints at a configurable base URL, and TomeVox discovers capabilities and generates audio by calling those endpoints.

All request/response bodies use JSON (`application/json`) unless otherwise noted. Audio responses use `audio/wav` with PCM encoding.

---

## Authentication

If the engine requires authentication, TomeVox will send a Bearer token in the `Authorization` header on every request:

```
Authorization: Bearer <api_key>
```

The API key is configured per-engine in TomeVox settings. Engines that do not require authentication should ignore this header.

---

## Endpoints

### 1. `POST /GetEngineDetails`

Returns the engine's capabilities, configuration, and available voices. TomeVox calls this endpoint when an engine is first registered and periodically to refresh cached metadata.

#### Request

**Method:** `POST`  
**Content-Type:** `application/json`  
**Body:** Empty JSON object `{}` (reserved for future parameters)

#### Response

**Content-Type:** `application/json`  
**Status:** `200 OK`

```json
{
  "engine_id": "chatterbox-tts",
  "engine_name": "Chatterbox TTS",
  "sample_rate": 24000,
  "bit_depth": 16,
  "channels": 1,
  "max_seconds_per_conversion": 30,
  "supports_voice_cloning": true,
  "builtin_voices": [
    {
      "id": "voice_001",
      "display_name": "Sarah (American English)",
      "extra_info": "Warm, conversational female voice",
      "voice_sample_url": "https://example.com/samples/sarah.wav"
    },
    {
      "id": "voice_002",
      "display_name": "James (British English)",
      "extra_info": "Deep, authoritative male voice",
      "voice_sample_url": null
    }
  ],
  "supported_emotions": [
    "neutral", "happy", "sad", "angry", "fear",
    "surprise", "disgust", "excited", "calm"
  ],
  "extra_properties": {}
}
```

#### Response Schema

The response is a flat dictionary of engine properties. The following keys are defined. Implementors **must** include all required keys. New keys may be appended in future versions; clients must ignore unknown keys.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `engine_id` | `string` | Yes | Unique identifier for this engine type. Used by TomeVox to detect duplicates. Must be lowercase alphanumeric with hyphens (e.g., `"chatterbox-tts"`, `"edge-tts"`). |
| `engine_name` | `string` | Yes | Human-readable display name shown in the TomeVox UI (e.g., `"Chatterbox TTS"`). |
| `sample_rate` | `integer` | Yes | Sample rate of output audio in Hz (e.g., `24000`, `22050`, `44100`). |
| `bit_depth` | `integer` | Yes | Bit depth of output audio (e.g., `16`, `24`). |
| `channels` | `integer` | Yes | Number of audio channels (`1` for mono, `2` for stereo). Mono is strongly recommended. |
| `max_seconds_per_conversion` | `integer` | Yes | Suggested maximum audio duration per request in seconds. TomeVox uses this to estimate chunk sizes. Not a hard limit. |
| `supports_voice_cloning` | `boolean` | Yes | Whether the engine can clone a voice from a provided audio sample. |
| `builtin_voices` | `array` | Yes | List of available built-in voices. Empty array `[]` if no built-in voices. See **Voice Object** below. |
| `supported_emotions` | `array` | No | List of emotion names the engine natively handles. If omitted, TomeVox will pass emotions but the engine may ignore them. |
| `extra_properties` | `object` | No | Reserved for future engine-specific configuration. Should be an empty object `{}` if unused. |
| `engine_params` | `array` | No | Declares engine-specific tunable parameters. TomeVox reads this once on registration and presents the parameters as UI controls. Each entry is a **Parameter Object** (see below). Omit or return `[]` if the engine has no tunable knobs. |

#### Parameter Object Schema

Each entry in `engine_params` has the following structure:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `short_name` | `string` | Yes | Machine-readable key, used as the key in `engine_options` when calling `ConvertTextToSpeech`. |
| `friendly_name` | `string` | Yes | Human-readable label shown in the UI. |
| `data_type` | `string` | Yes | One of `"int"`, `"float"`, `"string"`, `"list"`. Controls the input widget rendered by TomeVox. |
| `default_value` | any | Yes | Default value used when no value has been set by the user. |
| `min_value` | `number` | No | Minimum value for `int` / `float` parameters. |
| `max_value` | `number` | No | Maximum value for `int` / `float` parameters. |
| `list_options` | `array[string]` | No | Required when `data_type` is `"list"`. The allowed option values. |

---

#### Voice Object Schema

Each entry in `builtin_voices` has the following structure:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | `string` | Yes | Unique identifier for this voice, passed back in `ConvertTextToSpeech` as `builtin_voice_id`. |
| `display_name` | `string` | Yes | Human-readable name displayed in voice selection UI. |
| `extra_info` | `string` | No | Additional description (e.g., accent, characteristics). Displayed as subtitle text. |
| `voice_sample_url` | `string\|null` | No | Full URL to a preview audio sample. `null` if unavailable. |

---

### 2. `POST /ConvertTextToSpeech`

Converts input text to speech audio. Returns a PCM-encoded WAV file.

#### Request

**Method:** `POST`  
**Content-Type:** `application/json`

```json
{
  "input_text": "The quick brown fox jumped over the lazy dog.",
  "builtin_voice_id": "voice_001",
  "voice_to_clone_sample": null,
  "random_seed": 42,
  "emotion_set": ["happy", "excited"],
  "intensity": 70,
  "volume": 80,
  "speed_adjust": 1.5,
  "pitch_adjust": -0.5
}
```

#### Request Schema

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `input_text` | `string` | Yes | — | The text to convert to speech. |
| `builtin_voice_id` | `string\|null` | No | `null` | ID of a built-in voice from `GetEngineDetails.builtin_voices`. If the engine has built-in voices and this is `null`, the engine should use its default voice. Ignored if engine has no built-in voice list. |
| `voice_to_clone_sample` | `string\|null` | No | `null` | Base64-encoded PCM WAV file bytes for voice cloning. If the engine does not support voice cloning, this parameter must be accepted but ignored. When provided alongside `builtin_voice_id`, the clone sample takes priority. |
| `random_seed` | `integer\|null` | No | `null` | Random seed for reproducible generation. `null` means the engine picks randomly. Engines that don't support seeded generation should ignore this. |
| `emotion_set` | `array[string]` | No | `["neutral"]` | Ordered list of emotions. The first element is the dominant emotion; subsequent elements are modifiers. Each value is chosen from: `neutral`, `happy`, `sad`, `angry`, `fear`, `surprise`, `disgust`, `excited`, `calm`, `confused`, `anxious`, `hopeful`, `melancholy`, `fearful`. If the engine handles emotions natively, it should map these to its internal emotion system. If empty or omitted, default to neutral tone. |
| `intensity` | `integer` | No | `50` | Emotional intensity, range `1`–`100`. Scale to engine's internal range. Higher = more emotionally expressive. |
| `volume` | `integer` | No | `75` | Output volume, range `1`–`100`. Scale to engine's internal range. |
| `speed_adjust` | `float` | No | `0.0` | Speed adjustment as a percentage, range `-5.0` to `5.0`. Positive = faster, negative = slower. For example, `2.0` means 2% faster. Engines with complex emotion handling may choose to ignore this. |
| `pitch_adjust` | `float` | No | `0.0` | Pitch adjustment as a percentage, range `-5.0` to `5.0`. Positive = higher pitch, negative = lower. For example, `-1.5` means 1.5% lower pitch. Engines with complex emotion handling may choose to ignore this. |
| `engine_options` | `object\|null` | No | `null` | Engine-specific parameters declared via `GetEngineDetails.engine_params`. Keys and value types are engine-defined. Engines that don't recognize this field should ignore it entirely. |

#### Response

**Content-Type:** `audio/wav`  
**Status:** `200 OK`

The response body is the raw bytes of a PCM-encoded WAV file. The audio format (sample rate, bit depth, channels) must match what was reported in `GetEngineDetails`.

#### Error Response

**Content-Type:** `application/json`  
**Status:** `4xx` or `5xx`

```json
{
  "error": "Input text exceeds maximum supported length",
  "error_code": "TEXT_TOO_LONG",
  "details": "Maximum 500 characters per request"
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `error` | `string` | Yes | Human-readable error message. |
| `error_code` | `string` | No | Machine-readable error code (e.g., `TEXT_TOO_LONG`, `VOICE_NOT_FOUND`, `CLONING_NOT_SUPPORTED`). |
| `details` | `string` | No | Additional context about the error. |

---

## Standard Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TEXT_TOO_LONG` | 400 | Input text exceeds the engine's supported length. |
| `VOICE_NOT_FOUND` | 404 | The specified `builtin_voice_id` does not exist. |
| `CLONING_NOT_SUPPORTED` | 400 | Voice cloning sample was provided but the engine does not support cloning. |
| `INVALID_EMOTION` | 400 | One or more emotions in `emotion_set` are not recognized. |
| `GENERATION_FAILED` | 500 | Internal engine error during audio generation. |
| `RATE_LIMITED` | 429 | Too many requests; retry after the indicated period. |

---

## Implementation Notes

### For Engine Implementors

1. **Both endpoints must be available** at the configured base URL: `{base_url}/GetEngineDetails` and `{base_url}/ConvertTextToSpeech`.

2. **WAV format requirements:** Output must be a valid WAV file with PCM encoding (not compressed formats like MP3 or OGG). The sample rate, bit depth, and channel count must match what `GetEngineDetails` reports.

3. **Voice cloning parameter:** Even if your engine does not support voice cloning, your `ConvertTextToSpeech` endpoint must accept the `voice_to_clone_sample` parameter without error. Simply ignore it if cloning is not supported.

4. **Emotion handling:** Every engine **must** accept `emotion_set` and `intensity` and map them internally. The engine is responsible for translating emotion words into its own parameter space. Three strategies:
   - **Native parameter mapping:** Map the emotion to engine-specific generation parameters (e.g., Chatterbox maps to exaggeration + cfg_weight + temperature; StyleTTS2 maps to diffusion presets alpha/beta/embedding_scale).
   - **Instruct/prompt-based:** Pass the emotion as a text instruction to the model (e.g., Qwen3-TTS uses instruct prompts like "Speak with a happy, cheerful tone").
   - **Prosody emulation:** For engines without native emotion support, map emotions to speed and pitch adjustments (e.g., XTTSv2 and OpenVoice V2 use per-emotion speed multipliers and pitch semitone offsets).
   
   All engines should also apply **prosody reinforcement** — subtle speed/pitch adjustments layered on top of native emotion controls — so the emotion is expressed through both the model's native capabilities and post-processing. User `speed_adjust` and `pitch_adjust` values are additive on top of the engine's emotion-derived adjustments. The `intensity` parameter (1-100, default 50) scales how strongly the emotion affects generation parameters.

5. **Idempotency:** When `random_seed` is provided with the same value, the engine should produce identical output (if the underlying model supports deterministic generation).

6. **Graceful degradation:** If a requested feature is not supported (e.g., an unrecognized emotion), the engine should generate audio with its best default behavior rather than returning an error, unless the request is fundamentally invalid.

### For TomeVox (Client Behavior)

1. **Chunking:** TomeVox splits text into chunks based on `max_seconds_per_conversion` from `GetEngineDetails`. Each chunk is sent as a separate `ConvertTextToSpeech` request.

2. **Voice selection priority:** If `voice_to_clone_sample` is provided, it takes precedence over `builtin_voice_id`. TomeVox will only send one of the two in most cases.

3. **Caching:** TomeVox caches `GetEngineDetails` responses in PostgreSQL. The response is refreshed when the user explicitly tests/refreshes an engine from settings.

4. **Retry policy:** On `429` or `5xx` errors, TomeVox retries with exponential backoff (max 3 retries).

---

## JSON Schema (Formal)

### GetEngineDetails Response

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GetEngineDetailsResponse",
  "type": "object",
  "required": [
    "engine_id",
    "engine_name",
    "sample_rate",
    "bit_depth",
    "channels",
    "max_seconds_per_conversion",
    "supports_voice_cloning",
    "builtin_voices"
  ],
  "properties": {
    "engine_id": {
      "type": "string",
      "pattern": "^[a-z0-9-]+$",
      "description": "Unique engine identifier"
    },
    "engine_name": {
      "type": "string",
      "description": "Human-readable engine name"
    },
    "sample_rate": {
      "type": "integer",
      "minimum": 8000,
      "maximum": 96000,
      "description": "Output sample rate in Hz"
    },
    "bit_depth": {
      "type": "integer",
      "enum": [8, 16, 24, 32],
      "description": "Output bit depth"
    },
    "channels": {
      "type": "integer",
      "enum": [1, 2],
      "description": "Number of audio channels"
    },
    "max_seconds_per_conversion": {
      "type": "integer",
      "minimum": 1,
      "maximum": 300,
      "description": "Suggested max duration per request"
    },
    "supports_voice_cloning": {
      "type": "boolean",
      "description": "Whether voice cloning is supported"
    },
    "builtin_voices": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "display_name"],
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique voice identifier"
          },
          "display_name": {
            "type": "string",
            "description": "Human-readable voice name"
          },
          "extra_info": {
            "type": "string",
            "description": "Additional voice description"
          },
          "voice_sample_url": {
            "type": ["string", "null"],
            "format": "uri",
            "description": "URL to voice preview audio"
          }
        }
      },
      "description": "Available built-in voices"
    },
    "supported_emotions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Emotions the engine natively supports"
    },
    "extra_properties": {
      "type": "object",
      "description": "Reserved for future engine-specific configuration"
    },
    "engine_params": {
      "type": "array",
      "description": "Engine-specific tunable parameters exposed to the TomeVox UI",
      "items": {
        "type": "object",
        "required": ["short_name", "friendly_name", "data_type", "default_value"],
        "properties": {
          "short_name": { "type": "string" },
          "friendly_name": { "type": "string" },
          "data_type": { "type": "string", "enum": ["int", "float", "string", "list"] },
          "default_value": {},
          "min_value": { "type": "number" },
          "max_value": { "type": "number" },
          "list_options": { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  },
  "additionalProperties": true
}
```

### ConvertTextToSpeech Request

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ConvertTextToSpeechRequest",
  "type": "object",
  "required": ["input_text"],
  "properties": {
    "input_text": {
      "type": "string",
      "minLength": 1,
      "description": "Text to convert to speech"
    },
    "builtin_voice_id": {
      "type": ["string", "null"],
      "description": "ID of a built-in voice"
    },
    "voice_to_clone_sample": {
      "type": ["string", "null"],
      "description": "Base64-encoded PCM WAV file for voice cloning"
    },
    "random_seed": {
      "type": ["integer", "null"],
      "description": "Seed for reproducible generation"
    },
    "emotion_set": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "neutral", "happy", "sad", "angry", "fear",
          "surprise", "disgust", "excited", "calm", "confused",
          "anxious", "hopeful", "melancholy", "fearful"
        ]
      },
      "default": ["neutral"],
      "description": "Ordered emotion list (first = dominant)"
    },
    "intensity": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 50,
      "description": "Emotional intensity"
    },
    "volume": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 75,
      "description": "Output volume"
    },
    "speed_adjust": {
      "type": "number",
      "minimum": -5.0,
      "maximum": 5.0,
      "default": 0.0,
      "description": "Speed adjustment percentage"
    },
    "pitch_adjust": {
      "type": "number",
      "minimum": -5.0,
      "maximum": 5.0,
      "default": 0.0,
      "description": "Pitch adjustment percentage"
    },
    "engine_options": {
      "type": ["object", "null"],
      "description": "Engine-specific parameters. Keys and value types are engine-defined. Engines that don't recognize this field should ignore it.",
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```
