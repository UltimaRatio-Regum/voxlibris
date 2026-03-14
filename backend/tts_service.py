"""
TTS Service - Text-to-Speech generation using edge-tts or Chatterbox
"""

import os
import io
import asyncio
import numpy as np
import logging
from pathlib import Path
from typing import Optional
import tempfile

from models import TextSegment, ProjectConfig, Sentiment
from audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

EDGE_TTS_AVAILABLE = False
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    logger.info("edge-tts is available")
except ImportError:
    logger.warning("edge-tts not installed")

CHATTERBOX_AVAILABLE = False
try:
    from chatterbox.tts import ChatterboxTTS
    import torch
    if torch.cuda.is_available():
        CHATTERBOX_AVAILABLE = True
        logger.info("Chatterbox TTS with CUDA is available")
    else:
        logger.warning("Chatterbox requires CUDA")
except ImportError:
    pass

EDGE_TTS_VOICES = {
    "male_us": "en-US-GuyNeural",
    "female_us": "en-US-JennyNeural", 
    "male_uk": "en-GB-RyanNeural",
    "female_uk": "en-GB-SoniaNeural",
    "male_au": "en-AU-WilliamNeural",
    "female_au": "en-AU-NatashaNeural",
    "narrator": "en-US-ChristopherNeural",
    "default": "en-US-AriaNeural",
}

OPENAI_TTS_VOICES = {
    "alloy": "alloy",       # Neutral, balanced
    "echo": "echo",         # Male, warm
    "fable": "fable",       # British accent
    "onyx": "onyx",         # Deep, authoritative
    "nova": "nova",         # Female, energetic  
    "shimmer": "shimmer",   # Female, soft
    "default": "alloy",
}

SENTIMENT_EXAGGERATION_MAP = {
    "neutral": 0.5,
    "happy": 0.7,
    "sad": 0.6,
    "angry": 0.85,
    "fearful": 0.75,
    "surprised": 0.8,
    "disgusted": 0.7,
    "excited": 0.9,
    "calm": 0.4,
    "anxious": 0.75,
    "hopeful": 0.6,
    "melancholy": 0.55,
}


def get_sentiment_exaggeration(sentiment_label: str, sentiment_score: float, base_exaggeration: float = 0.5) -> float:
    """
    Calculate Chatterbox exaggeration parameter based on segment sentiment.
    Higher exaggeration = more expressive/emotional speech.
    
    Args:
        sentiment_label: The emotion label (e.g., "happy", "sad", "angry")
        sentiment_score: Confidence score 0-1 for the sentiment
        base_exaggeration: Default exaggeration from config
    
    Returns:
        Adjusted exaggeration value between 0.0 and 1.0
    """
    target_exaggeration = SENTIMENT_EXAGGERATION_MAP.get(sentiment_label.lower(), base_exaggeration)
    
    adjusted = base_exaggeration + (target_exaggeration - base_exaggeration) * sentiment_score
    
    return max(0.0, min(1.0, adjusted))


