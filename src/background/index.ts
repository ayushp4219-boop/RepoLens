/**
 * Background Service Worker
 * Responsibilities:
 *  - Receive REPO_CONTEXT from content script
 *  - Store the active context in memory
 *  - Open the side panel when the toolbar icon is clicked
 *  - Relay context to the side panel on request
 */

import type { RepoContext } from '../lib/messages';
import { getCachedAnalysis, getSettings, setCachedAnalysis } from '../lib/storage';
import { fetchRepository } from './github';

// In-memory store (cleared on service worker termination; panel re-queries on load)
let activeContext: RepoContext | null = null;
const tabContextMap = new Map<number, RepoContext>();

// ── Side Panel setup ──────────────────────────────────────────────────────────

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);

chrome.action.onClicked.addListener((tab) => {
  if (tab.id == null) return;
  chrome.sidePanel.open({ tabId: tab.id }).catch(console.error);
});

// ── Message handling ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  switch (message.type) {
    case 'REPO_CONTEXT': {
      const ctx = message.payload as RepoContext;
      activeContext = ctx;
      if (tabId != null) {
        tabContextMap.set(tabId, ctx);
      }
      // Broadcast to any open side panels
      chrome.runtime.sendMessage({ type: 'REPO_CONTEXT', payload: ctx }).catch(() => {
        // Panel may not be open — safe to ignore
      });
      sendResponse({ ok: true });
      break;
    }

    case 'GET_REPO_CONTEXT': {
      // Panel is asking for the current context
      // Try to get from the active tab first
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const tab = tabs[0];
        const ctx = tab?.id != null ? tabContextMap.get(tab.id) ?? activeContext : activeContext;
        sendResponse({ type: 'REPO_CONTEXT_RESPONSE', payload: ctx ?? null });
      });
      return true; // keep channel open for async sendResponse
    }

    case 'FETCH_REPOSITORY': {
      const { context, scope = 'all' } = message.payload;
      getSettings().then(async ({ githubToken }) => {
        const result = await fetchRepository(context.owner, context.repo, githubToken, scope, (progress) => {
          chrome.runtime.sendMessage({ type: 'REPOSITORY_PROGRESS', payload: progress }).catch(() => {});
        });
        if (result.snapshot) {
          const key = `${context.owner}/${context.repo}@${result.snapshot.meta.sha}`;
          await setCachedAnalysis(key, result.snapshot);
        }
        sendResponse({ type: 'REPOSITORY_FETCH_RESPONSE', payload: result });
      });
      return true;
    }

    case 'GET_REPOSITORY_SNAPSHOT': {
      const { owner, repo, sha } = message.payload;
      getCachedAnalysis(`${owner}/${repo}@${sha}`).then((snapshot) => {
        sendResponse({ type: 'REPOSITORY_SNAPSHOT_RESPONSE', payload: snapshot ?? null });
      });
      return true;
    }

    case 'PING':
      sendResponse({ type: 'PONG' });
      break;
  }

  return true;
});

// ── Tab cleanup ───────────────────────────────────────────────────────────────

chrome.tabs.onRemoved.addListener((tabId) => {
  tabContextMap.delete(tabId);
});

// Keep service worker alive a bit during dev
// Chrome terminates idle service workers after ~30 s
setInterval(() => {
  // no-op heartbeat
}, 20_000);
