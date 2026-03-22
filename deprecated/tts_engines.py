"""
TTS Engine Base Class Architecture

Provides a unified interface for all TTS engines with common parameters:
- text: the text to convert to speech
- voice_wav: voice sample file path for cloning
- voice_text: transcript of the voice sample
- voice_id: voice ID for non-cloning models
- speed: speed adjustment (1.0 = normal)
- pitch: pitch adjustment (0.0 = normal)
- emotion: standardized emotion name from parser
"""

import os
import asyncio
import tempfile
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

# Standard emotion names used across the application
STANDARD_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear", "surprise", 
    "disgust", "excited", "calm", "confused"
]

# StyleTTS2 supported emotions
STYLETTS2_EMOTIONS = ["neutral", "happy", "sad", "angry", "fear", "excited"]

# Emotion mapping from standard emotions to StyleTTS2 emotions
# Covers both standard emotions and app-specific sentiment labels
STYLETTS2_EMOTION_MAP = {
    # Standard emotions
    "neutral": "neutral",
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "fear": "fear",
    "surprise": "excited",  # Map surprise to excited
    "disgust": "angry",     # Map disgust to angry
    "excited": "excited",
    "calm": "neutral",      # Map calm to neutral
    "confused": "neutral",  # Map confused to neutral
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


@dataclass
class TTSParams:
    """Common parameters for all TTS engines."""
    text: str
    voice_wav: Optional[str] = None
    voice_text: Optional[str] = None
    voice_id: Optional[str] = None
    speed: float = 1.0
    pitch: float = 0.0
    emotion: Optional[str] = None
    exaggeration: float = 0.5  # For Chatterbox-style emotion intensity
    extra: Optional[Dict[str, Any]] = None  # Engine-specific extras


class BaseTTSEngine(ABC):
    """Abstract base class for all TTS engines."""
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None):
        self.sample_rate = sample_rate
        self.audio_processor = audio_processor
    
    @property
    def name(self) -> str:
        """Return engine name for logging."""
        return self.__class__.__name__
    
    @abstractmethod
    async def generate(self, params: TTSParams) -> np.ndarray:
        """Generate audio from text using engine-specific logic.
        
        Args:
            params: TTSParams containing all generation parameters
            
        Returns:
            numpy array of audio samples
        """
        pass
    
    def supports_native_speed_pitch(self) -> bool:
        """Whether engine has built-in speed/pitch controls.
        
        If False, caller should apply pyrubberband post-processing.
        """
        return False
    
    def supports_voice_cloning(self) -> bool:
        """Whether engine supports voice cloning from samples."""
        return False
    
    def map_emotion(self, emotion: Optional[str]) -> Optional[str]:
        """Map standard emotion to engine-specific emotion.
        
        Override in subclasses for engines with emotion support.
        """
        return emotion
    
    def _apply_prosody(self, audio: np.ndarray, speed: float, pitch: float) -> np.ndarray:
        """Apply speed/pitch adjustments using pyrubberband.
        
        Only called if supports_native_speed_pitch() returns False.
        """
        if self.audio_processor and (speed != 1.0 or pitch != 0.0):
            return self.audio_processor.apply_prosody(
                audio, self.sample_rate, speed, pitch
            )
        return audio


