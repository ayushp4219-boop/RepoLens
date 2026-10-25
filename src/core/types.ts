// Shared TypeScript types used across the extension

export interface GraphNode {
  path: string;
  imports: string[];   // paths this file imports
  dependents: string[]; // paths that import this file
  summary: string;     // one-line summary: exports, fn/class names, top comment
  exports: string[];   // exported symbol names
}

export type DependencyGraph = Record<string, GraphNode>;

export type ImpactLevel = 'high' | 'medium' | 'low';

export interface AffectedFile {
  path: string;
  impact: ImpactLevel;
  reason: string;
  recommendedChange: string;
}

export interface DependencyPath {
  path: string[];
  reason: string;
}

export interface ImpactResponse {
  summary: string;
  affectedFiles: AffectedFile[];
  dependencyPaths: DependencyPath[];
  testsToUpdate: string[];
  risks: string[];
  confidence: number; // 0.0 – 1.0
  source?: 'ai' | 'local' | 'demo' | 'fallback';
}

export interface RepoMeta {
  owner: string;
  repo: string;
  branch: string;
  sha: string;
}

/** Source inventory cached after a fetch. File contents are never persisted. */
export interface RepositorySnapshot {
  meta: RepoMeta;
  sourceFiles: Array<{ path: string; size: number }>;
  graph?: DependencyGraph;
  fetchedAt: string;
}

export type RepositoryProgress = {
  stage: 'discovering' | 'filtering' | 'fetching' | 'complete';
  completed: number;
  total: number;
  message: string;
};

export type RepositoryFetchError =
  | 'rate_limited'
  | 'not_found'
  | 'no_supported_files'
  | 'too_large'
  | 'network_error';

export interface RepositoryFetchResult {
  snapshot?: RepositorySnapshot;
  error?: RepositoryFetchError;
  message?: string;
  canScopeToSrc?: boolean;
}
