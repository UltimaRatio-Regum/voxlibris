"""
Pydantic models for the Narrator AI API
"""

from typing import Optional
from pydantic import BaseModel


class Sentiment(BaseModel):
    label: str
    score: float


class TextSegment(BaseModel):
    id: str
    type: str  # "narration" or "dialogue"
    text: str
    speaker: Optional[str] = None
    sentiment: Optional[Sentiment] = None
    startIndex: int
    endIndex: int
    wordCount: Optional[int] = None
    approxDurationSeconds: Optional[float] = None


class SpeakerConfig(BaseModel):
    name: str
    voiceSampleId: Optional[str] = None
    pitchOffset: float = 0
    speedFactor: float = 1.0


class ProjectConfig(BaseModel):
    narratorVoiceId: Optional[str] = None
    narratorSpeed: float = 1.0
    defaultExaggeration: float = 0.5
    pauseBetweenSegments: int = 500
    speakers: dict[str, SpeakerConfig] = {}
    ttsEngine: str = "edge-tts"  # edge-tts, openai, chatterbox, piper


class VoiceSample(BaseModel):
    id: str
    name: str
    audioUrl: str
    duration: float
    createdAt: str


class ParseTextRequest(BaseModel):
    text: str


class ParseTextResponse(BaseModel):
    segments: list[TextSegment]
    detectedSpeakers: list[str]


class GenerateRequest(BaseModel):
    segments: list[TextSegment]
    config: ProjectConfig


class GenerateResponse(BaseModel):
    audioUrl: str
