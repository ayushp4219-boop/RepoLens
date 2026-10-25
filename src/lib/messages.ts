// Typed message definitions for the extension message bus

import type { RepositoryFetchResult, RepositoryProgress, RepositorySnapshot } from '../core/types';

export type RepoContext = {
  owner: string;
  repo: string;
  path: string;
  href: string;
};

export type MessageType =
  | { type: 'REPO_CONTEXT'; payload: RepoContext }
  | { type: 'OPEN_PANEL' }
  | { type: 'GET_REPO_CONTEXT' }
  | { type: 'REPO_CONTEXT_RESPONSE'; payload: RepoContext | null }
  | { type: 'FETCH_REPOSITORY'; payload: { context: RepoContext; scope?: 'all' | 'src' } }
  | { type: 'REPOSITORY_FETCH_RESPONSE'; payload: RepositoryFetchResult }
  | { type: 'REPOSITORY_PROGRESS'; payload: RepositoryProgress }
  | { type: 'GET_REPOSITORY_SNAPSHOT'; payload: { owner: string; repo: string; sha: string } }
  | { type: 'REPOSITORY_SNAPSHOT_RESPONSE'; payload: RepositorySnapshot | null }
  | { type: 'PING' }
  | { type: 'PONG' };

export function sendToBackground(message: MessageType): Promise<unknown> {
  return chrome.runtime.sendMessage(message);
}

export function sendToTab(tabId: number, message: MessageType): Promise<unknown> {
  return chrome.tabs.sendMessage(tabId, message);
}
