"""
Audio Processor - Handles pitch shifting, speed changes, and audio manipulation
"""

import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional

try:
    import pyrubberband as pyrb
    PYRUBBERBAND_AVAILABLE = True
except ImportError:
    PYRUBBERBAND_AVAILABLE = False


class AudioProcessor:
    """
    Processes audio files with pitch and speed adjustments
    based on emotion analysis using pyrubberband.
    """
    
    # Fixed set of emotions with +/-1% adjustments for pitch (semitones) and speed
    # Emotion adjustments are subtle to maintain natural speech quality
    # 
    # | Emotion    | Pitch (semitones) | Speed (factor) | Description                    |
    # |------------|-------------------|----------------|--------------------------------|
    # | neutral    |  0.00             | 1.00           | No adjustment                  |
    # | happy      | +0.12             | 1.01           | Slightly higher, slightly faster|
    # | sad        | -0.12             | 0.99           | Slightly lower, slightly slower |
    # | angry      | +0.12             | 1.01           | Slightly higher, slightly faster|
    # | fearful    | +0.12             | 1.01           | Slightly higher, slightly faster|
    # | surprised  | +0.12             | 1.01           | Slightly higher, slightly faster|
    # | disgusted  | -0.12             | 0.99           | Slightly lower, slightly slower |
    # | excited    | +0.12             | 1.01           | Slightly higher, slightly faster|
    # | calm       |  0.00             | 0.99           | Normal pitch, slightly slower   |
    # | anxious    | +0.06             | 1.01           | Slightly higher, slightly faster|
    # | hopeful    | +0.06             | 1.00           | Slightly higher, normal speed   |
    # | melancholy | -0.06             | 0.99           | Slightly lower, slightly slower |
    # 
    # Note: +0.12 semitones ≈ 1% pitch increase, 1.01 = 1% speed increase
    
    EMOTION_PITCH_MAP = {
        "neutral": 0.0,
        "happy": 0.12,
        "sad": -0.12,
        "angry": 0.12,
        "fearful": 0.12,
        "surprised": 0.12,
        "disgusted": -0.12,
        "excited": 0.12,
        "calm": 0.0,
        "anxious": 0.06,
        "hopeful": 0.06,
        "melancholy": -0.06,
    }
    
    EMOTION_SPEED_MAP = {
        "neutral": 1.00,
        "happy": 1.01,
        "sad": 0.99,
        "angry": 1.01,
        "fearful": 1.01,
        "surprised": 1.01,
        "disgusted": 0.99,
        "excited": 1.01,
        "calm": 0.99,
        "anxious": 1.01,
        "hopeful": 1.00,
        "melancholy": 0.99,
    }
    
    # Volume adjustments per emotion (1.0 = no change, 1.1 = 10% louder, 0.95 = 5% quieter)
    # Volume is applied as a simple amplitude multiplier
    EMOTION_VOLUME_MAP = {
        "neutral": 1.00,
        "happy": 1.05,
        "sad": 0.95,
        "angry": 1.10,
        "fearful": 0.95,
        "surprised": 1.08,
        "disgusted": 1.02,
        "excited": 1.10,
        "calm": 0.95,
        "anxious": 1.03,
        "hopeful": 1.02,
        "melancholy": 0.93,
    }
    
    # Intensity/exaggeration for Chatterbox TTS (0.0 to 1.0 scale)
    # Higher values = more emotional expression in the voice
    EMOTION_INTENSITY_MAP = {
        "neutral": 0.3,
        "happy": 0.6,
        "sad": 0.5,
        "angry": 0.7,
        "fearful": 0.6,
        "surprised": 0.7,
        "disgusted": 0.5,
        "excited": 0.8,
        "calm": 0.2,
        "anxious": 0.6,
        "hopeful": 0.5,
        "melancholy": 0.4,
    }
    
    # Valid emotions that the LLM should use
    VALID_EMOTIONS = list(EMOTION_PITCH_MAP.keys())
    
    def get_audio_duration(self, file_path: str) -> float:
        """Get the duration of an audio file in seconds."""
        try:
            info = sf.info(file_path)
            return info.duration
        except Exception:
            return 0.0
    
    def load_audio(self, file_path: str) -> tuple[np.ndarray, int]:
        """Load audio file and return (data, sample_rate)."""
        data, sr = sf.read(file_path)
        return data, sr
    
    def save_audio(self, file_path: str, data: np.ndarray, sample_rate: int):
        """Save audio data to file."""
        sf.write(file_path, data, sample_rate)
    
    def apply_emotion_prosody(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        emotion_label: str,
        emotion_score: float = 1.0,
        base_pitch_offset: float = 0,
        base_speed_factor: float = 1.0,
        base_volume_factor: float = 1.0,
    ) -> np.ndarray:
        """
        Apply pitch, speed, and volume changes based on emotion.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            emotion_label: Detected emotion (happy, sad, angry, etc.)
            emotion_score: Confidence of emotion (0-1), used to scale the effect
            base_pitch_offset: Additional pitch offset in semitones
            base_speed_factor: Additional speed multiplier
            base_volume_factor: Additional volume multiplier
            
        Returns:
            Processed audio data
        """
        if not PYRUBBERBAND_AVAILABLE:
            return audio_data
        
        emotion_label = emotion_label.lower() if emotion_label else "neutral"
        
        pitch_offset = self.EMOTION_PITCH_MAP.get(emotion_label, 0) * emotion_score
        pitch_offset += base_pitch_offset
        
        speed_factor = self.EMOTION_SPEED_MAP.get(emotion_label, 1.0)
        speed_factor = 1.0 + (speed_factor - 1.0) * emotion_score
        speed_factor *= base_speed_factor
        
        volume_factor = self.EMOTION_VOLUME_MAP.get(emotion_label, 1.0)
        volume_factor = 1.0 + (volume_factor - 1.0) * emotion_score
        volume_factor *= base_volume_factor
        
        speed_factor = max(0.5, min(2.0, speed_factor))
        pitch_offset = max(-12, min(12, pitch_offset))
        volume_factor = max(0.3, min(2.0, volume_factor))
        
        processed = audio_data
        
        if abs(speed_factor - 1.0) > 0.001:
            processed = pyrb.time_stretch(processed, sample_rate, speed_factor)
        
        if abs(pitch_offset) > 0.01:
            processed = pyrb.pitch_shift(processed, sample_rate, pitch_offset)
        
        if abs(volume_factor - 1.0) > 0.001:
            processed = processed * volume_factor
            processed = np.clip(processed, -1.0, 1.0)
        
        return processed
    
    def apply_sentiment_prosody(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        sentiment_label: str,
        sentiment_score: float = 0.5,
        base_pitch_offset: float = 0,
        base_speed_factor: float = 1.0,
        base_volume_factor: float = 1.0,
    ) -> np.ndarray:
        """
        Legacy method - redirects to apply_emotion_prosody for backwards compatibility.
        """
        return self.apply_emotion_prosody(
            audio_data, sample_rate, sentiment_label, sentiment_score,
            base_pitch_offset, base_speed_factor, base_volume_factor
        )
    
    def apply_pitch_shift(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        semitones: float,
    ) -> np.ndarray:
        """Apply pitch shift in semitones."""
        if not PYRUBBERBAND_AVAILABLE or abs(semitones) < 0.1:
            return audio_data
        return pyrb.pitch_shift(audio_data, sample_rate, semitones)
    
    def apply_time_stretch(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        factor: float,
    ) -> np.ndarray:
        """Apply time stretch (speed change without pitch change)."""
        if not PYRUBBERBAND_AVAILABLE or abs(factor - 1.0) < 0.01:
            return audio_data
        factor = max(0.5, min(2.0, factor))
        return pyrb.time_stretch(audio_data, sample_rate, factor)
    
    def concatenate_audio(
        self,
        audio_chunks: list[np.ndarray],
        sample_rate: int,
        pause_duration_ms: int = 500,
    ) -> np.ndarray:
        """
        Concatenate audio chunks with pauses between them.
        
        Args:
            audio_chunks: List of audio data arrays
            sample_rate: Sample rate in Hz
            pause_duration_ms: Pause between chunks in milliseconds
        """
        if not audio_chunks:
            return np.array([], dtype=np.float32)
        
        pause_samples = int(sample_rate * pause_duration_ms / 1000)
        pause = np.zeros(pause_samples, dtype=np.float32)
        
        result_parts = []
        for i, chunk in enumerate(audio_chunks):
            if len(chunk.shape) > 1:
                chunk = np.mean(chunk, axis=1)
            
            result_parts.append(chunk.astype(np.float32))
            
            if i < len(audio_chunks) - 1:
                result_parts.append(pause)
        
        return np.concatenate(result_parts)
    
    def normalize_audio(
        self,
        audio_data: np.ndarray,
        target_db: float = -3.0,
    ) -> np.ndarray:
        """Normalize audio to target dB level."""
        if len(audio_data) == 0:
            return audio_data
        
        peak = np.max(np.abs(audio_data))
        if peak < 1e-10:
            return audio_data
        
        target_amplitude = 10 ** (target_db / 20)
        normalized = audio_data * (target_amplitude / peak)
        
        return normalized
    
    def create_silence(self, sample_rate: int, duration_ms: int) -> np.ndarray:
        """Create silence of specified duration."""
        num_samples = int(sample_rate * duration_ms / 1000)
        return np.zeros(num_samples, dtype=np.float32)
    
    def trim_silence_edges(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_ms: int = 50,
        silence_threshold: float = 0.01,
    ) -> np.ndarray:
        """
        Trim silence from the beginning and end of audio.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            block_ms: Block size in milliseconds for analysis
            silence_threshold: Max RMS amplitude to consider as silence
        
        Returns:
            Audio data with leading and trailing silence removed
        """
        if len(audio_data) == 0:
            return audio_data
        
        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        block_samples = int(sample_rate * block_ms / 1000)
        total_blocks = len(audio_data) // block_samples
        
        if total_blocks == 0:
            return audio_data.astype(np.float32)
        
        # Find first non-silent block (from start)
        first_sound_block = 0
        for i in range(total_blocks):
            start_idx = i * block_samples
            end_idx = min(start_idx + block_samples, len(audio_data))
            block = audio_data[start_idx:end_idx]
            rms = np.sqrt(np.mean(block ** 2))
            if rms >= silence_threshold:
                first_sound_block = i
                break
        else:
            # All silence
            return np.array([], dtype=np.float32)
        
        # Find last non-silent block (from end)
        last_sound_block = total_blocks - 1
        for i in range(total_blocks - 1, -1, -1):
            start_idx = i * block_samples
            end_idx = min(start_idx + block_samples, len(audio_data))
            block = audio_data[start_idx:end_idx]
            rms = np.sqrt(np.mean(block ** 2))
            if rms >= silence_threshold:
                last_sound_block = i
                break
        
        # Extract the audio between first and last sound blocks
        start_sample = first_sound_block * block_samples
        end_sample = min((last_sound_block + 1) * block_samples, len(audio_data))
        
        return audio_data[start_sample:end_sample].astype(np.float32)
    
    def truncate_at_long_silence(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_ms: int = 50,
        silence_threshold: float = 0.01,
        long_silence_ms: int = 2000,
    ) -> np.ndarray:
        """
        Scan for 2+ seconds of contiguous silence and truncate everything after.
        
        This catches TTS model hallucinations that sometimes appear after
        a long pause. If we find 2+ seconds of silence followed by more audio,
        we truncate at the start of that silence.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            block_ms: Block size in milliseconds for analysis
            silence_threshold: Max RMS amplitude to consider as silence
            long_silence_ms: Duration of silence that triggers truncation (default 2000ms)
        
        Returns:
            Audio data truncated at first occurrence of long silence
        """
        if len(audio_data) == 0:
            return audio_data
        
        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        block_samples = int(sample_rate * block_ms / 1000)
        long_silence_blocks = max(1, int(long_silence_ms / block_ms))
        total_blocks = len(audio_data) // block_samples
        
        if total_blocks == 0:
            return audio_data.astype(np.float32)
        
        # Calculate RMS for each block
        block_rms = []
        for i in range(total_blocks):
            start_idx = i * block_samples
            end_idx = min(start_idx + block_samples, len(audio_data))
            block = audio_data[start_idx:end_idx]
            rms = np.sqrt(np.mean(block ** 2))
            block_rms.append(rms)
        
        # Scan for contiguous silence of 2+ seconds
        consecutive_silence = 0
        silence_start_block = None
        
        for i, rms in enumerate(block_rms):
            is_silence = rms < silence_threshold
            
            if is_silence:
                if consecutive_silence == 0:
                    silence_start_block = i
                consecutive_silence += 1
                
                # Found long silence - truncate at start of this silence
                if consecutive_silence >= long_silence_blocks and silence_start_block is not None:
                    trim_point = silence_start_block * block_samples
                    return audio_data[:trim_point].astype(np.float32)
            else:
                # Reset silence counter
                consecutive_silence = 0
                silence_start_block = None
        
        # No long silence found, return original
        return audio_data.astype(np.float32)
    
    def aggressive_silence_trim(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_ms: int = 50,
        silence_threshold: float = 0.01,
        long_silence_ms: int = 2000,
    ) -> np.ndarray:
        """
        Aggressively trim silence from audio in two passes:
        
        1. First, scan for 2+ seconds of contiguous silence and truncate
           everything after that point (catches model hallucinations)
        2. Then trim any remaining silence from beginning and end
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            block_ms: Block size in milliseconds for analysis (default 50ms)
            silence_threshold: Max RMS amplitude to consider as silence (default 0.01)
            long_silence_ms: Duration of silence that triggers truncation (default 2000ms)
        
        Returns:
            Audio data with aggressive silence removal applied
        """
        if len(audio_data) == 0:
            return audio_data
        
        # Pass 1: Truncate at first occurrence of 2+ second silence
        audio_data = self.truncate_at_long_silence(
            audio_data, sample_rate, block_ms, silence_threshold, long_silence_ms
        )
        
        # Pass 2: Trim remaining silence from edges
        audio_data = self.trim_silence_edges(
            audio_data, sample_rate, block_ms, silence_threshold
        )
        
        return audio_data
    
    def trim_trailing_silence(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_ms: int = 50,
        silence_threshold: float = 0.01,
        min_silence_duration_ms: int = 500,
    ) -> np.ndarray:
        """
        Legacy method - now redirects to aggressive_silence_trim for better results.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            block_ms: Block size in milliseconds for analysis (default 50ms)
            silence_threshold: Max RMS amplitude to consider as silence (default 0.01)
            min_silence_duration_ms: Ignored - uses 2000ms for long silence detection
        
        Returns:
            Audio data with aggressive silence removal applied
        """
        return self.aggressive_silence_trim(
            audio_data, sample_rate, block_ms, silence_threshold, long_silence_ms=2000
        )
