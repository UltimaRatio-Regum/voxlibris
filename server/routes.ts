import type { Express, Request, Response } from "express";
import { createServer, type Server } from "http";
import { createProxyMiddleware } from "http-proxy-middleware";
import express from "express";
import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { parseTextWithLLM, parseTextWithLLMStreaming, getAvailableModels, isOpenRouterConfigured, invalidatePromptCache } from "./llm-service";
import { ensureAuthenticated, ensureAdmin } from "./auth";

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

function getUserHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  if (req.isAuthenticated() && req.user) {
    const user = req.user as any;
    headers['X-User-Id'] = user.id;
    headers['X-User-Role'] = user.user_type;
  }
  return headers;
}

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {

  app.post('/api/parse-text-llm', ensureAuthenticated, express.json(), async (req: Request, res: Response) => {
    try {
      const { text, model, knownSpeakers } = req.body as { 
        text: string; 
        model?: string;
        knownSpeakers?: string[];
      };
      
      if (!text || typeof text !== 'string') {
        return res.status(400).json({ error: 'Text is required' });
      }

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

  app.post('/api/parse-text-llm-stream', ensureAuthenticated, express.json(), async (req: Request, res: Response) => {
    try {
      const { text, model, knownSpeakers } = req.body as { 
        text: string; 
        model?: string;
        knownSpeakers?: string[];
      };
      
      if (!text || typeof text !== 'string') {
        return res.status(400).json({ error: 'Text is required' });
      }

      if (!isOpenRouterConfigured()) {
        console.log('OpenRouter not configured, falling back to basic parsing');
        const fallbackResult = await fallbackToBasicParsing(text);
        return res.json({
          ...fallbackResult,
          _fallback: true,
          _fallbackReason: 'OpenRouter not configured'
        });
      }

      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no');
      res.flushHeaders();
      
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

  app.get('/api/models', ensureAuthenticated, async (_req: Request, res: Response) => {
    try {
      const models = await getAvailableModels();
      const configured = isOpenRouterConfigured();
      res.json({ models, configured });
    } catch (error) {
      res.status(500).json({ error: 'Failed to fetch models' });
    }
  });

  app.post('/api/parsing-prompt', ensureAdmin, express.json(), async (req: Request, res: Response) => {
    try {
      const resp = await fetch(`${PYTHON_BACKEND_URL}/parsing-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req.body),
      });
      const data = await resp.json();
      invalidatePromptCache();
      res.json(data);
    } catch (error) {
      res.status(500).json({ error: 'Failed to save parsing prompt' });
    }
  });

  app.delete('/api/parsing-prompt', ensureAdmin, async (_req: Request, res: Response) => {
    try {
      const resp = await fetch(`${PYTHON_BACKEND_URL}/parsing-prompt`, { method: 'DELETE' });
      const data = await resp.json();
      invalidatePromptCache();
      res.json(data);
    } catch (error) {
      res.status(500).json({ error: 'Failed to reset parsing prompt' });
    }
  });

  const DOCS_DIR = path.resolve(process.cwd(), "docs");

  function getDocsManifest() {
    if (!fs.existsSync(DOCS_DIR)) return [];
    const files = fs.readdirSync(DOCS_DIR).filter(f => f.endsWith('.md'));
    interface DocManifestEntry {
      slug: string;
      filename: string;
      title: string;
      description: string;
      category: string;
      order: number;
      keywords: string[];
    }
    const entries: DocManifestEntry[] = [];
    for (const filename of files) {
      const raw = fs.readFileSync(path.join(DOCS_DIR, filename), 'utf-8');
      const { data } = matter(raw);
      if (!data.title) continue;
      const slug = filename.replace(/^\d+-/, '').replace(/\.md$/, '');
      entries.push({
        slug,
        filename,
        title: data.title as string,
        description: (data.description as string) || '',
        category: (data.category as string) || 'General',
        order: (data.order as number) || 99,
        keywords: (data.keywords as string[]) || [],
      });
    }
    return entries.sort((a, b) => a.order - b.order);
  }

  app.get('/api/docs/manifest', (_req: Request, res: Response) => {
    try {
      const manifest = getDocsManifest();
      res.json(manifest);
    } catch (error) {
      res.status(500).json({ error: 'Failed to read documentation' });
    }
  });

  app.get('/api/docs/:slug', (req: Request, res: Response) => {
    try {
      const { slug } = req.params;
      const manifest = getDocsManifest();
      const entry = manifest.find(m => m.slug === slug);
      if (!entry) {
        return res.status(404).json({ error: 'Document not found' });
      }
      const raw = fs.readFileSync(path.join(DOCS_DIR, entry.filename), 'utf-8');
      const { content } = matter(raw);
      res.json({ ...entry, content });
    } catch (error) {
      res.status(500).json({ error: 'Failed to read document' });
    }
  });

  const apiProxy = createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: undefined,
    logger: console,
    on: {
      proxyReq: (proxyReq, req) => {
        const headers = getUserHeaders(req as Request);
        for (const [key, value] of Object.entries(headers)) {
          proxyReq.setHeader(key, value);
        }
        if ((req as any).body && !req.headers['content-type']?.includes('multipart/form-data')) {
          const bodyData = JSON.stringify((req as any).body);
          proxyReq.setHeader('Content-Type', 'application/json');
          proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData));
          proxyReq.write(bodyData);
        }
      },
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

  app.use('/api', ensureAuthenticated, apiProxy);
  
  app.use('/uploads', ensureAuthenticated, createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/uploads' + path,
    on: {
      proxyReq: (proxyReq, req) => {
        const headers = getUserHeaders(req as Request);
        for (const [key, value] of Object.entries(headers)) {
          proxyReq.setHeader(key, value);
        }
      },
    },
  }));

  app.use('/voice_library', ensureAuthenticated, createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/voice_library' + path,
    on: {
      proxyReq: (proxyReq, req) => {
        const headers = getUserHeaders(req as Request);
        for (const [key, value] of Object.entries(headers)) {
          proxyReq.setHeader(key, value);
        }
      },
    },
  }));

  app.use('/custom-voices', ensureAuthenticated, createProxyMiddleware({
    target: PYTHON_BACKEND_URL,
    changeOrigin: true,
    pathRewrite: (path, req) => '/custom-voices' + path,
    on: {
      proxyReq: (proxyReq, req) => {
        const headers = getUserHeaders(req as Request);
        for (const [key, value] of Object.entries(headers)) {
          proxyReq.setHeader(key, value);
        }
      },
    },
  }));

  return httpServer;
}
