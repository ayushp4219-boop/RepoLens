/**
 * Pure graph utility functions — no external dependencies, fully unit-testable.
 */

import type { DependencyGraph } from './types';

/**
 * Given a set of directly-impacted file paths, return the set of files
 * that transitively depend on them (their dependents), up to `hops` levels.
 * Direct-impact files are excluded from the result.
 */
export function computeIndirectImpact(
  directPaths: string[],
  graph: DependencyGraph,
  hops = 2,
): Set<string> {
  const directSet = new Set(directPaths);
  const indirect = new Set<string>();
  let frontier = [...directSet];

  for (let h = 0; h < hops; h++) {
    const nextFrontier: string[] = [];
    for (const path of frontier) {
      const node = graph[path];
      if (!node) continue;
      for (const dep of node.dependents) {
        if (!directSet.has(dep) && !indirect.has(dep) && graph[dep]) {
          indirect.add(dep);
          nextFrontier.push(dep);
        }
      }
    }
    frontier = nextFrontier;
    if (frontier.length === 0) break;
  }

  return indirect;
}

/**
 * Returns the shortest path between two nodes using BFS on the imports graph.
 * Returns null if no path exists.
 */
export function findPath(
  from: string,
  to: string,
  graph: DependencyGraph,
): string[] | null {
  if (from === to) return [from];

  const visited = new Set<string>();
  const queue: Array<{ node: string; path: string[] }> = [{ node: from, path: [from] }];

  while (queue.length > 0) {
    const item = queue.shift();
    if (!item) break;
    const { node, path } = item;

    if (visited.has(node)) continue;
    visited.add(node);

    const graphNode = graph[node];
    if (!graphNode) continue;

    for (const imp of graphNode.imports) {
      if (imp === to) return [...path, imp];
      if (!visited.has(imp)) {
        queue.push({ node: imp, path: [...path, imp] });
      }
    }
  }

  return null;
}

/**
 * Detects strongly connected components (circular dependency groups)
 * using an iterative DFS approximation suitable for small graphs.
 */
export function findCircularGroups(graph: DependencyGraph): string[][] {
  const visited = new Set<string>();
  const groups: string[][] = [];

  for (const start of Object.keys(graph)) {
    if (visited.has(start)) continue;

    const stack: string[] = [start];
    const group: string[] = [];
    const inStack = new Set<string>();

    while (stack.length > 0) {
      const node = stack[stack.length - 1];
      if (!inStack.has(node)) {
        inStack.add(node);
        group.push(node);
      }

      const graphNode = graph[node];
      let pushed = false;

      if (graphNode) {
        for (const imp of graphNode.imports) {
          if (!visited.has(imp) && !inStack.has(imp) && graph[imp]) {
            stack.push(imp);
            pushed = true;
            break;
          }
        }
      }

      if (!pushed) {
        stack.pop();
        visited.add(node);
      }
    }

    if (group.length > 1) groups.push(group);
  }

  return groups;
}

/** Returns paths that have no dependents and are not entry-point-like files. */
export function findOrphans(graph: DependencyGraph): string[] {
  const ENTRY_PATTERNS = ['server', 'main', 'index', 'app'];

  return Object.values(graph)
    .filter((node) => {
      const isOrphan = node.dependents.length === 0;
      const basename = node.path.split('/').pop()?.replace(/\.\w+$/, '') ?? '';
      const isEntryLike = ENTRY_PATTERNS.some((p) => basename.toLowerCase().includes(p));
      return isOrphan && !isEntryLike;
    })
    .map((n) => n.path);
}

/** Generates a markdown document from an impact analysis result. */
export function generateImpactMarkdown(
  changeRequest: string,
  result: import('./types').ImpactResponse,
  repo: { owner: string; repo: string },
): string {
  const lines: string[] = [
    `# RepoLens Impact Analysis`,
    ``,
    `**Repository:** ${repo.owner}/${repo.repo}`,
    `**Change Request:** ${changeRequest}`,
    `**Confidence:** ${Math.round(result.confidence * 100)}%`,
    ``,
    `## Summary`,
    ``,
    result.summary,
    ``,
  ];

  const groups: Array<[import('./types').ImpactLevel, string]> = [
    ['high', 'High Impact'],
    ['medium', 'Medium Impact'],
    ['low', 'Low Impact'],
  ];

  for (const [level, label] of groups) {
    const files = result.affectedFiles.filter((f) => f.impact === level);
    if (files.length === 0) continue;

    lines.push(`## ${label} Files`, ``);
    for (const file of files) {
      lines.push(`### \`${file.path}\``);
      lines.push(`**Why:** ${file.reason}`);
      lines.push(`**Recommended change:** ${file.recommendedChange}`, ``);
    }
  }

  if (result.dependencyPaths.length > 0) {
    lines.push(`## Dependency Paths`, ``);
    for (const dp of result.dependencyPaths) {
      lines.push(`- \`${dp.path.join(' → ')}\``);
      lines.push(`  ${dp.reason}`, ``);
    }
  }

  if (result.testsToUpdate.length > 0) {
    lines.push(`## Tests to Update`, ``);
    for (const t of result.testsToUpdate) lines.push(`- \`${t}\``);
    lines.push(``);
  }

  if (result.risks.length > 0) {
    lines.push(`## Risks`, ``);
    for (const r of result.risks) lines.push(`- ⚠️ ${r}`);
    lines.push(``);
  }

  lines.push(`---`, `*Generated by [RepoLens](https://github.com/ayushp4219-boop/RepoLens)*`);
  return lines.join('\n');
}