class EdgeTTSEngine(BaseTTSEngine):
    """Microsoft Edge TTS engine - high quality neural TTS."""
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None):
        super().__init__(sample_rate, audio_processor)
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        import edge_tts
        import soundfile as sf
        
        voice = params.voice_id or "en-US-AriaNeural"
        
        logger.info(f"EdgeTTS generating with voice: {voice}")
        
        communicate = edge_tts.Communicate(params.text, voice)
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            await communicate.save(tmp_path)
            
            # Convert to numpy array
            audio, sr = sf.read(tmp_path)
            
            # Resample if needed
            if sr != self.sample_rate:
                from scipy import signal
                samples = int(len(audio) * self.sample_rate / sr)
                audio = signal.resample(audio, samples)
            
            # Apply prosody if needed
            if params.speed != 1.0 or params.pitch != 0.0:
                audio = self._apply_prosody(audio, params.speed, params.pitch)
            
            return audio.astype(np.float32)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class OpenAITTSEngine(BaseTTSEngine):
    """OpenAI TTS engine."""
    
    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None, api_key: str = None):
        super().__init__(sample_rate, audio_processor)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        from openai import OpenAI
        import soundfile as sf
        
        voice = params.voice_id if params.voice_id in self.VOICES else "alloy"
        
        logger.info(f"OpenAI TTS generating with voice: {voice}")
        
        client = OpenAI(api_key=self.api_key)
        
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=params.text,
            response_format="mp3"
        )
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            response.stream_to_file(tmp_path)
        
        try:
            audio, sr = sf.read(tmp_path)
            
            if sr != self.sample_rate:
                from scipy import signal
                samples = int(len(audio) * self.sample_rate / sr)
                audio = signal.resample(audio, samples)
            
            if params.speed != 1.0 or params.pitch != 0.0:
                audio = self._apply_prosody(audio, params.speed, params.pitch)
            
            return audio.astype(np.float32)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class ChatterboxFreeEngine(BaseTTSEngine):
    """Chatterbox Free TTS engine using HuggingFace Spaces."""
    
    SPACE_URL = "mrfakename/Chatterbox-TTS"
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None, timeout: int = 300):
        super().__init__(sample_rate, audio_processor)
        self.timeout = timeout
    
    def supports_voice_cloning(self) -> bool:
        return True
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        from gradio_client import Client, handle_file
        import httpx
        import soundfile as sf
        
        if not params.voice_wav:
            raise ValueError("Chatterbox Free requires a voice sample (voice_wav)")
        
        exaggeration = params.exaggeration
        
        logger.info(f"Chatterbox Free generating with exaggeration: {exaggeration}")
        
        loop = asyncio.get_running_loop()
        
        def call_gradio():
            client_kwargs = {
                "httpx_kwargs": {
                    "timeout": httpx.Timeout(self.timeout, connect=60.0)
                }
            }
            client = Client(self.SPACE_URL, **client_kwargs)
            
            result = client.predict(
                params.text,
                handle_file(params.voice_wav),
                exaggeration,
                0.5,  # CFG weight
                0.5,  # Temperature
                api_name="/generate"
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
        
        if params.speed != 1.0 or params.pitch != 0.0:
            audio = self._apply_prosody(audio, params.speed, params.pitch)
        
        return audio.astype(np.float32)


class HFTTSPaidEngine(BaseTTSEngine):
    """HuggingFace TTS Paid engine - multi-model support (Qwen3, Chatterbox, XTTS, StyleTTS2)."""
    
    def __init__(
        self, 
        sample_rate: int = 24000, 
        audio_processor=None,
        space_url: str = None,
        api_key: str = None,
        model: str = "qwen3",
        language: str = "en",
        timeout: int = 600,
        tts_settings: dict = None
    ):
        super().__init__(sample_rate, audio_processor)
        self.space_url = space_url
        self.api_key = api_key
        self.model = model
        self.language = language
        self.timeout = timeout
        self.tts_settings = tts_settings or {}
    
    def supports_voice_cloning(self) -> bool:
        return True
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        from gradio_client import Client, handle_file
        import httpx
        import soundfile as sf
        
        if not params.voice_wav:
            raise ValueError("HF TTS Paid requires a voice sample (voice_wav)")
        
        if not self.space_url:
            raise ValueError("HF TTS Paid requires space_url configuration")
        
        model = self.model
        
        # Get StyleTTS2 parameters from settings
        st_alpha = self.tts_settings.get("styletts2_alpha", 0.3)
        st_beta = self.tts_settings.get("styletts2_beta", 0.7)
        st_diffusion_steps = self.tts_settings.get("styletts2_diffusion_steps", 5)
        st_embedding_scale = self.tts_settings.get("styletts2_embedding_scale", 1.0)
        
        # Qwen3 settings
        qwen_model_id = self.tts_settings.get("qwen_model_id", "Qwen/Qwen3-TTS-0.6B-BF16")
        qwen_x_vector_only_mode = False
        
        ref_text = params.voice_text or ""
        
        # For Qwen3, enable x_vector_only_mode if no transcript
        if model == "qwen3" and not ref_text:
            qwen_x_vector_only_mode = True
        
        logger.info(f"HF TTS Paid generating with model: {model}")
        
        loop = asyncio.get_running_loop()
        
        def call_gradio():
            httpx_kwargs = {
                "timeout": httpx.Timeout(self.timeout, connect=60.0)
            }
            
            if self.api_key:
                httpx_kwargs["headers"] = {
                    "Authorization": f"Bearer {self.api_key}"
                }
            
            client = Client(self.space_url, httpx_kwargs=httpx_kwargs)
            
            result = client.predict(
                params.text,
                model,
                self.language,
                handle_file(params.voice_wav),
                ref_text,
                qwen_x_vector_only_mode,
                qwen_model_id,
                st_alpha,
                st_beta,
                st_diffusion_steps,
                st_embedding_scale,
                api_name="/tts"
            )
            return result
        
        result = await loop.run_in_executor(None, call_gradio)
        
        audio_path = result
        audio, sr = sf.read(audio_path)
        
        if sr != self.sample_rate:
            from scipy import signal
            samples = int(len(audio) * self.sample_rate / sr)
            audio = signal.resample(audio, samples)
        
        if params.speed != 1.0 or params.pitch != 0.0:
            audio = self._apply_prosody(audio, params.speed, params.pitch)
        
        return audio.astype(np.float32)


class StyleTTS2Engine(BaseTTSEngine):
    """StyleTTS2 TTS engine - expressive voice synthesis with emotion control."""
    
    SPACE_URL = "CherithCutestory/styletts2"
    SUPPORTED_EMOTIONS = ["neutral", "happy", "sad", "angry", "fear", "excited"]
    
    def __init__(
        self, 
        sample_rate: int = 24000, 
        audio_processor=None,
        timeout: int = 300,
        seed: int = 42
    ):
        super().__init__(sample_rate, audio_processor)
        self.timeout = timeout
        self.seed = seed
    
    def supports_voice_cloning(self) -> bool:
        return True
    
    def supports_native_speed_pitch(self) -> bool:
        """StyleTTS2 has built-in speed/pitch controls."""
        return True
    
    def map_emotion(self, emotion: Optional[str]) -> str:
        """Map standard emotion to StyleTTS2 emotion."""
        if not emotion:
            return "neutral"
        
        emotion_lower = emotion.lower()
        return STYLETTS2_EMOTION_MAP.get(emotion_lower, "neutral")
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        from gradio_client import Client, handle_file
        import httpx
        import soundfile as sf
        
        if not params.voice_wav:
            raise ValueError("StyleTTS2 requires a voice sample (voice_wav)")
        
        # Map emotion to StyleTTS2 format
        emotion = self.map_emotion(params.emotion)
        
        # StyleTTS2 uses native speed/pitch
        speed = params.speed
        pitch = params.pitch
        
        voice_text = params.voice_text or ""
        
        logger.info(f"StyleTTS2 generating with emotion: {emotion}, speed: {speed}, pitch: {pitch}")
        
        loop = asyncio.get_running_loop()
        
        def call_gradio():
            httpx_kwargs = {
                "timeout": httpx.Timeout(self.timeout, connect=60.0)
            }
            
            client = Client(self.SPACE_URL, httpx_kwargs=httpx_kwargs)
            
            result = client.predict(
                text=params.text,
                voice_wav=handle_file(params.voice_wav),
                voice_text=voice_text,
                emotion=emotion,
                speed=speed,
                pitch=pitch,
                seed=self.seed,
                api_name="/tts"
            )
            return result
        
        result = await loop.run_in_executor(None, call_gradio)
        
        audio_path = result
        audio, sr = sf.read(audio_path)
        
        if sr != self.sample_rate:
            from scipy import signal
            samples = int(len(audio) * self.sample_rate / sr)
            audio = signal.resample(audio, samples)
        
        # No need for pyrubberband - StyleTTS2 handles speed/pitch natively
        return audio.astype(np.float32)


class PiperTTSEngine(BaseTTSEngine):
    """Piper TTS engine - fast local synthesis."""
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None, model_path: str = None):
        super().__init__(sample_rate, audio_processor)
        self.model_path = model_path
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        import subprocess
        import soundfile as sf
        
        voice = params.voice_id or "en_US-lessac-medium"
        
        logger.info(f"Piper TTS generating with voice: {voice}")
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            cmd = ["piper", "--model", voice, "--output_file", tmp_path]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate(input=params.text.encode())
            
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                raise RuntimeError("Piper failed to generate audio")
            
            audio, sr = sf.read(tmp_path)
            
            if sr != self.sample_rate:
                from scipy import signal
                samples = int(len(audio) * self.sample_rate / sr)
                audio = signal.resample(audio, samples)
            
            if params.speed != 1.0 or params.pitch != 0.0:
                audio = self._apply_prosody(audio, params.speed, params.pitch)
            
            return audio.astype(np.float32)
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class SopranoTTSEngine(BaseTTSEngine):
    """Soprano TTS engine - ultra-fast local synthesis."""
    
    MODEL_ID = "ekwek/Soprano-1.1-80M"
    
    def __init__(self, sample_rate: int = 24000, audio_processor=None):
        super().__init__(sample_rate, audio_processor)
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        if self._model is None:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            logger.info(f"Loading Soprano model: {self.MODEL_ID}")
            self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
            self._model = AutoModelForCausalLM.from_pretrained(self.MODEL_ID)
    
    async def generate(self, params: TTSParams) -> np.ndarray:
        loop = asyncio.get_running_loop()
        
        def run_inference():
            self._load_model()
            
            inputs = self._tokenizer(params.text, return_tensors="pt")
            outputs = self._model.generate(**inputs, max_new_tokens=4096)
            
            # Extract audio tokens and convert to waveform
            audio_tokens = outputs[0]
            # This is simplified - actual Soprano needs codec decoding
            # For now, return placeholder
            logger.warning("Soprano TTS codec decoding not fully implemented")
            return np.zeros(self.sample_rate, dtype=np.float32)
        
        audio = await loop.run_in_executor(None, run_inference)
        
        if params.speed != 1.0 or params.pitch != 0.0:
            audio = self._apply_prosody(audio, params.speed, params.pitch)
        
        return audio


