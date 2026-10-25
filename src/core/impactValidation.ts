import type { DependencyGraph, ImpactLevel, ImpactResponse } from './types';

const levels = new Set<ImpactLevel>(['high', 'medium', 'low']);

const asStrings = (value: unknown): string[] => Array.isArray(value)
  ? value.filter((item): item is string => typeof item === 'string')
  : [];

/** Removes unsupported and hallucinated paths from an untrusted impact response. */
export function sanitizeImpactResponse(value: unknown, graph: DependencyGraph): ImpactResponse | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (typeof data.summary !== 'string' || !Array.isArray(data.affectedFiles)) return null;

  const affectedFiles = data.affectedFiles.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const file = item as Record<string, unknown>;
    if (typeof file.path !== 'string' || !graph[file.path]) return [];
    if (typeof file.reason !== 'string' || typeof file.recommendedChange !== 'string') return [];
    return [{
      path: file.path,
      impact: levels.has(file.impact as ImpactLevel) ? file.impact as ImpactLevel : 'medium',
      reason: file.reason,
      recommendedChange: file.recommendedChange,
    }];
  });

  const dependencyPaths = Array.isArray(data.dependencyPaths) ? data.dependencyPaths.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const path = asStrings((item as Record<string, unknown>).path);
    const reason = (item as Record<string, unknown>).reason;
    return path.length >= 2 && path.every((entry) => graph[entry]) && typeof reason === 'string'
      ? [{ path, reason }]
      : [];
  }) : [];

  return {
    summary: data.summary,
    affectedFiles,
    dependencyPaths,
    testsToUpdate: asStrings(data.testsToUpdate).filter((path) => Boolean(graph[path])),
    risks: asStrings(data.risks),
    confidence: typeof data.confidence === 'number' ? Math.max(0, Math.min(1, data.confidence)) : 0.5,
    source: data.source === 'fallback' ? 'fallback' : 'ai',
  };
}
