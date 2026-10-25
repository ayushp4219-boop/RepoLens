type ImpactFile = { path: string; summary: string; imports: string[]; dependents: string[] };
type ImpactRequest = { changeRequest?: unknown; files?: unknown };
type ResponseLike = {
  status: (code: number) => ResponseLike;
  json: (body: unknown) => void;
  end: () => void;
  setHeader: (name: string, value: string) => void;
};
type RequestLike = { method?: string; body?: ImpactRequest; headers: Record<string, string | string[] | undefined>; socket?: { remoteAddress?: string } };

const windows = new Map<string, { count: number; startedAt: number }>();
const RATE_WINDOW_MS = 60_000;
const RATE_LIMIT = 30;

function allowCors(req: RequestLike, res: ResponseLike): void {
  const origin = typeof req.headers.origin === 'string' ? req.headers.origin : '';
  const configured = process.env.ALLOWED_ORIGIN;
  if (origin && (origin === configured || (!configured && /^chrome-extension:\/\/[a-p]{32}$/.test(origin)))) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

function rateLimited(req: RequestLike): boolean {
  const key = (typeof req.headers['x-forwarded-for'] === 'string' ? req.headers['x-forwarded-for'].split(',')[0] : req.socket?.remoteAddress) ?? 'unknown';
  const now = Date.now();
  const window = windows.get(key);
  if (!window || now - window.startedAt > RATE_WINDOW_MS) {
    windows.set(key, { count: 1, startedAt: now });
    return false;
  }
  window.count += 1;
  return window.count > RATE_LIMIT;
}

function validFiles(value: unknown): ImpactFile[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length > 10) return null;
  const files: ImpactFile[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') return null;
    const file = item as Record<string, unknown>;
    if (typeof file.path !== 'string' || typeof file.summary !== 'string' || !Array.isArray(file.imports) || !Array.isArray(file.dependents)) return null;
    files.push({
      path: file.path,
      summary: file.summary,
      imports: file.imports.filter((entry): entry is string => typeof entry === 'string'),
      dependents: file.dependents.filter((entry): entry is string => typeof entry === 'string'),
    });
  }
  return files;
}

function stripFences(value: string): string {
  return value.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
}

function validResponse(value: unknown, files: ImpactFile[]): boolean {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (typeof data.summary !== 'string' || !Array.isArray(data.affectedFiles) || !Array.isArray(data.dependencyPaths) || !Array.isArray(data.testsToUpdate) || !Array.isArray(data.risks) || typeof data.confidence !== 'number') return false;
  const paths = new Set(files.map((file) => file.path));
  return data.affectedFiles.every((item) => item && typeof item === 'object' && paths.has((item as Record<string, unknown>).path as string))
    && data.dependencyPaths.every((item) => item && typeof item === 'object' && Array.isArray((item as Record<string, unknown>).path) && ((item as Record<string, unknown>).path as unknown[]).every((path) => typeof path === 'string' && paths.has(path)));
}

function fallback(changeRequest: string, files: ImpactFile[]): Record<string, unknown> {
  return {
    source: 'fallback',
    summary: `The AI response was unavailable, so RepoLens returned a safe fallback based on ${files.length} locally selected files for “${changeRequest}”.`,
    affectedFiles: files.map((file, index) => ({
      path: file.path,
      impact: index < 3 ? 'high' : index < 6 ? 'medium' : 'low',
      reason: `This file was selected by local relevance scoring. ${file.summary}`,
      recommendedChange: 'Review this module and its listed local dependencies before implementing the requested change.',
    })),
    dependencyPaths: files.slice(0, 3).flatMap((file) => {
      const target = file.imports.find((path) => files.some((candidate) => candidate.path === path));
      return target ? [{ path: [file.path, target], reason: 'Local dependency relationship.' }] : [];
    }),
    testsToUpdate: files.filter((file) => /(?:test|spec)\.[tj]sx?$/i.test(file.path)).map((file) => file.path),
    risks: ['Validate this fallback plan against the implementation; the AI response could not be used.'],
    confidence: 0.45,
  };
}

function promptFor(changeRequest: string, files: ImpactFile[]): string {
  return `You are RepoLens. Return JSON only—no markdown or commentary. Analyze this requested repository change using only the supplied file metadata. Never invent a path. Every affectedFiles.path and every dependencyPaths path item must exactly match a supplied file path.\n\nRequired JSON schema:\n{"summary":"short explanation","affectedFiles":[{"path":"supplied path","impact":"high|medium|low","reason":"repository evidence","recommendedChange":"specific proposed edit"}],"dependencyPaths":[{"path":["supplied path"],"reason":"why it matters"}],"testsToUpdate":["supplied path"],"risks":["risk"],"confidence":0.0}\n\nChange request:\n${changeRequest}\n\nFiles:\n${JSON.stringify(files)}`;
}

async function callGemma(prompt: string): Promise<unknown> {
  const url = process.env.GEMMA_API_URL;
  const key = process.env.GEMMA_API_KEY;
  if (!url || !key) throw new Error('Gemma proxy is not configured');
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({ model: process.env.GEMMA_MODEL ?? 'gemma-3-27b-it', messages: [{ role: 'user', content: prompt }], temperature: 0.15 }),
  });
  if (!response.ok) throw new Error(`Gemma request failed (${response.status})`);
  const body = await response.json() as { choices?: Array<{ message?: { content?: string } }>; candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> };
  const content = body.choices?.[0]?.message?.content ?? body.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!content) throw new Error('Gemma response had no text');
  return JSON.parse(stripFences(content));
}

export default async function handler(req: RequestLike, res: ResponseLike): Promise<void> {
  allowCors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  if (rateLimited(req)) return res.status(429).json({ error: 'Too many requests. Try again shortly.' });

  const changeRequest = typeof req.body?.changeRequest === 'string' ? req.body.changeRequest.trim() : '';
  const files = validFiles(req.body?.files);
  if (!changeRequest || !files) return res.status(400).json({ error: 'Expected a changeRequest and 1–10 file summaries.' });

  const prompt = promptFor(changeRequest, files);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const result = await callGemma(prompt);
      if (validResponse(result, files)) return res.status(200).json(result);
    } catch {
      // Retry once, then return an explicit safe fallback below.
    }
  }
  return res.status(200).json(fallback(changeRequest, files));
}