class TTSService:
    """
    Text-to-Speech service that uses:
    - Chatterbox when GPU available (voice cloning)
    - edge-tts for high-quality neural TTS (default)
    """
    
    def __init__(self):
        self.model = None
        self.sample_rate = 24000
        self.edge_voice = EDGE_TTS_VOICES["default"]
        
        if CHATTERBOX_AVAILABLE:
            try:
                self.model = ChatterboxTTS.from_pretrained(device="cuda")
                logger.info("Loaded Chatterbox TTS on CUDA")
            except Exception as e:
                logger.warning(f"Failed to load Chatterbox: {e}")
    
    async def generate_audiobook_async(
        self,
        segments: list[TextSegment],
        config: ProjectConfig,
        voice_files: dict[str, str],
        output_path: str,
        audio_processor: AudioProcessor,
        progress_callback=None,
    ):
        """
        Generate complete audiobook from text segments (async version).
        """
        audio_chunks = []
        total = len(segments)
        
        for i, segment in enumerate(segments):
            logger.info(f"Processing segment {i+1}/{total}: {segment.type} - '{segment.text[:50]}...'")
            
            if progress_callback:
                progress_callback(i, total, f"Generating audio for segment {i+1}/{total}")
            
            voice_id = None
            pitch_offset = 0.0
            speed_factor = 1.0
            edge_voice = self.edge_voice
            openai_voice = "alloy"
            
            if segment.type == "dialogue" and segment.speaker:
                speaker_config = config.speakers.get(segment.speaker)
                if speaker_config:
                    voice_id = speaker_config.voiceSampleId
                    pitch_offset = speaker_config.pitchOffset
                    speed_factor = speaker_config.speedFactor
            else:
                voice_id = config.narratorVoiceId
                speed_factor = getattr(config, 'narratorSpeed', 1.0) or 1.0
            
            # Parse voice ID prefixes for different TTS engines
            voice_path = None
            if voice_id:
                if voice_id.startswith("edge:"):
                    # Azure neural voice (e.g., "edge:en-US-AriaNeural")
                    edge_voice = voice_id.replace("edge:", "")
                elif voice_id.startswith("openai:"):
                    # OpenAI voice (e.g., "openai:alloy")
                    openai_voice = voice_id.replace("openai:", "")
                elif voice_id.startswith("library:"):
                    # Voice library sample for Chatterbox
                    voice_path = voice_files.get(voice_id)
                elif voice_id.startswith("edge_"):
                    # Legacy format
                    edge_voice = EDGE_TTS_VOICES.get(voice_id.replace("edge_", ""), self.edge_voice)
                elif voice_id != "none":
                    # Uploaded voice sample
                    voice_path = voice_files.get(voice_id)
            
            exaggeration = config.defaultExaggeration
            is_voice_cloning = config.ttsEngine in ("chatterbox", "chatterbox-free", "chatterbox-paid", "hf-tts-paid", "styletts2")
            if is_voice_cloning and segment.sentiment:
                exaggeration = get_sentiment_exaggeration(
                    segment.sentiment.label,
                    segment.sentiment.score,
                    config.defaultExaggeration,
                )
                logger.info(f"  Chatterbox exaggeration adjusted to {exaggeration:.2f} for sentiment '{segment.sentiment.label}'")
            
            # For StyleTTS2, pass emotion and compute sentiment-derived speed/pitch
            emotion_label = segment.sentiment.label if segment.sentiment else None
            
            # Compute StyleTTS2 speed/pitch including sentiment adjustments
            styletts2_speed = speed_factor
            styletts2_pitch = pitch_offset
            if config.ttsEngine == "styletts2" and segment.sentiment:
                # Apply sentiment-based adjustments using prosody weights
                sentiment_adjustments = audio_processor.get_sentiment_prosody_adjustments(
                    segment.sentiment.label,
                    segment.sentiment.score,
                    base_pitch_offset=pitch_offset,
                    base_speed_factor=speed_factor,
                )
                styletts2_speed = sentiment_adjustments.get("speed", speed_factor)
                styletts2_pitch = sentiment_adjustments.get("pitch", pitch_offset)
                logger.info(f"  StyleTTS2 sentiment adjustments: speed={styletts2_speed:.2f}, pitch={styletts2_pitch:.2f}")
            
            audio = await self._generate_segment_audio_async(
                text=segment.text,
                voice_path=voice_path,
                edge_voice=edge_voice if config.ttsEngine == "edge-tts" else None,
                openai_voice=openai_voice if config.ttsEngine == "openai" else None,
                exaggeration=exaggeration,
                tts_engine=config.ttsEngine,
                emotion=emotion_label,
                speed=styletts2_speed if config.ttsEngine == "styletts2" else 1.0,
                pitch=styletts2_pitch if config.ttsEngine == "styletts2" else 0.0,
            )
            
            # Skip prosody post-processing for StyleTTS2 (it handles speed/pitch/emotion natively)
            if config.ttsEngine == "styletts2":
                logger.info(f"  StyleTTS2 applied native emotion={emotion_label}, speed={styletts2_speed:.2f}, pitch={styletts2_pitch:.2f}")
            elif segment.sentiment:
                logger.info(f"  Applying prosody for sentiment: {segment.sentiment.label} (score: {segment.sentiment.score:.2f})")
                audio = audio_processor.apply_sentiment_prosody(
                    audio_data=audio,
                    sample_rate=self.sample_rate,
                    sentiment_label=segment.sentiment.label,
                    sentiment_score=segment.sentiment.score,
                    base_pitch_offset=pitch_offset,
                    base_speed_factor=speed_factor,
                )
            elif pitch_offset != 0 or speed_factor != 1.0:
                if pitch_offset != 0:
                    audio = audio_processor.apply_pitch_shift(audio, self.sample_rate, pitch_offset)
                if speed_factor != 1.0:
                    audio = audio_processor.apply_time_stretch(audio, self.sample_rate, speed_factor)
            
            # Trim trailing silence from each chunk to prevent gaps
            audio = audio_processor.trim_trailing_silence(
                audio, 
                self.sample_rate,
                block_ms=50,
                silence_threshold=0.01,
                min_silence_duration_ms=500,
            )
            
            audio_chunks.append(audio)
        
        if progress_callback:
            progress_callback(total, total, "Concatenating audio...")
        
        logger.info(f"Concatenating {len(audio_chunks)} audio chunks with {config.pauseBetweenSegments}ms pauses")
        final_audio = audio_processor.concatenate_audio(
            audio_chunks,
            self.sample_rate,
            config.pauseBetweenSegments,
        )
        
        final_audio = audio_processor.normalize_audio(final_audio)
        
        audio_processor.save_audio(output_path, final_audio, self.sample_rate)
        logger.info(f"Saved audiobook to {output_path} ({len(final_audio) / self.sample_rate:.1f} seconds)")
        
        return output_path
    
    def generate_audiobook(
        self,
        segments: list[TextSegment],
        config: ProjectConfig,
        voice_files: dict[str, str],
        output_path: str,
        audio_processor: AudioProcessor,
        progress_callback=None,
    ):
        """
        Synchronous wrapper for generate_audiobook_async.
        """
        return asyncio.run(self.generate_audiobook_async(
            segments, config, voice_files, output_path, audio_processor, progress_callback
        ))
    
    async def _generate_segment_audio_async(
        self,
        text: str,
        voice_path: Optional[str] = None,
        edge_voice: Optional[str] = "en-US-AriaNeural",
        openai_voice: Optional[str] = "alloy",
        exaggeration: float = 0.5,
        tts_engine: str = "edge-tts",
        emotion: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> np.ndarray:
        """
        Generate audio for a single text segment.
        Dispatches to the appropriate TTS engine based on config.
        Raises exceptions if the engine fails (no fallbacks).
        """
        if tts_engine == "chatterbox-free" or tts_engine == "chatterbox":
            # "chatterbox" is legacy, treat as chatterbox-free
            if tts_engine == "chatterbox":
                logger.info("Legacy 'chatterbox' engine mapped to 'chatterbox-free'")
            return await self._generate_with_chatterbox_free(text, voice_path, exaggeration)
        elif tts_engine in ("chatterbox-paid", "hf-tts-paid"):
            # HuggingFace TTS Paid - uses model from tts_settings.json
            return await self._generate_with_chatterbox_paid(text, voice_path, exaggeration)
        elif tts_engine == "styletts2":
            # StyleTTS2 - standalone HF Space with emotion support and native speed/pitch
            return await self._generate_with_styletts2(text, voice_path, emotion=emotion, speed=speed, pitch=pitch)
        elif tts_engine == "openai":
            # Use passed openai_voice, fallback to default if invalid
            voice = OPENAI_TTS_VOICES.get(openai_voice, OPENAI_TTS_VOICES["default"]) if openai_voice else "alloy"
            return await self._generate_with_openai(text, voice)
        elif tts_engine == "piper":
            return await self._generate_with_piper(text, voice_path)
        elif tts_engine == "soprano":
            return await self._generate_with_soprano(text)
        elif tts_engine == "edge-tts":
            if not EDGE_TTS_AVAILABLE:
                raise RuntimeError("edge-tts is not installed. Please install it with: pip install edge-tts")
            return await self._generate_with_edge_tts(text, edge_voice or "en-US-AriaNeural")
        else:
            raise ValueError(f"Unknown TTS engine: {tts_engine}")
    
    async def _generate_with_chatterbox_free(
        self,
        text: str,
        voice_path: Optional[str] = None,
        exaggeration: float = 0.5,
    ) -> np.ndarray:
        """
        Generate audio using Chatterbox TTS via free HuggingFace Spaces.
        Tries local GPU model first, then HuggingFace Spaces via Gradio.
        Raises exceptions on failure (no fallbacks).
        """
        if not voice_path:
            raise ValueError("Chatterbox Free requires a voice sample. Please select a voice from the library or upload one.")
        
        # Try local Chatterbox with CUDA first
        if self.model is not None:
            try:
                wav = self.model.generate(
                    text,
                    audio_prompt_path=voice_path,
                    exaggeration=exaggeration,
                )
                return wav.numpy().flatten()
            except Exception as e:
                logger.warning(f"Local Chatterbox generation failed: {e}, trying Gradio API...")
        
        # Try HuggingFace Spaces via Gradio client
        return await self._generate_with_chatterbox_gradio(text, voice_path, exaggeration)
    
    async def _generate_with_chatterbox_paid(
        self,
        text: str,
        voice_path: Optional[str] = None,
        exaggeration: float = 0.5,
        model_override: Optional[str] = None,
    ) -> np.ndarray:
        """
        Generate audio using Chatterbox TTS via custom HuggingFace Space (Gradio client).
        Uses api_name="/gradio_api/api/tts_to_mp3" with (text, seed, voice_reference_audio).
        Returns MP3 audio which is decoded to numpy array.
        Raises exceptions on failure (no fallbacks).
        """
        from chatterbox_config import CHATTERBOX_PAID_CONFIG, is_paid_chatterbox_configured, load_tts_settings
        from gradio_client import Client, handle_file
        import soundfile as sf
        import io
        
        if not is_paid_chatterbox_configured():
            raise RuntimeError("Chatterbox Paid is not configured. Please set CHATTERBOX_API_URL environment variable.")
        
        if not voice_path:
            raise ValueError("Chatterbox Paid requires a voice sample. Please select a voice from the library or upload one.")
        
        if not os.path.exists(voice_path):
            raise FileNotFoundError(f"Voice file not found: {voice_path}")
        
        config = CHATTERBOX_PAID_CONFIG
        
        # Apply character limit if configured (0 = no limit)
        if config["max_chars"] > 0 and len(text) > config["max_chars"]:
            truncated = text[:config["max_chars"]]
            last_space = truncated.rfind(' ')
            if last_space > config["max_chars"] * 0.6:
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters for Chatterbox paid")
        
        try:
            space_url = config["space_url"]
            api_key = config.get("api_key", "")
            timeout_secs = config.get("timeout", 120)
            
            # Load dynamic settings from tts_settings.json (set via Settings tab)
            tts_settings = load_tts_settings()
            
            # Multi-model parameters - use override if provided, else prefer tts_settings.json
            if model_override:
                model = model_override
                logger.info(f"Using model override: {model}")
            else:
                model = tts_settings.get("chatterbox_model", config.get("model", "qwen3"))
            language = config.get("language", "English")
            qwen_model_id = config.get("qwen_model_id", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
            qwen_x_vector_only_mode = config.get("qwen_x_vector_only_mode", False)
            
            # StyleTTS2 parameters - prefer tts_settings.json
            st_alpha = tts_settings.get("st_alpha", config.get("st_alpha", 0.3))
            st_beta = tts_settings.get("st_beta", config.get("st_beta", 0.7))
            st_diffusion_steps = tts_settings.get("st_diffusion_steps", config.get("st_diffusion_steps", 5))
            st_embedding_scale = tts_settings.get("st_embedding_scale", config.get("st_embedding_scale", 1.0))
            
            # Try to load voice transcript for VCTK samples (improves Qwen3 quality)
            ref_text = None
            if voice_path and model == "qwen3":
                transcript_path = voice_path.replace(".wav", ".txt").replace(".flac", ".txt")
                if os.path.exists(transcript_path):
                    try:
                        with open(transcript_path, 'r') as f:
                            ref_text = f.read().strip()
                        logger.info(f"Loaded voice transcript: {ref_text[:50]}...")
                    except Exception as e:
                        logger.warning(f"Failed to load transcript: {e}")
                
                # If no transcript available for Qwen3, use x_vector_only_mode
                if not ref_text:
                    qwen_x_vector_only_mode = True
                    logger.info("No transcript found, enabling qwen_x_vector_only_mode")
            
            logger.info(f"Connecting to Chatterbox paid space: {space_url} (model: {model})")
            
            # Run in executor to avoid blocking
            loop = asyncio.get_running_loop()
            
            def call_gradio():
                import httpx
                
                # Set longer timeout for httpx (default is 10s which is too short for TTS)
                httpx_kwargs = {
                    "timeout": httpx.Timeout(timeout_secs, connect=60.0)
                }
                
                # Pass API key as Bearer token in Authorization header
                if api_key:
                    httpx_kwargs["headers"] = {
                        "Authorization": f"Bearer {api_key}"
                    }
                    logger.info("Using Bearer token authentication")
                
                client_kwargs = {"httpx_kwargs": httpx_kwargs}
                
                client = Client(space_url, **client_kwargs)
                # Multi-model API with all parameters:
                # (text, backend, language, voice_wav, ref_text, 
                #  qwen_x_vector_only_mode, qwen_model_id,
                #  st_alpha, st_beta, st_diffusion_steps, st_embedding_scale)
                result = client.predict(
                    text,                           # text to speak
                    model,                          # backend: chatterbox, xtts_v2, styletts2, qwen3
                    language,                       # language (e.g., "English", "en")
                    handle_file(voice_path),        # voice_wav: reference audio file
                    ref_text,                       # ref_text: transcript of voice sample (Qwen3)
                    qwen_x_vector_only_mode,        # qwen_x_vector_only_mode
                    qwen_model_id,                  # qwen_model_id
                    st_alpha,                       # StyleTTS2: voice style strength
                    st_beta,                        # StyleTTS2: prosody emphasis
                    st_diffusion_steps,             # StyleTTS2: diffusion steps
                    st_embedding_scale,             # StyleTTS2: speaker identity scale
                    api_name="/tts_to_mp3"
                )
                return result
            
            # Apply timeout to the executor call
            result = await asyncio.wait_for(
                loop.run_in_executor(None, call_gradio),
                timeout=timeout_secs
            )
            
            logger.info(f"Chatterbox paid result type: {type(result)}, value: {result}")
            
            # Result should be a file path to MP3
            if isinstance(result, str):
                audio_file_path = result
            elif hasattr(result, 'path'):
                audio_file_path = result.path
            elif hasattr(result, 'name'):
                audio_file_path = result.name
            elif isinstance(result, (list, tuple)) and len(result) > 0:
                first = result[0]
                if isinstance(first, str):
                    audio_file_path = first
                elif hasattr(first, 'path'):
                    audio_file_path = first.path
                elif hasattr(first, 'name'):
                    audio_file_path = first.name
                else:
                    raise RuntimeError(f"Unexpected result format: {type(first)}")
            else:
                raise RuntimeError(f"Unexpected result format: {type(result)}")
            
            logger.info(f"Audio file path: {audio_file_path}")
            
            # Read the MP3 file - use pydub for MP3 decoding
            from pydub import AudioSegment
            
            audio_segment = AudioSegment.from_file(audio_file_path, format="mp3")
            
            # Convert to numpy array
            samples = np.array(audio_segment.get_array_of_samples())
            
            # Handle stereo -> mono conversion
            if audio_segment.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)
            
            # Normalize to float32 [-1, 1]
            audio = samples.astype(np.float32) / (2 ** (audio_segment.sample_width * 8 - 1))
            
            # Resample if needed
            if audio_segment.frame_rate != self.sample_rate:
                from scipy import signal
                audio = signal.resample(audio, int(len(audio) * self.sample_rate / audio_segment.frame_rate))
            
            logger.info(f"Chatterbox paid generated {len(audio)/self.sample_rate:.2f}s of audio")
            return audio.astype(np.float32)
        
        except asyncio.TimeoutError:
            logger.error(f"Chatterbox paid timed out after {timeout_secs}s")
            raise RuntimeError(f"Chatterbox Paid timed out after {timeout_secs} seconds") from None
        except Exception as e:
            logger.error(f"Chatterbox paid space failed: {e}")
            raise RuntimeError(f"Chatterbox Paid generation failed: {e}") from e
    
    async def _generate_with_chatterbox_gradio(
        self,
        text: str,
        voice_path: str,
        exaggeration: float = 0.5,
        temperature: float = 0.8,
        cfg_weight: float = 0.5,
    ) -> np.ndarray:
        """
        Generate audio using Chatterbox TTS via HuggingFace Spaces Gradio API.
        Max 300 characters per request.
        """
        from gradio_client import Client, handle_file
        import soundfile as sf
        
        # Validate inputs
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided to Chatterbox Gradio")
            raise ValueError("Text cannot be empty")
        
        # Validate voice_path exists
        if not os.path.exists(voice_path):
            logger.warning(f"Voice file not found: {voice_path}")
            raise FileNotFoundError(f"Voice reference file not found: {voice_path}")
        
        logger.info(f"Generating with Chatterbox Gradio (text length: {len(text)})")
        
        # Chatterbox has a 300 character limit - truncate at word boundary
        if len(text) > 300:
            truncated = text[:300]
            # Try to truncate at word boundary
            last_space = truncated.rfind(' ')
            if last_space > 200:  # Only use word boundary if reasonable
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters for Chatterbox")
        
        def call_gradio():
            client = Client("ResembleAI/Chatterbox")
            result = client.predict(
                text_input=text,
                audio_prompt_path_input=handle_file(voice_path),
                exaggeration_input=exaggeration,
                temperature_input=temperature,
                seed_num_input=0,  # Random seed
                cfgw_input=cfg_weight,
                vad_trim_input=False,
                api_name="/generate_tts_audio"
            )
            return result
        
        try:
            # Run synchronous Gradio call in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, call_gradio)
        except Exception as e:
            logger.error(f"Chatterbox Gradio API call failed: {e}")
            raise RuntimeError(f"Chatterbox Free generation failed (HuggingFace Space may be unavailable or quota exceeded): {e}") from e
        
        logger.info(f"Chatterbox Gradio result type: {type(result)}")
        
        # Handle different return types from gradio_client
        # Can be a string path, tuple, or FileData object
        if isinstance(result, str):
            result_path = result
        elif isinstance(result, (list, tuple)):
            result_path = result[0]
        elif hasattr(result, 'path'):
            # FileData object
            result_path = result.path
        else:
            logger.error(f"Unexpected Gradio result type: {type(result)}")
            raise ValueError(f"Unexpected result from Chatterbox: {type(result)}")
        
        logger.info(f"Reading audio from: {result_path}")
        
        # Read the audio file
        audio, sr = sf.read(result_path)
        
        # Resample if needed
        if sr != self.sample_rate:
            from scipy import signal
            audio = signal.resample(audio, int(len(audio) * self.sample_rate / sr))
        
        return audio.astype(np.float32)
    
    async def _generate_with_openai(self, text: str, voice: str = "alloy") -> np.ndarray:
        """
        Generate audio using OpenAI TTS API.
        Requires OPENAI_API_KEY environment variable.
        Raises exceptions on failure (no fallbacks).
        """
        import httpx
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": voice,
                    "response_format": "mp3",
                },
                timeout=60.0,
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI TTS API error (status {response.status_code}): {response.text}")
            
            return await self._mp3_bytes_to_numpy(response.content)
    
    async def _generate_with_piper(self, text: str, voice_path: Optional[str] = None) -> np.ndarray:
        """
        Generate audio using Piper TTS (open source, fast).
        Raises exceptions on failure (no fallbacks).
        """
        import subprocess
        import shutil
        
        if not shutil.which("piper"):
            raise RuntimeError("Piper TTS is not installed. Please install it to use this engine.")
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name
        
        cmd = ["piper", "--output_file", output_path]
        if voice_path:
            cmd.extend(["--model", voice_path])
        
        try:
            process = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Piper TTS generation failed: {process.stderr}")
            
            import soundfile as sf
            audio, sr = sf.read(output_path)
            
            if sr != self.sample_rate:
                from scipy import signal
                audio = signal.resample(audio, int(len(audio) * self.sample_rate / sr))
            
            return audio.astype(np.float32)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    async def _generate_with_styletts2(
        self, 
        text: str, 
        voice_path: Optional[str],
        emotion: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 0.0
    ) -> np.ndarray:
        """
        Generate audio using StyleTTS2 HuggingFace Space (CherithCutestory/styletts2).
        Supports voice cloning, emotion control, and native speed/pitch adjustment.
        """
        from gradio_client import Client, handle_file
        import httpx
        import soundfile as sf
        
        if not voice_path:
            raise ValueError("StyleTTS2 requires a voice sample for cloning")
        
        # StyleTTS2 supported emotions
        styletts2_emotions = ["neutral", "happy", "sad", "angry", "fear", "excited"]
        
        # Map standard/app emotions to StyleTTS2 emotions
        # App sentiment labels: joy, sadness, anger, fear, surprise, disgust, neutral,
        # anxious, hopeful, melancholy, fearful, surprised, disgusted
        emotion_map = {
            # Standard emotions
            "neutral": "neutral",
            "happy": "happy",
            "sad": "sad",
            "angry": "angry",
            "fear": "fear",
            "surprise": "excited",
            "disgust": "angry",
            "excited": "excited",
            "calm": "neutral",
            "confused": "neutral",
            # App-specific sentiment labels
            "joy": "happy",
            "sadness": "sad",
            "anger": "angry",
            "fearful": "fear",
            "surprised": "excited",
            "disgusted": "angry",
            "anxious": "fear",
            "hopeful": "happy",
            "melancholy": "sad",
        }
        
        mapped_emotion = emotion_map.get(emotion.lower() if emotion else "neutral", "neutral")
        
        # Try to load voice transcript
        voice_text = ""
        if voice_path:
            txt_path = voice_path.rsplit(".", 1)[0] + ".txt"
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r") as f:
                        voice_text = f.read().strip()
                    logger.info(f"Loaded voice transcript for StyleTTS2: {voice_text[:50]}...")
                except Exception as e:
                    logger.warning(f"Failed to load transcript: {e}")
        
        space_url = "CherithCutestory/styletts2"
        timeout_secs = 300
        
        logger.info(f"StyleTTS2 generating with emotion: {mapped_emotion}, speed: {speed}, pitch: {pitch}")
        
        loop = asyncio.get_running_loop()
        
        def call_gradio():
            httpx_kwargs = {
                "timeout": httpx.Timeout(timeout_secs, connect=60.0)
            }
            
            client = Client(space_url, httpx_kwargs=httpx_kwargs)
            
            result = client.predict(
                text=text,
                voice_wav=handle_file(voice_path),
                voice_text=voice_text,
                emotion=mapped_emotion,
                speed=speed,
                pitch=pitch,
                seed=42,
                api_name="/tts"
            )
            return result
        
        result = await loop.run_in_executor(None, call_gradio)
        
        # Result is audio file path
        audio_path = result
        audio, sr = sf.read(audio_path)
        
        if sr != self.sample_rate:
            from scipy import signal
            samples = int(len(audio) * self.sample_rate / sr)
            audio = signal.resample(audio, samples)
        
        # StyleTTS2 has native speed/pitch control, no pyrubberband needed
        return audio.astype(np.float32)
    
    async def _generate_with_soprano(self, text: str) -> np.ndarray:
        """
        Generate audio using Soprano TTS (ekwek/Soprano-1.1-80M).
        Ultra-fast local model: 2000x real-time on GPU, 20x on CPU.
        Raises exceptions on failure (no fallbacks).
        """
        from soprano import SopranoTTS
        import torch
        
        loop = asyncio.get_running_loop()
        
        def generate_sync():
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            logger.info(f"Soprano TTS using device: {device}")
            
            model = SopranoTTS(
                backend='auto',
                device=device,
                cache_size_mb=100,
            )
            
            audio = model.infer(text)
            
            if isinstance(audio, torch.Tensor):
                audio = audio.cpu().numpy()
            
            if len(audio.shape) > 1:
                audio = audio.squeeze()
            
            return audio
        
        audio = await loop.run_in_executor(None, generate_sync)
        
        soprano_sr = 32000
        if soprano_sr != self.sample_rate:
            from scipy import signal
            audio = signal.resample(audio, int(len(audio) * self.sample_rate / soprano_sr))
        
        logger.info(f"Soprano TTS generated {len(audio)/self.sample_rate:.2f}s of audio")
        return audio.astype(np.float32)
    
    async def _generate_with_edge_tts(self, text: str, voice: str = "en-US-AriaNeural") -> np.ndarray:
        """
        Generate audio using edge-tts (Microsoft Azure Neural TTS).
        Raises exceptions on failure (no fallbacks).
        """
        communicate = edge_tts.Communicate(text, voice)
        
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        if not audio_data:
            raise RuntimeError(f"edge-tts returned empty audio for voice '{voice}'")
        
        audio_array = await self._mp3_bytes_to_numpy(audio_data)
        return audio_array
    
    async def _mp3_bytes_to_numpy(self, mp3_data: bytes) -> np.ndarray:
        """
        Convert MP3 bytes to numpy array at target sample rate.
        """
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            audio = audio.set_frame_rate(self.sample_rate).set_channels(1)
            
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0
            
            return samples
        except ImportError:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(mp3_data)
                temp_path = f.name
            
            try:
                import subprocess
                wav_path = temp_path.replace(".mp3", ".wav")
                subprocess.run([
                    "ffmpeg", "-y", "-i", temp_path,
                    "-ar", str(self.sample_rate), "-ac", "1",
                    wav_path
                ], capture_output=True, check=True)
                
                import soundfile as sf
                audio, sr = sf.read(wav_path)
                os.unlink(wav_path)
                return audio.astype(np.float32)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
    
    def _synthesize_fallback(self, text: str) -> np.ndarray:
        """
        Simple sine wave fallback if all TTS fails.
        """
        words = text.split()
        duration = max(0.5, min(30.0, len(words) * 0.2))
        num_samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, num_samples)
        audio = 0.3 * np.sin(2 * np.pi * 200 * t).astype(np.float32)
        return audio


async def list_edge_voices():
    """List all available edge-tts voices."""
    if not EDGE_TTS_AVAILABLE:
        return []
    
    voices = await edge_tts.list_voices()
    return [
        {
            "id": v["ShortName"],
            "name": v["FriendlyName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
        }
        for v in voices
        if v["Locale"].startswith("en-")
    ]
