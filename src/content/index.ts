/**
 * Content script — runs on https://github.com/* pages only.
 * Responsibilities:
 *  1. Detect owner/repo/path from the current URL.
 *  2. Send REPO_CONTEXT to the background worker.
 *  3. Re-detect on GitHub SPA navigation (turbo:load, popstate, pushState).
 */

import type { RepoContext } from '../lib/messages';

// ── URL parsing ──────────────────────────────────────────────────────────────

function parseGitHubUrl(href: string): RepoContext | null {
  try {
    const url = new URL(href);
    if (!url.hostname.includes('github.com')) return null;

    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length < 2) return null;

    const owner = parts[0];
    const repo = parts[1];

    // Skip special github.com paths
    const SKIP = ['login', 'logout', 'settings', 'marketplace', 'explore', 'topics', 'trending'];
    if (SKIP.includes(owner)) return null;

    const path = parts.slice(2).join('/');

    return { owner, repo, path, href };
  } catch {
    return null;
  }
}

// ── Context dispatch ─────────────────────────────────────────────────────────

let lastSentHref = '';

function detectAndSend(href: string = window.location.href): void {
  if (href === lastSentHref) return;
  lastSentHref = href;

  const context = parseGitHubUrl(href);
  if (!context) return;

  chrome.runtime.sendMessage({ type: 'REPO_CONTEXT', payload: context }).catch(() => {
    // Service worker may not be active yet — safe to ignore
  });
}

// ── SPA navigation listeners ──────────────────────────────────────────────────

// Turbo Drive (GitHub's primary SPA framework)
document.addEventListener('turbo:load', () => detectAndSend(window.location.href));
document.addEventListener('turbo:render', () => detectAndSend(window.location.href));

// Fallback: popstate (browser back/forward)
window.addEventListener('popstate', () => detectAndSend(window.location.href));

// Monkey-patch pushState / replaceState to catch programmatic navigation
(function patchHistory(): void {
  const patchMethod = (method: 'pushState' | 'replaceState'): void => {
    const original = history[method].bind(history) as (...args: Parameters<typeof history[typeof method]>) => void;
    history[method] = function (...args: Parameters<typeof history[typeof method]>): void {
      original(...args);
      detectAndSend(window.location.href);
    };
  };
  patchMethod('pushState');
  patchMethod('replaceState');
})();

// Listen for GET_REPO_CONTEXT requests from the panel
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'GET_REPO_CONTEXT') {
    const context = parseGitHubUrl(window.location.href);
    sendResponse({ type: 'REPO_CONTEXT_RESPONSE', payload: context });
  }
  return true;
});

// Initial detection on script load
detectAndSend();
