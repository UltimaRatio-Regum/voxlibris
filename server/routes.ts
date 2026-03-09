import type { Express, Request, Response } from "express";
import { createServer, type Server } from "http";
import { createProxyMiddleware } from "http-proxy-middleware";
import express from "express";
import { parseTextWithLLM, parseTextWithLLMStreaming, getAvailableModels, isOpenRouterConfigured } from "./llm-service";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://127.0.0.1:8000";

async function fallbackToBasicParsing(text: string): Promise<any> {
  const response = await fetch(`${PYTHON_BACKEND_URL}/parse-text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  
  if (!response.ok) {
    throw new Error(`Python backend error: ${response.status}`);
  }
  
  return response.json();
}

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {

  // LLM-powered text parsing endpoint with automatic fallback
  app.post('/api/parse-text-llm', express.json(), async (req: Request, res: Response) => {
    try {
      const { text, model, knownSpeakers } = req.body as { 
        text: string; 
        model?: string;
        knownSpeakers?: string[];
      };
      
      if (!text || typeof text !== 'string') {
        return res.status(400).json({ error: 'Text is required' });
      }

      // Check if OpenRouter is configured
      if (!isOpenRouterConfigured()) {
        console.log('OpenRouter not configured, falling back to basic parsing');
        const fallbackResult = await fallbackToBasicParsing(text);
        return res.json({
          ...fallbackResult,
          _fallback: true,
          _fallbackReason: 'OpenRouter not configured'
        });
      }

      try {
        const speakers = Array.isArray(knownSpeakers) ? knownSpeakers : [];
        const result = await parseTextWithLLM(text, model, speakers);
        
        // Calculate proper text positions and include all new fields
        let currentPos = 0;
        const segments = result.segments.map((seg, index) => {
          const segmentText = seg.text;
          const startIdx = text.indexOf(segmentText, currentPos);
          const startIndex = startIdx >= 0 ? startIdx : currentPos;
          const endIndex = startIndex + segmentText.length;
          currentPos = endIndex;
          
          return {
            id: `seg-${Date.now()}-${index}`,
            type: seg.type,
            text: segmentText,
            speaker: seg.speaker,
            speakerCandidates: seg.speakerCandidates,
            needsReview: seg.needsReview,
            sentiment: seg.sentiment || { label: "neutral" as const, score: 0.5 },
            startIndex,
            endIndex,
            chunkId: seg.chunkId,
            approxDurationSeconds: seg.approxDurationSeconds,
          };
        });

        res.json({
          segments,
          detectedSpeakers: result.detectedSpeakers,
        });
      } catch (llmError) {
        // LLM failed, fall back to basic parsing
        console.error('LLM parsing failed, falling back to basic:', llmError);
        const fallbackResult = await fallbackToBasicParsing(text);
        return res.json({
          ...fallbackResult,
          _fallback: true,
          _fallbackReason: llmError instanceof Error ? llmError.message : 'LLM error'
        });
      }
    } catch (error) {
      console.error('Parse error:', error);
      res.status(500).json({ 
        error: 'Failed to parse text',
        message: error instanceof Error ? error.message : 'Unknown error'
      });
    }
  });

  // Streaming LLM parsing endpoint with SSE
  app.post('/api/parse-text-llm-stream', express.json(), async (req: Request, res: Response) => {
    try {
      const { text, model, knownSpeakers } = req.body as { 
        text: string; 
        model?: string;
        knownSpeakers?: string[];
      };
      
      if (!text || typeof text !== 'string') {
        return res.status(400).json({ error: 'Text is required' });
      }

      // Check if OpenRouter is configured
      if (!isOpenRouterConfigured()) {
        console.log('OpenRouter not configured, falling back to basic parsing');
        const fallbackResult = await fallbackToBasicParsing(text);
        return res.json({
          ...fallbackResult,
          _fallback: true,
          _fallbackReason: 'OpenRouter not configured'
        });
      }

      // Set up SSE headers
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no'); // Disable nginx buffering
      res.flushHeaders();
      
      // Helper to flush after each write
      const sendSSE = (data: object) => {
        res.write(`data: ${JSON.stringify(data)}\n\n`);
        if (typeof (res as any).flush === 'function') {
          (res as any).flush();
        }
      };

      const speakers = Array.isArray(knownSpeakers) ? knownSpeakers : [];
      const streamGenerator = parseTextWithLLMStreaming(text, model, speakers);
      
      let allSegments: any[] = [];
      let allSpeakers: string[] = [];
      let currentPos = 0;
      
      for await (const update of streamGenerator) {
        if (update.type === 'error') {
          sendSSE({ type: 'error', error: update.error });
          res.end();
          return;
        }
        
        if (update.type === 'progress') {
          sendSSE({ 
            type: 'progress', 
            chunkIndex: update.chunkIndex, 
            totalChunks: update.totalChunks 
          });
        }
        
        if (update.type === 'chunk' && update.segments) {
          // Process segments with proper positions and all new fields
          const processedSegments = update.segments.map((seg, index) => {
            const segmentText = seg.text;
            const startIdx = text.indexOf(segmentText, currentPos);
            const startIndex = startIdx >= 0 ? startIdx : currentPos;
            const endIndex = startIndex + segmentText.length;
            currentPos = endIndex;
            
            return {
              id: `seg-${Date.now()}-${allSegments.length + index}`,
              type: seg.type,
              text: segmentText,
              speaker: seg.speaker,
              speakerCandidates: seg.speakerCandidates,
              needsReview: seg.needsReview,
              sentiment: seg.sentiment || { label: "neutral" as const, score: 0.5 },
              startIndex,
              endIndex,
              chunkId: seg.chunkId,
              approxDurationSeconds: seg.approxDurationSeconds,
            };
          });
          
          allSegments.push(...processedSegments);
          allSpeakers = update.detectedSpeakers || [];
          
          sendSSE({ 
            type: 'chunk', 
            chunkIndex: update.chunkIndex, 
            totalChunks: update.totalChunks,
            segments: processedSegments,
            detectedSpeakers: allSpeakers
          });
        }
        
        if (update.type === 'complete') {
          sendSSE({ 
            type: 'complete', 
            totalSegments: allSegments.length,
            detectedSpeakers: allSpeakers
          });
        }
      }
      
      res.end();
    } catch (error) {
      console.error('Streaming parse error:', error);
      if (!res.headersSent) {
        res.status(500).json({ 
          error: 'Failed to parse text',
          message: error instanceof Error ? error.message : 'Unknown error'
        });
      } else {
        res.write(`data: ${JSON.stringify({ type: 'error', error: 'Stream error' })}\n\n`);
        res.end();
      }
    }
  });

  // Get available LLM models
  app.get('/api/models', async (_req: Request, res: Response) => {
    try {
      const models = await getAvailableModels();
      const configured = isOpenRouterConfigured();
      res.json({ models, configured });
    } catch (error) {
      res.status(500).json({ error: 'Failed to fetch models' });
    }
  });

  const apiProxy = createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: undefined,
    logger: console,
    on: {
      error: (err, req, res) => {
        console.error('Proxy error:', err.message);
        if (res && 'writeHead' in res && !res.headersSent) {
          (res as any).writeHead(502, { 'Content-Type': 'application/json' });
          (res as any).end(JSON.stringify({ 
            error: 'Backend service unavailable',
            message: 'Please ensure the Python backend is running on port 8000'
          }));
        }
      },
    },
  });

  app.use('/api', apiProxy);
  
  app.use('/uploads', createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/uploads' + path,
  }));

  app.use('/voice_library', createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/voice_library' + path,
  }));

  app.use('/custom-voices', createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/custom-voices' + path,
  }));

  return httpServer;
}
