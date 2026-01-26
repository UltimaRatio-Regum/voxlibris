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
            
            audio = await self._generate_segment_audio_async(
                text=segment.text,
                voice_path=voice_path,
                edge_voice=edge_voice if config.ttsEngine == "edge-tts" else None,
                openai_voice=openai_voice if config.ttsEngine == "openai" else None,
                exaggeration=config.defaultExaggeration,
                tts_engine=config.ttsEngine,
            )
            
            if segment.sentiment:
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
    ) -> np.ndarray:
        """
        Generate audio for a single text segment.
        Dispatches to the appropriate TTS engine based on config.
        """
        if tts_engine == "chatterbox-free" or tts_engine == "chatterbox":
            # "chatterbox" is legacy, treat as chatterbox-free
            if tts_engine == "chatterbox":
                logger.info("Legacy 'chatterbox' engine mapped to 'chatterbox-free'")
            return await self._generate_with_chatterbox_free(text, voice_path, exaggeration)
        elif tts_engine == "chatterbox-paid":
            return await self._generate_with_chatterbox_paid(text, voice_path, exaggeration)
        elif tts_engine == "openai":
            # Use passed openai_voice, fallback to default if invalid
            voice = OPENAI_TTS_VOICES.get(openai_voice, OPENAI_TTS_VOICES["default"]) if openai_voice else "alloy"
            return await self._generate_with_openai(text, voice)
        elif tts_engine == "piper":
            return await self._generate_with_piper(text, voice_path)
        else:  # edge-tts (default)
            if EDGE_TTS_AVAILABLE:
                return await self._generate_with_edge_tts(text, edge_voice or "en-US-AriaNeural")
            return self._synthesize_fallback(text)
    
    async def _generate_with_chatterbox_free(
        self,
        text: str,
        voice_path: Optional[str] = None,
        exaggeration: float = 0.5,
    ) -> np.ndarray:
        """
        Generate audio using Chatterbox TTS via free HuggingFace Spaces.
        Tries local GPU model first, then falls back to HuggingFace Spaces via Gradio.
        """
        # Try local Chatterbox with CUDA first
        if self.model is not None and voice_path:
            try:
                wav = self.model.generate(
                    text,
                    audio_prompt_path=voice_path,
                    exaggeration=exaggeration,
                )
                return wav.numpy().flatten()
            except Exception as e:
                logger.warning(f"Local Chatterbox generation failed: {e}")
        
        # Fall back to HuggingFace Spaces via Gradio client
        if voice_path:
            try:
                return await self._generate_with_chatterbox_gradio(text, voice_path, exaggeration)
            except Exception as e:
                logger.warning(f"Gradio Chatterbox failed: {e}")
        
        logger.warning("Chatterbox free not available, falling back to edge-tts")
        if EDGE_TTS_AVAILABLE:
            return await self._generate_with_edge_tts(text, EDGE_TTS_VOICES["default"])
        return self._synthesize_fallback(text)
    
    async def _generate_with_chatterbox_paid(
        self,
        text: str,
        voice_path: Optional[str] = None,
        exaggeration: float = 0.5,
    ) -> np.ndarray:
        """
        Generate audio using Chatterbox TTS via paid custom API endpoint.
        Requires CHATTERBOX_API_URL and CHATTERBOX_API_KEY environment variables.
        """
        from .chatterbox_config import CHATTERBOX_PAID_CONFIG, is_paid_chatterbox_configured
        import aiohttp
        import base64
        
        if not is_paid_chatterbox_configured():
            logger.warning("Chatterbox paid API not configured, falling back to free tier")
            return await self._generate_with_chatterbox_free(text, voice_path, exaggeration)
        
        if not voice_path or not os.path.exists(voice_path):
            logger.warning(f"Voice file not found: {voice_path}, falling back to edge-tts")
            if EDGE_TTS_AVAILABLE:
                return await self._generate_with_edge_tts(text, EDGE_TTS_VOICES["default"])
            return self._synthesize_fallback(text)
        
        config = CHATTERBOX_PAID_CONFIG
        
        # Apply character limit if configured
        if config["max_chars"] > 0 and len(text) > config["max_chars"]:
            truncated = text[:config["max_chars"]]
            last_space = truncated.rfind(' ')
            if last_space > config["max_chars"] * 0.6:
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters for Chatterbox paid")
        
        try:
            # Read voice file and encode as base64
            with open(voice_path, 'rb') as f:
                voice_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Prepare request payload
            payload = {
                "text": text,
                "audio_prompt": voice_data,
                "exaggeration": exaggeration,
                "temperature": config["default_temperature"],
                "cfg_weight": config["default_cfg_weight"],
            }
            
            headers = {
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            }
            
            logger.info(f"Calling Chatterbox paid API: {config['api_url']}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config["api_url"],
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=config["timeout"])
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Chatterbox paid API error: {response.status} - {error_text}")
                    
                    # Expect audio data in response (WAV or raw PCM)
                    content_type = response.headers.get("Content-Type", "")
                    
                    if "audio" in content_type or "octet-stream" in content_type:
                        # Binary audio response
                        audio_data = await response.read()
                        import io
                        import soundfile as sf
                        audio, sr = sf.read(io.BytesIO(audio_data))
                        if sr != self.sample_rate:
                            import scipy.signal as signal
                            audio = signal.resample(audio, int(len(audio) * self.sample_rate / sr))
                        return audio.astype(np.float32)
                    else:
                        # JSON response with base64 audio
                        data = await response.json()
                        if "audio" in data:
                            audio_bytes = base64.b64decode(data["audio"])
                            import io
                            import soundfile as sf
                            audio, sr = sf.read(io.BytesIO(audio_bytes))
                            if sr != self.sample_rate:
                                import scipy.signal as signal
                                audio = signal.resample(audio, int(len(audio) * self.sample_rate / sr))
                            return audio.astype(np.float32)
                        else:
                            raise Exception("Unexpected response format from Chatterbox paid API")
        
        except Exception as e:
            logger.error(f"Chatterbox paid API failed: {e}")
            logger.warning("Falling back to Chatterbox free tier")
            return await self._generate_with_chatterbox_free(text, voice_path, exaggeration)
    
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
        
        # Run synchronous Gradio call in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, call_gradio)
        
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
        """
        try:
            import httpx
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not found, using fallback")
                return self._synthesize_fallback(text)
            
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
                    logger.error(f"OpenAI TTS failed: {response.text}")
                    return self._synthesize_fallback(text)
                
                return await self._mp3_bytes_to_numpy(response.content)
        except Exception as e:
            logger.error(f"OpenAI TTS error: {e}")
            return self._synthesize_fallback(text)
    
    async def _generate_with_piper(self, text: str, voice_path: Optional[str] = None) -> np.ndarray:
        """
        Generate audio using Piper TTS (open source, fast).
        Falls back to edge-tts if Piper not installed.
        """
        try:
            import subprocess
            import shutil
            
            if not shutil.which("piper"):
                logger.warning("Piper not installed, falling back to edge-tts")
                if EDGE_TTS_AVAILABLE:
                    return await self._generate_with_edge_tts(text, EDGE_TTS_VOICES["default"])
                return self._synthesize_fallback(text)
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                output_path = f.name
            
            cmd = ["piper", "--output_file", output_path]
            if voice_path:
                cmd.extend(["--model", voice_path])
            
            process = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if process.returncode != 0:
                logger.warning(f"Piper TTS failed: {process.stderr}, falling back to edge-tts")
                if EDGE_TTS_AVAILABLE:
                    return await self._generate_with_edge_tts(text, EDGE_TTS_VOICES["default"])
                return self._synthesize_fallback(text)
            
            import soundfile as sf
            audio, sr = sf.read(output_path)
            os.unlink(output_path)
            
            if sr != self.sample_rate:
                from scipy import signal
                audio = signal.resample(audio, int(len(audio) * self.sample_rate / sr))
            
            return audio.astype(np.float32)
        except Exception as e:
            logger.warning(f"Piper TTS error: {e}, falling back to edge-tts")
            if EDGE_TTS_AVAILABLE:
                return await self._generate_with_edge_tts(text, EDGE_TTS_VOICES["default"])
            return self._synthesize_fallback(text)
    
    async def _generate_with_edge_tts(self, text: str, voice: str = "en-US-AriaNeural") -> np.ndarray:
        """
        Generate audio using edge-tts (Microsoft Azure Neural TTS).
        """
        try:
            communicate = edge_tts.Communicate(text, voice)
            
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if not audio_data:
                logger.warning("edge-tts returned empty audio")
                return self._synthesize_fallback(text)
            
            audio_array = await self._mp3_bytes_to_numpy(audio_data)
            return audio_array
            
        except Exception as e:
            logger.error(f"edge-tts generation failed: {e}")
            return self._synthesize_fallback(text)
    
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
