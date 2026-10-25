/**
 * chrome.storage.local wrapper with typed helpers.
 * We store ONLY graph + summaries, never raw file contents.
 */

export interface StorageSchema {
  githubToken: string;
  demoMode: boolean;
  proxyUrl: string;
  // Cached analyses keyed by "owner/repo@sha"
  [cacheKey: `cache:${string}`]: unknown;
}

export async function getStorage<K extends keyof StorageSchema>(
  key: K,
): Promise<StorageSchema[K] | undefined> {
  const result = await chrome.storage.local.get(key);
  return result[key] as StorageSchema[K] | undefined;
}

export async function setStorage<K extends keyof StorageSchema>(
  key: K,
  value: StorageSchema[K],
): Promise<void> {
  await chrome.storage.local.set({ [key]: value });
}

export async function getSettings(): Promise<{
  githubToken: string;
  demoMode: boolean;
  proxyUrl: string;
}> {
  const result = await chrome.storage.local.get(['githubToken', 'demoMode', 'proxyUrl']);
  return {
    githubToken: (result.githubToken as string) || '',
    demoMode: (result.demoMode as boolean) || false,
    proxyUrl: (result.proxyUrl as string) || '',
  };
}

export async function getCachedAnalysis(cacheKey: string): Promise<unknown | undefined> {
  const result = await chrome.storage.local.get(`cache:${cacheKey}`);
  return result[`cache:${cacheKey}`];
}

export async function setCachedAnalysis(cacheKey: string, data: unknown): Promise<void> {
  await chrome.storage.local.set({ [`cache:${cacheKey}`]: data });
}
