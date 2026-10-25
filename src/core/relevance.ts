import { findPath } from './graphUtils';
import type { DependencyGraph, ImpactLevel, ImpactResponse } from './types';

export interface RankedFile {
  path: string;
  score: number;
  reasons: string[];
}

const SYNONYMS: Record<string, string[]> = {
  'role-based access control': ['auth', 'authorization', 'role', 'permission', 'guard', 'middleware', 'user', 'session', 'policy'],
  authentication: ['auth', 'login', 'session', 'token', 'jwt', 'user'],
  authorization: ['auth', 'permission', 'role', 'guard', 'policy', 'middleware'],
  payment: ['billing', 'invoice', 'charge', 'stripe', 'subscription'],
  database: ['model', 'schema', 'repository', 'migration', 'store'],
  api: ['route', 'controller', 'handler', 'endpoint', 'middleware'],
};

function keywordsFor(request: string): string[] {
  const normalized = request.toLowerCase();
  const keywords = new Set(normalized.match(/[a-z][a-z0-9_-]{2,}/g) ?? []);
  for (const [phrase, synonyms] of Object.entries(SYNONYMS)) {
    if (normalized.includes(phrase)) synonyms.forEach((word) => keywords.add(word));
  }
  return [...keywords];
}

function includesKeyword(value: string, keyword: string): boolean {
  return value.toLowerCase().includes(keyword.toLowerCase());
}

/** Ranks a request against local path, exports, and generated summaries, then expands graph neighbors. */
export function rankRelevantFiles(request: string, graph: DependencyGraph, limit = 10): RankedFile[] {
  const keywords = keywordsFor(request);
  const ranked = new Map<string, RankedFile>();

  for (const node of Object.values(graph)) {
    const basename = node.path.split('/').pop() ?? node.path;
    let score = 0;
    const reasons: string[] = [];
    for (const keyword of keywords) {
      if (includesKeyword(basename, keyword)) {
        score += 12;
        reasons.push(`filename matches “${keyword}”`);
      } else if (includesKeyword(node.path, keyword)) {
        score += 8;
        reasons.push(`path matches “${keyword}”`);
      }
      if (node.exports.some((name) => includesKeyword(name, keyword))) {
        score += 5;
        reasons.push(`export matches “${keyword}”`);
      }
      if (includesKeyword(node.summary, keyword)) {
        score += 2;
        reasons.push(`summary matches “${keyword}”`);
      }
    }
    if (score > 0) ranked.set(node.path, { path: node.path, score, reasons: [...new Set(reasons)] });
  }

  // If the request vocabulary is unfamiliar, use well-connected files as a useful local fallback.
  if (ranked.size === 0) {
    Object.values(graph)
      .sort((a, b) => (b.imports.length + b.dependents.length) - (a.imports.length + a.dependents.length))
      .slice(0, Math.min(5, Object.keys(graph).length))
      .forEach((node) => ranked.set(node.path, {
        path: node.path,
        score: node.imports.length + node.dependents.length + 1,
        reasons: ['central local dependency'],
      }));
  }

  const seeds = [...ranked.values()].sort((a, b) => b.score - a.score).slice(0, 5);
  for (const seed of seeds) {
    let frontier = [seed.path];
    for (let hop = 1; hop <= 2; hop += 1) {
      const next: string[] = [];
      for (const path of frontier) {
        const node = graph[path];
        if (!node) continue;
        for (const neighbor of [...node.imports, ...node.dependents]) {
          if (!graph[neighbor] || neighbor === seed.path) continue;
          const existing = ranked.get(neighbor);
          const bonus = hop === 1 ? 5 : 2;
          if (existing) {
            existing.score += bonus;
            existing.reasons.push(`${hop}-hop dependency of ${seed.path}`);
          } else {
            ranked.set(neighbor, {
              path: neighbor,
              score: bonus,
              reasons: [`${hop}-hop dependency of ${seed.path}`],
            });
          }
          next.push(neighbor);
        }
      }
      frontier = [...new Set(next)];
    }
  }

  return [...ranked.values()]
    .map((entry) => ({ ...entry, reasons: [...new Set(entry.reasons)] }))
    .sort((a, b) => b.score - a.score || a.path.localeCompare(b.path))
    .slice(0, limit);
}

function impactFor(index: number): ImpactLevel {
  return index < 3 ? 'high' : index < 6 ? 'medium' : 'low';
}

/** A deliberately transparent fallback response grounded entirely in the local graph. */
export function createLocalMockImpact(request: string, graph: DependencyGraph): ImpactResponse {
  const ranked = rankRelevantFiles(request, graph);
  const selected = new Set(ranked.map((item) => item.path));
  const affectedFiles = ranked.map((item, index) => {
    const node = graph[item.path];
    const dependencyCount = node.imports.length + node.dependents.length;
    const evidence = item.reasons.slice(0, 2).join('; ');
    return {
      path: item.path,
      impact: impactFor(index),
      reason: `Local relevance score: ${evidence || 'connected module'}. It has ${node.imports.length} imports and ${node.dependents.length} dependents.`,
      recommendedChange: `Review this module's ${node.exports.length ? `exports (${node.exports.join(', ')})` : 'public behavior'} and update its ${dependencyCount ? 'connected callers or dependencies' : 'tests and documentation'} as needed.`,
    };
  });

  const dependencyPaths: ImpactResponse['dependencyPaths'] = [];
  for (const item of ranked.slice(0, 5)) {
    const node = graph[item.path];
    const related = [...node.imports, ...node.dependents].find((path) => selected.has(path));
    if (!related) continue;
    const path = findPath(item.path, related, graph) ?? findPath(related, item.path, graph) ?? [item.path, related];
    dependencyPaths.push({ path, reason: 'Both files ranked highly and are connected in the local dependency graph.' });
    if (dependencyPaths.length === 3) break;
  }

  const testFiles = Object.keys(graph).filter((path) => /(?:^|\/)(?:test|tests|__tests__)\//i.test(path) || /\.(?:test|spec)\.[tj]sx?$/i.test(path));
  const score = ranked.reduce((total, item) => total + item.score, 0);
  return {
    summary: `Local mock analysis ranked ${affectedFiles.length} graph-backed files for “${request}”. It is a deterministic fallback based on names, summaries, exports, and dependency relationships—not an AI recommendation.`,
    affectedFiles,
    dependencyPaths,
    testsToUpdate: testFiles.slice(0, 3),
    risks: [
      'Validate the suggested changes against application behavior; this local fallback does not inspect source semantics.',
      'Review indirect callers before merging changes to high-impact shared modules.',
    ],
    confidence: Math.min(0.85, Math.max(0.35, 0.35 + Math.min(score, 60) / 120)),
  };
}
