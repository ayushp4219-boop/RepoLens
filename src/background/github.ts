import type {
  RepoMeta,
  RepositoryFetchResult,
  RepositoryProgress,
  RepositorySnapshot,
} from '../core/types';
import { buildDependencyGraph, parseTsconfig, type SourceFile } from '../core/analyzer';

const MAX_FILES = 150;
const MAX_FILE_BYTES = 200 * 1024;
const SOURCE_FILE = /\.(?:ts|tsx|js|jsx)$/i;
const EXCLUDED_PATH = /(?:^|\/)(?:node_modules|dist|build|vendor)(?:\/|$)/i;
const EXCLUDED_FILE = /(?:\.d\.ts$|\.min\.[^.]+$|(?:package-)?lock\.(?:json|ya?ml)$)/i;

type TreeEntry = { path: string; type: string; size?: number };
type GitHubFailure = { kind: 'rate_limited' | 'not_found' | 'network_error'; message: string };

function supported(entry: TreeEntry): boolean {
  return entry.type === 'blob'
    && SOURCE_FILE.test(entry.path)
    && !EXCLUDED_PATH.test(entry.path)
    && !EXCLUDED_FILE.test(entry.path)
    && (entry.size ?? 0) <= MAX_FILE_BYTES;
}

async function api<T>(url: string, token: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: 'application/vnd.github+json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch {
    throw { kind: 'network_error', message: 'Unable to reach GitHub. Check your connection and try again.' } satisfies GitHubFailure;
  }

  if (response.status === 403 && response.headers.get('x-ratelimit-remaining') === '0') {
    throw { kind: 'rate_limited', message: 'GitHub API rate limit reached. Add a token in Options or try again later.' } satisfies GitHubFailure;
  }
  if (response.status === 404) {
    throw { kind: 'not_found', message: 'Repository not found or it is private.' } satisfies GitHubFailure;
  }
  if (!response.ok) {
    throw { kind: 'network_error', message: `GitHub request failed (${response.status}). Please try again.` } satisfies GitHubFailure;
  }
  return response.json() as Promise<T>;
}

async function fetchInBatches(
  owner: string,
  repo: string,
  sha: string,
  paths: string[],
  onProgress: (progress: RepositoryProgress) => void,
): Promise<SourceFile[]> {
  // Raw URLs do not consume GitHub REST API quota. The content exists only in this
  // function long enough to build the graph; it is never sent to the panel or saved.
  let completed = 0;
  let index = 0;
  const total = paths.length;
  const sourceFiles: SourceFile[] = [];
  const workers = Array.from({ length: Math.min(6, total) }, async () => {
    while (index < total) {
      const path = paths[index++];
      if (!path) return;
      try {
        const response = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${sha}/${path}`);
        if (response.ok) sourceFiles.push({ path, content: await response.text() });
      } catch {
        // A single raw fetch should not prevent graph construction for other files.
      }
      completed += 1;
      onProgress({
        stage: 'fetching',
        completed,
        total,
        message: `Fetching ${completed}/${total} files`,
      });
    }
  });
  await Promise.all(workers);
  return sourceFiles;
}

async function fetchTsconfig(owner: string, repo: string, sha: string): Promise<string> {
  try {
    const response = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${sha}/tsconfig.json`);
    return response.ok ? await response.text() : '';
  } catch {
    return '';
  }
}

export async function fetchRepository(
  owner: string,
  repo: string,
  token: string,
  scope: 'all' | 'src',
  onProgress: (progress: RepositoryProgress) => void,
): Promise<RepositoryFetchResult> {
  try {
    onProgress({ stage: 'discovering', completed: 0, total: 1, message: 'Finding default branch…' });
    const repository = await api<{ default_branch: string }>(`https://api.github.com/repos/${owner}/${repo}`, token);
    const branch = repository.default_branch;
    const commit = await api<{ sha: string }>(`https://api.github.com/repos/${owner}/${repo}/commits/${encodeURIComponent(branch)}`, token);
    const meta: RepoMeta = { owner, repo, branch, sha: commit.sha };

    onProgress({ stage: 'discovering', completed: 1, total: 1, message: 'Reading repository tree…' });
    const tree = await api<{ truncated: boolean; tree: TreeEntry[] }>(
      `https://api.github.com/repos/${owner}/${repo}/git/trees/${commit.sha}?recursive=1`, token,
    );
    if (tree.truncated) {
      return { error: 'too_large', message: 'GitHub returned a truncated tree. Choose a smaller repository.' };
    }

    const eligible = tree.tree.filter(supported);
    const srcFiles = eligible.filter((entry) => entry.path.startsWith('src/'));
    const candidates = scope === 'src' ? srcFiles : eligible;
    onProgress({ stage: 'filtering', completed: candidates.length, total: candidates.length, message: `Found ${candidates.length} supported files` });

    if (candidates.length === 0) {
      return { error: 'no_supported_files', message: 'No supported TypeScript or JavaScript files were found.' };
    }
    if (candidates.length > MAX_FILES) {
      return {
        error: 'too_large',
        message: `This repository has ${candidates.length} supported files; RepoLens analyzes up to ${MAX_FILES} at a time.`,
        canScopeToSrc: scope === 'all' && srcFiles.length > 0 && srcFiles.length <= MAX_FILES,
      };
    }

    const sourceFiles = candidates.map(({ path, size = 0 }) => ({ path, size }));
    const [contents, tsconfig] = await Promise.all([
      fetchInBatches(owner, repo, commit.sha, sourceFiles.map((file) => file.path), onProgress),
      fetchTsconfig(owner, repo, commit.sha),
    ]);
    const snapshot: RepositorySnapshot = {
      meta,
      sourceFiles,
      graph: buildDependencyGraph(contents, parseTsconfig(tsconfig)),
      fetchedAt: new Date().toISOString(),
    };
    onProgress({ stage: 'complete', completed: sourceFiles.length, total: sourceFiles.length, message: `Ready — ${sourceFiles.length} files fetched` });
    return { snapshot };
  } catch (error) {
    const failure = error as Partial<GitHubFailure>;
    return { error: failure.kind ?? 'network_error', message: failure.message ?? 'Unable to fetch this repository.' };
  }
}
