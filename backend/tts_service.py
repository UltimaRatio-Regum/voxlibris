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
            
            if segment.type == "dialogue" and segment.speaker:
                speaker_config = config.speakers.get(segment.speaker)
                if speaker_config:
                    voice_id = speaker_config.voiceSampleId
                    pitch_offset = speaker_config.pitchOffset
                    speed_factor = speaker_config.speedFactor
                    if voice_id and voice_id.startswith("edge_"):
                        edge_voice = EDGE_TTS_VOICES.get(voice_id.replace("edge_", ""), self.edge_voice)
            else:
                voice_id = config.narratorVoiceId
                if voice_id and voice_id.startswith("edge_"):
                    edge_voice = EDGE_TTS_VOICES.get(voice_id.replace("edge_", ""), EDGE_TTS_VOICES["narrator"])
            
            voice_path = voice_files.get(voice_id) if voice_id and not voice_id.startswith("edge_") else None
            
            audio = await self._generate_segment_audio_async(
                text=segment.text,
                voice_path=voice_path,
                edge_voice=edge_voice,
                exaggeration=config.defaultExaggeration,
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
        edge_voice: str = "en-US-AriaNeural",
        exaggeration: float = 0.5,
    ) -> np.ndarray:
        """
        Generate audio for a single text segment.
        Uses Chatterbox if available with GPU, otherwise edge-tts.
        """
        if self.model is not None and voice_path:
            try:
                wav = self.model.generate(
                    text,
                    audio_prompt_path=voice_path,
                    exaggeration=exaggeration,
                )
                return wav.numpy().flatten()
            except Exception as e:
                logger.warning(f"Chatterbox generation failed: {e}, using edge-tts")
        
        if EDGE_TTS_AVAILABLE:
            return await self._generate_with_edge_tts(text, edge_voice)
        
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
