// Typed message definitions for the extension message bus

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
  | { type: 'PING' }
  | { type: 'PONG' };

export function sendToBackground(message: MessageType): Promise<unknown> {
  return chrome.runtime.sendMessage(message);
}

export function sendToTab(tabId: number, message: MessageType): Promise<unknown> {
  return chrome.tabs.sendMessage(tabId, message);
}
