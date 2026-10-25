import type { DependencyGraph, GraphNode } from './types';

const SOURCE_EXTENSIONS = ['.ts', '.tsx', '.js', '.jsx'];

export type SourceFile = { path: string; content: string };
export type PathConfig = { baseUrl?: string; paths?: Record<string, string[]> };

const cleanPath = (value: string) => value.replace(/^\.\//, '').replace(/\/+/g, '/').replace(/\/\/+/g, '/');

function dirname(path: string): string {
  const slash = path.lastIndexOf('/');
  return slash === -1 ? '' : path.slice(0, slash);
}

function join(base: string, target: string): string {
  const segments = `${base}/${target}`.split('/');
  const resolved: string[] = [];
  for (const segment of segments) {
    if (!segment || segment === '.') continue;
    if (segment === '..') resolved.pop();
    else resolved.push(segment);
  }
  return resolved.join('/');
}

/** Extracts static imports, re-exports, CommonJS requires, and string-literal dynamic imports. */
export function parseImportSpecifiers(content: string): string[] {
  const found = new Set<string>();
  const patterns = [
    /\b(?:import|export)\s+(?:type\s+)?(?:[^'"\n;]+?\s+from\s+)?['"]([^'"]+)['"]/g,
    /\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
    /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
  ];
  for (const pattern of patterns) {
    for (const match of content.matchAll(pattern)) found.add(match[1]);
  }
  return [...found];
}

function candidatePaths(base: string): string[] {
  const normalized = cleanPath(base);
  const ext = SOURCE_EXTENSIONS.find((extension) => normalized.endsWith(extension));
  if (ext) {
    const stem = normalized.slice(0, -ext.length);
    // A compiled .js import commonly points back to a TS source module.
    return [...new Set([normalized, ...SOURCE_EXTENSIONS.map((extension) => `${stem}${extension}`)])];
  }
  return [
    ...SOURCE_EXTENSIONS.map((extension) => `${normalized}${extension}`),
    ...SOURCE_EXTENSIONS.map((extension) => `${normalized}/index${extension}`),
  ];
}

function aliasTarget(specifier: string, config: PathConfig): string | null {
  for (const [pattern, targets] of Object.entries(config.paths ?? {})) {
    const star = pattern.indexOf('*');
    const prefix = star === -1 ? pattern : pattern.slice(0, star);
    const suffix = star === -1 ? '' : pattern.slice(star + 1);
    if (!specifier.startsWith(prefix) || !specifier.endsWith(suffix)) continue;
    const replacement = star === -1 ? '' : specifier.slice(prefix.length, specifier.length - suffix.length);
    const target = targets[0];
    if (target) return target.replace('*', replacement);
  }
  return null;
}

/** Resolves only repository-local modules. Package imports intentionally return null. */
export function resolveImport(
  fromPath: string,
  specifier: string,
  available: Set<string>,
  config: PathConfig = {},
): string | null {
  let target: string | null = null;
  if (specifier.startsWith('.')) {
    target = join(dirname(fromPath), specifier);
  } else {
    const alias = aliasTarget(specifier, config);
    if (alias) target = join(config.baseUrl ?? '', alias);
  }
  if (!target) return null;
  return candidatePaths(target).find((candidate) => available.has(candidate)) ?? null;
}

export function summarizeFile(content: string): Pick<GraphNode, 'summary' | 'exports'> {
  const exports = new Set<string>();
  for (const match of content.matchAll(/\bexport\s+(?:default\s+)?(?:async\s+)?(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g)) {
    exports.add(match[1]);
  }
  for (const match of content.matchAll(/\bexport\s*{([^}]+)}/g)) {
    for (const part of match[1].split(',')) exports.add(part.trim().split(/\s+as\s+/i).pop() ?? '');
  }
  const names = [...exports].filter(Boolean).slice(0, 8);
  const declarations = [...content.matchAll(/\b(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)/g)]
    .map((match) => match[1]).slice(0, 5);
  const comment = content.match(/^\s*(?:\/\/\s*([^\n]+)|\/\*\*?\s*([\s\S]*?)\*\/)/)?.slice(1).find(Boolean)
    ?.replace(/\s*\*\s*/g, ' ').trim();
  const parts = [
    comment,
    names.length ? `Exports: ${names.join(', ')}.` : '',
    declarations.length ? `Defines: ${declarations.join(', ')}.` : '',
  ].filter(Boolean);
  return { exports: names, summary: parts.join(' ') || 'Source module.' };
}

export function buildDependencyGraph(files: SourceFile[], config: PathConfig = {}): DependencyGraph {
  const available = new Set(files.map((file) => cleanPath(file.path)));
  const graph: DependencyGraph = {};
  for (const file of files) {
    const path = cleanPath(file.path);
    const imports = parseImportSpecifiers(file.content)
      .map((specifier) => resolveImport(path, specifier, available, config))
      .filter((resolved): resolved is string => Boolean(resolved));
    const { summary, exports } = summarizeFile(file.content);
    graph[path] = { path, imports: [...new Set(imports)], dependents: [], summary, exports };
  }
  for (const node of Object.values(graph)) {
    for (const imported of node.imports) graph[imported]?.dependents.push(node.path);
  }
  return graph;
}

/** Parses common tsconfig JSON-with-comments safely enough for path aliases. */
export function parseTsconfig(content: string): PathConfig {
  try {
    const cleaned = content.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    const parsed = JSON.parse(cleaned) as { compilerOptions?: { baseUrl?: string; paths?: Record<string, string[]> } };
    return { baseUrl: parsed.compilerOptions?.baseUrl, paths: parsed.compilerOptions?.paths };
  } catch {
    return {};
  }
}
