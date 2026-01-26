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
    ) -> np.ndarray:
        """
        Apply pitch and speed changes based on emotion.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            emotion_label: Detected emotion (happy, sad, angry, etc.)
            emotion_score: Confidence of emotion (0-1), used to scale the effect
            base_pitch_offset: Additional pitch offset in semitones
            base_speed_factor: Additional speed multiplier
            
        Returns:
            Processed audio data
        """
        if not PYRUBBERBAND_AVAILABLE:
            return audio_data
        
        # Normalize emotion label to lowercase
        emotion_label = emotion_label.lower() if emotion_label else "neutral"
        
        # Get emotion-based adjustments (+/-1% as specified)
        pitch_offset = self.EMOTION_PITCH_MAP.get(emotion_label, 0) * emotion_score
        pitch_offset += base_pitch_offset
        
        speed_factor = self.EMOTION_SPEED_MAP.get(emotion_label, 1.0)
        # Scale the speed adjustment by emotion score
        speed_factor = 1.0 + (speed_factor - 1.0) * emotion_score
        speed_factor *= base_speed_factor
        
        # Clamp to safe ranges
        speed_factor = max(0.5, min(2.0, speed_factor))
        pitch_offset = max(-12, min(12, pitch_offset))
        
        processed = audio_data
        
        # Apply speed change using pyrubberband's time_stretch
        # This is PITCH-INVARIANT by default - changes tempo without affecting pitch
        if abs(speed_factor - 1.0) > 0.001:
            processed = pyrb.time_stretch(processed, sample_rate, speed_factor)
        
        # Apply pitch shift using pyrubberband's pitch_shift
        # This is SPEED-INVARIANT - changes pitch without affecting tempo
        if abs(pitch_offset) > 0.01:
            processed = pyrb.pitch_shift(processed, sample_rate, pitch_offset)
        
        return processed
    
    def apply_sentiment_prosody(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        sentiment_label: str,
        sentiment_score: float = 0.5,
        base_pitch_offset: float = 0,
        base_speed_factor: float = 1.0,
    ) -> np.ndarray:
        """
        Legacy method - redirects to apply_emotion_prosody for backwards compatibility.
        """
        return self.apply_emotion_prosody(
            audio_data, sample_rate, sentiment_label, sentiment_score,
            base_pitch_offset, base_speed_factor
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
    
    def trim_trailing_silence(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        block_ms: int = 50,
        silence_threshold: float = 0.01,
        min_silence_duration_ms: int = 500,
    ) -> np.ndarray:
        """
        Trim trailing silence from audio data.
        
        Uses a sliding window to detect contiguous blocks of near-silence
        (low mean and low variance) at the end of the audio.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            block_ms: Block size in milliseconds for analysis (default 50ms)
            silence_threshold: Max RMS amplitude to consider as silence (default 0.01)
            min_silence_duration_ms: Minimum silence duration to trigger trimming (default 500ms)
        
        Returns:
            Audio data with trailing silence removed
        """
        if len(audio_data) == 0:
            return audio_data
        
        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        block_samples = int(sample_rate * block_ms / 1000)
        min_silence_samples = int(sample_rate * min_silence_duration_ms / 1000)
        min_silence_blocks = max(1, min_silence_samples // block_samples)
        
        total_blocks = len(audio_data) // block_samples
        if total_blocks == 0:
            return audio_data
        
        # Analyze blocks from the end
        silence_start_block = None
        consecutive_silence = 0
        
        for i in range(total_blocks - 1, -1, -1):
            start_idx = i * block_samples
            end_idx = min(start_idx + block_samples, len(audio_data))
            block = audio_data[start_idx:end_idx]
            
            # Calculate RMS (root mean square) for the block
            rms = np.sqrt(np.mean(block ** 2))
            
            # Check if this block is silence
            is_silence = rms < silence_threshold
            
            if is_silence:
                consecutive_silence += 1
                silence_start_block = i
            else:
                # Found non-silence, check if we had enough silence after this
                if consecutive_silence >= min_silence_blocks:
                    # Trim from silence_start_block
                    trim_point = silence_start_block * block_samples
                    return audio_data[:trim_point].astype(np.float32)
                else:
                    # Not enough silence, keep everything
                    return audio_data.astype(np.float32)
        
        # If we get here, the entire audio (or most of it) is silence
        # Keep at least some audio if it exists
        if consecutive_silence >= min_silence_blocks and silence_start_block is not None:
            trim_point = silence_start_block * block_samples
            if trim_point > 0:
                return audio_data[:trim_point].astype(np.float32)
        
        return audio_data.astype(np.float32)
