import { useEffect, useState } from 'react';
import { GitBranch, Layers, Network, Settings, AlertCircle } from 'lucide-react';
import type { RepoContext } from '../lib/messages';
import ImpactTab from './tabs/ImpactTab';
import DependencyMapTab from './tabs/DependencyMapTab';

type TabId = 'impact' | 'deps';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('impact');
  const [repoContext, setRepoContext] = useState<RepoContext | null>(null);

  // ── Pull current context on mount ────────────────────────────────────────
  useEffect(() => {
    chrome.runtime.sendMessage({ type: 'GET_REPO_CONTEXT' }).then((response) => {
      if (response?.payload) {
        setRepoContext(response.payload as RepoContext);
      }
    }).catch(() => {});

    // Listen for context updates pushed from the background
    const listener = (message: { type: string; payload?: RepoContext }) => {
      if (message.type === 'REPO_CONTEXT' && message.payload) {
        setRepoContext(message.payload);
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const isOnGitHub = repoContext != null;

  return (
    <div className="flex flex-col h-screen bg-[#0d1117] text-[#e6edf3] overflow-hidden">
      {/* ── Header ── */}
      <header className="flex-shrink-0 border-b border-[#30363d] px-3 py-2.5">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Network className="w-4 h-4 text-[#58a6ff]" />
            <span className="text-sm font-semibold text-[#58a6ff]">RepoLens</span>
          </div>
          <a
            href="/src/options/index.html"
            target="_blank"
            rel="noreferrer"
            className="text-[#8b949e] hover:text-[#e6edf3] transition-colors"
            title="Options"
          >
            <Settings className="w-3.5 h-3.5" />
          </a>
        </div>

        {isOnGitHub ? (
          <div className="space-y-0.5">
            <p className="text-xs font-medium text-[#e6edf3] truncate">
              {repoContext.owner}
              <span className="text-[#8b949e]">/</span>
              {repoContext.repo}
            </p>
            {repoContext.path && (
              <div className="flex items-center gap-1">
                <GitBranch className="w-3 h-3 text-[#8b949e]" />
                <span className="text-[10px] text-[#8b949e] truncate">{repoContext.path || '/'}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-[#8b949e]">
            <AlertCircle className="w-3.5 h-3.5" />
            <span className="text-xs">Navigate to a GitHub repository</span>
          </div>
        )}
      </header>

      {/* ── Tab bar ── */}
      <nav className="flex-shrink-0 flex border-b border-[#30363d]">
        <TabButton
          id="impact"
          active={activeTab === 'impact'}
          onClick={() => setActiveTab('impact')}
          icon={<Layers className="w-3.5 h-3.5" />}
          label="Impact Analysis"
        />
        <TabButton
          id="deps"
          active={activeTab === 'deps'}
          onClick={() => setActiveTab('deps')}
          icon={<Network className="w-3.5 h-3.5" />}
          label="Dependency Map"
        />
      </nav>

      {/* ── Tab content ── */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'impact' && (
          <ImpactTab repoContext={repoContext} />
        )}
        {activeTab === 'deps' && (
          <DependencyMapTab repoContext={repoContext} />
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
}: {
  id: TabId;
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px',
        active
          ? 'text-[#58a6ff] border-[#58a6ff]'
          : 'text-[#8b949e] border-transparent hover:text-[#e6edf3]',
      ].join(' ')}
    >
      {icon}
      {label}
    </button>
  );
}
