import { useEffect, useState, useMemo } from 'react';
import {
  GitBranch,
  Layers,
  Network,
  Settings,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import clsx from 'clsx';
import type { RepoContext } from '../lib/messages';
import type { DependencyGraph, ImpactResponse, RepoMeta } from '../core/types';
import { MOCK_GRAPH, MOCK_REPO } from '../demo/mockGraph';
import { DEMO_CHANGE_REQUEST } from '../demo/mockImpact';
import ImpactTab from './tabs/ImpactTab';
import DependencyMapTab from './tabs/DependencyMapTab';

type TabId = 'impact' | 'deps';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('impact');
  const [repoContext, setRepoContext] = useState<RepoContext | null>(null);
  const [isDemoMode, setIsDemoMode] = useState<boolean>(true);
  const [changeRequest, setChangeRequest] = useState<string>(DEMO_CHANGE_REQUEST);
  const [impactResult, setImpactResult] = useState<ImpactResponse | null>(null);

  // Load storage settings on mount
  useEffect(() => {
    chrome.storage?.local?.get(['demoMode'], (res) => {
      if (typeof res?.demoMode === 'boolean') {
        setIsDemoMode(res.demoMode);
      }
    });

    // Request active tab context
    chrome.runtime?.sendMessage?.({ type: 'GET_REPO_CONTEXT' }).then((response) => {
      if (response?.payload) {
        setRepoContext(response.payload as RepoContext);
        // If real repo detected, default demo mode to false unless saved
        chrome.storage?.local?.get(['demoMode'], (res) => {
          if (typeof res?.demoMode !== 'boolean') {
            setIsDemoMode(false);
          }
        });
      }
    }).catch(() => {});

    const listener = (message: { type: string; payload?: RepoContext }) => {
      if (message.type === 'REPO_CONTEXT' && message.payload) {
        setRepoContext(message.payload);
      }
    };
    chrome.runtime?.onMessage?.addListener(listener);
    return () => chrome.runtime?.onMessage?.removeListener(listener);
  }, []);

  const currentRepo: RepoMeta = useMemo(() => {
    if (isDemoMode || !repoContext) {
      return MOCK_REPO;
    }
    return {
      owner: repoContext.owner,
      repo: repoContext.repo,
      branch: 'main',
      sha: 'head',
    };
  }, [isDemoMode, repoContext]);

  const activeGraph: DependencyGraph = useMemo(() => {
    if (isDemoMode || !repoContext) {
      return MOCK_GRAPH;
    }
    // In Phase 2, real graph fetching is wired in Phase 3. Fallback to mock graph.
    return MOCK_GRAPH;
  }, [isDemoMode, repoContext]);

  const toggleDemoMode = () => {
    const nextVal = !isDemoMode;
    setIsDemoMode(nextVal);
    chrome.storage?.local?.set({ demoMode: nextVal });
  };

  return (
    <div className="flex flex-col h-screen bg-[#0d1117] text-[#e6edf3] overflow-hidden select-none">
      {/* ── Header ── */}
      <header className="flex-shrink-0 border-b border-[#30363d] px-3 py-2 bg-[#0d1117]">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Network className="w-4 h-4 text-[#58a6ff]" />
            <span className="text-sm font-semibold text-[#58a6ff]">RepoLens</span>
            <span className="text-[10px] bg-[#30363d] text-[#8b949e] px-1.5 py-0.2 rounded font-mono">
              MVP
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleDemoMode}
              className={clsx(
                'flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-colors border',
                isDemoMode
                  ? 'bg-[#58a6ff]/15 border-[#58a6ff]/40 text-[#58a6ff]'
                  : 'bg-[#21262d] border-[#30363d] text-[#8b949e] hover:text-[#e6edf3]',
              )}
              title="Toggle Demo Mode with mock data"
            >
              <Sparkles className="w-3 h-3" />
              <span>Demo</span>
            </button>

            <a
              href="/src/options/index.html"
              target="_blank"
              rel="noreferrer"
              className="text-[#8b949e] hover:text-[#e6edf3] transition-colors p-0.5"
              title="Settings & Options"
            >
              <Settings className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>

        {/* Repo Context Pill */}
        <div className="flex items-center justify-between bg-[#161b22] border border-[#30363d] rounded px-2 py-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <GitBranch className="w-3 h-3 text-[#58a6ff] flex-shrink-0" />
            <span className="text-xs font-mono font-medium text-[#e6edf3] truncate">
              {currentRepo.owner}/{currentRepo.repo}
            </span>
            <span className="text-[10px] font-mono text-[#8b949e] bg-[#0d1117] px-1 rounded border border-[#30363d]">
              {currentRepo.branch}
            </span>
          </div>

          {impactResult ? (
            <span className="text-[10px] text-[#3fb950] font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3fb950]" />
              Analyzed
            </span>
          ) : (
            <span className="text-[10px] text-[#8b949e] flex items-center gap-1">
              <RefreshCw className="w-2.5 h-2.5" />
              Ready
            </span>
          )}
        </div>
      </header>

      {/* ── Tab navigation ── */}
      <nav className="flex-shrink-0 flex border-b border-[#30363d] bg-[#0d1117]">
        <TabButton
          active={activeTab === 'impact'}
          onClick={() => setActiveTab('impact')}
          icon={<Layers className="w-3.5 h-3.5" />}
          label="Impact Analysis"
          badge={impactResult ? `${impactResult.affectedFiles.length}` : undefined}
        />
        <TabButton
          active={activeTab === 'deps'}
          onClick={() => setActiveTab('deps')}
          icon={<Network className="w-3.5 h-3.5" />}
          label="Dependency Map"
          badge={`${Object.keys(activeGraph).length}`}
        />
      </nav>

      {/* ── Tab Views ── */}
      <main className="flex-1 overflow-hidden relative">
        {activeTab === 'impact' && (
          <ImpactTab
            repoContext={repoContext}
            graph={activeGraph}
            currentRepo={currentRepo}
            isDemoMode={isDemoMode}
            impactResult={impactResult}
            onImpactResult={setImpactResult}
            onClearResult={() => setImpactResult(null)}
            changeRequest={changeRequest}
            onChangeRequest={setChangeRequest}
          />
        )}
        {activeTab === 'deps' && (
          <DependencyMapTab
            repoContext={repoContext}
            graph={activeGraph}
            currentRepo={currentRepo}
            isDemoMode={isDemoMode}
            impactResult={impactResult}
          />
        )}
      </main>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px flex-1 justify-center',
        active
          ? 'text-[#58a6ff] border-[#58a6ff] bg-[#161b22]/50'
          : 'text-[#8b949e] border-transparent hover:text-[#e6edf3] hover:bg-[#161b22]/20',
      )}
    >
      {icon}
      <span>{label}</span>
      {badge && (
        <span
          className={clsx(
            'text-[9px] font-mono px-1.5 py-0.2 rounded-full border',
            active
              ? 'bg-[#58a6ff]/15 border-[#58a6ff]/30 text-[#58a6ff]'
              : 'bg-[#21262d] border-[#30363d] text-[#8b949e]',
          )}
        >
          {badge}
        </span>
      )}
    </button>
  );
}
