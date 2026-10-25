import type {
  RepoMeta,
  RepositoryFetchResult,
  RepositoryProgress,
  RepositorySnapshot,
} from '../core/types';

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
): Promise<void> {
  // Raw URLs do not consume GitHub REST API quota. Bodies are intentionally discarded:
  // Phase 4 will parse them into a graph without ever placing source in extension storage.
  let completed = 0;
  const workers = Array.from({ length: Math.min(6, paths.length) }, async () => {
    while (paths.length > 0) {
      const path = paths.shift();
      if (!path) return;
      try {
        await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${sha}/${path}`);
      } catch {
        // Keep the inventory useful even when one optional raw fetch fails.
      }
      completed += 1;
      onProgress({
        stage: 'fetching',
        completed,
        total: completed + paths.length,
        message: `Fetching ${completed}/${completed + paths.length} files`,
      });
    }
  });
  await Promise.all(workers);
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
    await fetchInBatches(owner, repo, commit.sha, sourceFiles.map((file) => file.path), onProgress);
    const snapshot: RepositorySnapshot = { meta, sourceFiles, fetchedAt: new Date().toISOString() };
    onProgress({ stage: 'complete', completed: sourceFiles.length, total: sourceFiles.length, message: `Ready — ${sourceFiles.length} files fetched` });
    return { snapshot };
  } catch (error) {
    const failure = error as Partial<GitHubFailure>;
    return { error: failure.kind ?? 'network_error', message: failure.message ?? 'Unable to fetch this repository.' };
  }
}