class EngineFactory:
    """Factory for creating TTS engine instances."""
    
    @staticmethod
    def create(
        engine_name: str,
        audio_processor=None,
        sample_rate: int = 24000,
        **kwargs
    ) -> BaseTTSEngine:
        """Create a TTS engine instance by name.
        
        Args:
            engine_name: Name of the TTS engine (e.g., "edge-tts", "styletts2")
            audio_processor: AudioProcessor for prosody adjustments
            sample_rate: Target sample rate
            **kwargs: Engine-specific configuration
            
        Returns:
            BaseTTSEngine instance
        """
        engine_map = {
            "edge-tts": EdgeTTSEngine,
            "openai": OpenAITTSEngine,
            "chatterbox": ChatterboxFreeEngine,
            "chatterbox-free": ChatterboxFreeEngine,
            "chatterbox-paid": HFTTSPaidEngine,
            "hf-tts-paid": HFTTSPaidEngine,
            "styletts2": StyleTTS2Engine,
            "piper": PiperTTSEngine,
            "soprano": SopranoTTSEngine,
        }
        
        engine_class = engine_map.get(engine_name)
        
        if not engine_class:
            raise ValueError(f"Unknown TTS engine: {engine_name}")
        
        return engine_class(
            sample_rate=sample_rate,
            audio_processor=audio_processor,
            **kwargs
        )
