import type { TTSEngine } from "@shared/schema";

export interface TTSEngineConfig {
  id: TTSEngine;
  label: string;
  name: string;
  description: string;
  badge?: string;
  badgeVariant?: "default" | "secondary" | "destructive" | "outline";
  supportsVoiceCloning: boolean;
  requiresApiKey: boolean;
  isLocal: boolean;
}

export const TTS_ENGINES: TTSEngineConfig[] = [
  {
    id: "edge-tts",
    label: "Edge TTS (Recommended)",
    name: "Edge TTS (Azure Neural)",
    description: "47 English neural voices, free, high quality",
    badge: "Recommended",
    badgeVariant: "default",
    supportsVoiceCloning: false,
    requiresApiKey: false,
    isLocal: false,
  },
  {
    id: "soprano",
    label: "Soprano TTS",
    name: "Soprano TTS (80M)",
    description: "Ultra-fast local TTS, 2000x real-time on GPU",
    badge: "Local",
    badgeVariant: "default",
    supportsVoiceCloning: false,
    requiresApiKey: false,
    isLocal: true,
  },
];

export function getTTSEngine(id: TTSEngine): TTSEngineConfig | undefined {
  return TTS_ENGINES.find(e => e.id === id);
}

export function isVoiceCloningEngine(id: TTSEngine): boolean {
  const engine = getTTSEngine(id);
  return engine?.supportsVoiceCloning ?? false;
}

export function getVoiceCloningEngines(): TTSEngineConfig[] {
  return TTS_ENGINES.filter(e => e.supportsVoiceCloning);
}

export function getLocalEngines(): TTSEngineConfig[] {
  return TTS_ENGINES.filter(e => e.isLocal);
}
