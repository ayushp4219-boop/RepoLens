import { useState, useRef } from 'react';
import {
  Search,
  Zap,
  Copy,
  Check,
  AlertTriangle,
  TestTube,
  GitMerge,
  Shield,
  ArrowLeft,
  Sparkles,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import clsx from 'clsx';
import type { ImpactLevel, ImpactResponse, DependencyGraph, RepoMeta } from '../../core/types';
import type { RepoContext } from '../../lib/messages';
import { MOCK_IMPACT, DEMO_CHANGE_REQUEST } from '../../demo/mockImpact';
import { generateImpactMarkdown } from '../../core/graphUtils';
import { createLocalMockImpact, rankRelevantFiles } from '../../core/relevance';
import { sanitizeImpactResponse } from '../../core/impactValidation';
import FileImpactCard from '../components/FileImpactCard';

interface Props {
  repoContext: RepoContext | null;
  graph: DependencyGraph;
  currentRepo: RepoMeta;
  isDemoMode: boolean;
  impactResult: ImpactResponse | null;
  onImpactResult: (result: ImpactResponse) => void;
  onClearResult: () => void;
  changeRequest: string;
  onChangeRequest: (value: string) => void;
  repositoryReady: boolean;
}

type ViewState = 'input' | 'loading' | 'results';

const LOADING_STEPS = [
  'Scoring file relevance for change…',
  'Computing dependency traversal…',
  'Preparing a graph-grounded impact report…',
];

const IMPACT_LABELS: Record<ImpactLevel, { label: string; color: string; bg: string }> = {
  high: { label: 'High Impact', color: 'text-[#f85149]', bg: 'bg-[#f85149]/10 border-[#f85149]/20' },
  medium: { label: 'Medium Impact', color: 'text-[#d29922]', bg: 'bg-[#d29922]/10 border-[#d29922]/20' },
  low: { label: 'Low Impact', color: 'text-[#3fb950]', bg: 'bg-[#3fb950]/10 border-[#3fb950]/20' },
};

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function getProxyUrl(): Promise<string> {
  return new Promise((resolve) => chrome.storage.local.get(['proxyUrl'], (result) => resolve((result.proxyUrl as string) || '')));
}

async function requestProxyImpact(changeRequest: string, graph: DependencyGraph): Promise<ImpactResponse | null> {
  const proxyUrl = await getProxyUrl();
  if (!proxyUrl) return null;
  let origin: string;
  try {
    const endpoint = new URL(proxyUrl);
    if (endpoint.protocol !== 'https:') return null;
    origin = `${endpoint.origin}/*`;
  } catch {
    return null;
  }

  const granted = await new Promise<boolean>((resolve) => {
    chrome.permissions.contains({ origins: [origin] }, (hasPermission) => {
      if (hasPermission) return resolve(true);
      chrome.permissions.request({ origins: [origin] }, resolve);
    });
  });
  if (!granted) return null;

  const files = rankRelevantFiles(changeRequest, graph, 10).map(({ path }) => {
    const node = graph[path];
    return { path, summary: node.summary, imports: node.imports, dependents: node.dependents };
  });
  if (!files.length) return null;
  try {
    const response = await fetch(proxyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ changeRequest, files }),
    });
    if (!response.ok) return null;
    return sanitizeImpactResponse(await response.json(), graph);
  } catch {
    return null;
  }
}

export default function ImpactTab({
  repoContext,
  graph,
  currentRepo,
  isDemoMode,
  impactResult,
  onImpactResult,
  onClearResult,
  changeRequest,
  onChangeRequest,
  repositoryReady,
}: Props) {
  const [view, setView] = useState<ViewState>(impactResult ? 'results' : 'input');
  const [loadingStep, setLoadingStep] = useState(0);
  const [copied, setCopied] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    high: true,
    medium: true,
    low: true,
    depPaths: true,
    tests: true,
    risks: true,
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const toggleSection = (key: string) =>
    setExpandedSections((s) => ({ ...s, [key]: !s[key] }));

  const handleAnalyze = async () => {
    if (!changeRequest.trim()) {
      textareaRef.current?.focus();
      return;
    }

    if (!isDemoMode && Object.keys(graph).length === 0) return;

    const proxyResult = !isDemoMode ? requestProxyImpact(changeRequest, graph) : null;
    setView('loading');
    setLoadingStep(0);

    for (let i = 0; i < LOADING_STEPS.length; i++) {
      setLoadingStep(i);
      await sleep(250 + Math.random() * 200);
    }

    const result = isDemoMode
      ? { ...MOCK_IMPACT, source: 'demo' as const }
      : await proxyResult ?? createLocalMockImpact(changeRequest, graph);
    onImpactResult(result);
    setView('results');
  };

  const handleCopy = async () => {
    if (!impactResult) return;
    const md = generateImpactMarkdown(changeRequest, impactResult, currentRepo);
    await navigator.clipboard.writeText(md);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (view === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 px-6 text-center">
        <div className="w-8 h-8 border-2 border-[#58a6ff] border-t-transparent rounded-full animate-spin" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-[#e6edf3]">Analyzing Impact…</p>
          <p className="text-xs text-[#8b949e]">{LOADING_STEPS[loadingStep]}</p>
        </div>
        <div className="flex gap-1">
          {LOADING_STEPS.map((_, i) => (
            <div
              key={i}
              className={clsx(
                'h-1 rounded-full transition-all duration-300',
                i <= loadingStep ? 'bg-[#58a6ff] w-4' : 'bg-[#30363d] w-2',
              )}
            />
          ))}
        </div>
        {isDemoMode && (
          <p className="text-[10px] text-[#8b949e] bg-[#161b22] px-2.5 py-1 rounded-full border border-[#30363d]">
            Demo Mode — offline mock analysis
          </p>
        )}
      </div>
    );
  }

  if (view === 'results' && impactResult) {
    return (
      <ResultsView
        result={impactResult}
        changeRequest={changeRequest}
        currentRepo={currentRepo}
        repoContext={repoContext}
        isDemoMode={isDemoMode}
        copied={copied}
        expandedSections={expandedSections}
        onToggleSection={toggleSection}
        onCopy={handleCopy}
        onBack={() => {
          onClearResult();
          setView('input');
        }}
      />
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-3 space-y-3">
        {isDemoMode && (
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-[#58a6ff]" />
                <span className="text-xs font-semibold text-[#58a6ff]">Demo Mode Active</span>
              </div>
              <span className="text-[10px] text-[#8b949e] bg-[#0d1117] px-2 py-0.5 rounded border border-[#30363d]">
                19 mock files
              </span>
            </div>
            <p className="text-xs text-[#8b949e] leading-relaxed">
              Explore dependencies and change impact on a realistic Express + TypeScript codebase with auth, models, and routes.
            </p>
            <button
              type="button"
              onClick={() => onChangeRequest(DEMO_CHANGE_REQUEST)}
              className="text-xs text-[#58a6ff] hover:text-[#79c0ff] transition-colors underline underline-offset-2 text-left"
            >
              Preset: &ldquo;{DEMO_CHANGE_REQUEST}&rdquo;
            </button>
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider">
            Describe your change
          </label>
          <textarea
            ref={textareaRef}
            value={changeRequest}
            onChange={(e) => onChangeRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleAnalyze();
              }
            }}
            rows={3}
            placeholder="e.g. Add role-based access control"
            className="w-full bg-[#161b22] border border-[#30363d] rounded-md px-3 py-2 text-sm text-[#e6edf3] placeholder-[#484f58] resize-none focus:outline-none focus:border-[#58a6ff] transition-colors"
          />
          <p className="text-[10px] text-[#484f58]">Press ⌘↵ or Ctrl+↵ to analyze</p>
        </div>

        <button
          type="button"
          onClick={handleAnalyze}
          disabled={!changeRequest.trim() || (!isDemoMode && !repositoryReady)}
          className="w-full flex items-center justify-center gap-2 bg-[#238636] hover:bg-[#2ea043] disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium py-2 rounded-md transition-colors"
        >
          <Search className="w-4 h-4" />
          {isDemoMode ? 'Analyze Impact' : repositoryReady ? 'Analyze Local Impact' : 'Waiting for repository'}
        </button>

        {!isDemoMode && repositoryReady && (
          <p className="text-[10px] text-[#8b949e] text-center leading-relaxed">
            Uses deterministic local scoring until the optional AI proxy is configured in Phase 7.
          </p>
        )}

        {!repoContext && !isDemoMode && (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <Zap className="w-8 h-8 text-[#30363d]" />
            <p className="text-xs text-[#484f58] text-center leading-relaxed">
              Navigate to a public GitHub repository or toggle Demo Mode in Settings.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

interface ResultsViewProps {
  result: ImpactResponse;
  changeRequest: string;
  currentRepo: RepoMeta;
  repoContext: RepoContext | null;
  isDemoMode: boolean;
  copied: boolean;
  expandedSections: Record<string, boolean>;
  onToggleSection: (key: string) => void;
  onCopy: () => void;
  onBack: () => void;
}

function ResultsView({
  result,
  changeRequest,
  currentRepo,
  repoContext,
  isDemoMode,
  copied,
  expandedSections,
  onToggleSection,
  onCopy,
  onBack,
}: ResultsViewProps) {
  const byImpact = {
    high: result.affectedFiles.filter((f) => f.impact === 'high'),
    medium: result.affectedFiles.filter((f) => f.impact === 'medium'),
    low: result.affectedFiles.filter((f) => f.impact === 'low'),
  };

  const owner = repoContext?.owner ?? currentRepo.owner;
  const repo = repoContext?.repo ?? currentRepo.repo;
  const branch = currentRepo.sha || currentRepo.branch;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="sticky top-0 z-10 flex items-center justify-between px-3 py-2 bg-[#0d1117] border-b border-[#30363d]">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-[#8b949e] hover:text-[#e6edf3] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Edit request
        </button>

        <div className="flex items-center gap-2">
          <AnalysisBadge source={result.source ?? (isDemoMode ? 'demo' : 'local')} />
          <button
            type="button"
            onClick={onCopy}
            className="flex items-center gap-1.5 text-xs bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] px-2 py-1 rounded text-[#e6edf3] transition-colors"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-[#3fb950]" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied!' : 'Copy Plan'}
          </button>
        </div>
      </div>

      <div className="p-3 space-y-3">
        <div className="bg-[#161b22] border border-[#30363d] rounded-md px-3 py-2">
          <p className="text-[10px] text-[#8b949e] uppercase tracking-wider mb-0.5">Change request</p>
          <p className="text-xs text-[#e6edf3] leading-relaxed">&ldquo;{changeRequest}&rdquo;</p>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] rounded-md p-3 space-y-2">
          <p className="text-xs text-[#c9d1d9] leading-relaxed">{result.summary}</p>
          <div className="flex items-center gap-2 pt-1 border-t border-[#21262d]">
            <div className="flex-1 h-1.5 bg-[#30363d] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#58a6ff] rounded-full transition-all"
                style={{ width: `${Math.round(result.confidence * 100)}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-[#58a6ff] tabular-nums">
              {Math.round(result.confidence * 100)}%
            </span>
            <span className="text-xs text-[#8b949e]">confidence</span>
          </div>
        </div>

        {(['high', 'medium', 'low'] as ImpactLevel[]).map((level) => {
          const files = byImpact[level];
          if (files.length === 0) return null;
          const { label, color, bg } = IMPACT_LABELS[level];
          const isOpen = expandedSections[level];

          return (
            <div key={level}>
              <button
                type="button"
                onClick={() => onToggleSection(level)}
                className="w-full flex items-center justify-between mb-2 group"
              >
                <div className="flex items-center gap-2">
                  <span className={clsx('text-xs font-semibold', color)}>{label}</span>
                  <span className={clsx('text-[10px] font-medium px-1.5 py-0.5 rounded border', bg, color)}>
                    {files.length}
                  </span>
                </div>
                {isOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 text-[#8b949e]" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-[#8b949e]" />
                )}
              </button>

              {isOpen && (
                <div className="space-y-1.5">
                  {files.map((file) => (
                    <FileImpactCard
                      key={file.path}
                      file={file}
                      owner={owner}
                      repo={repo}
                      branch={branch}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {result.dependencyPaths.length > 0 && (
          <Section
            icon={<GitMerge className="w-3.5 h-3.5" />}
            title={`Dependency Paths (${result.dependencyPaths.length})`}
            isOpen={expandedSections.depPaths}
            onToggle={() => onToggleSection('depPaths')}
          >
            <div className="space-y-2">
              {result.dependencyPaths.map((dp, i) => (
                <div key={i} className="bg-[#161b22] border border-[#30363d] rounded-md p-2.5 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-1">
                    {dp.path.map((p, j) => (
                      <span key={p} className="flex items-center gap-1">
                        <span className="text-[10px] font-mono bg-[#0d1117] text-[#58a6ff] px-1.5 py-0.5 rounded border border-[#30363d]">
                          {p.split('/').pop()}
                        </span>
                        {j < dp.path.length - 1 && (
                          <span className="text-[10px] text-[#484f58]">→</span>
                        )}
                      </span>
                    ))}
                  </div>
                  <p className="text-[10px] text-[#8b949e] leading-relaxed">{dp.reason}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {result.testsToUpdate.length > 0 && (
          <Section
            icon={<TestTube className="w-3.5 h-3.5" />}
            title={`Tests to Update (${result.testsToUpdate.length})`}
            isOpen={expandedSections.tests}
            onToggle={() => onToggleSection('tests')}
          >
            <div className="space-y-1 bg-[#161b22] border border-[#30363d] rounded-md p-2.5">
              {result.testsToUpdate.map((t) => {
                const githubUrl = `https://github.com/${owner}/${repo}/blob/${branch}/${t}`;
                return (
                  <a
                    key={t}
                    href={githubUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 text-[11px] font-mono text-[#8b949e] hover:text-[#58a6ff] transition-colors py-0.5"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-[#d29922] flex-shrink-0" />
                    {t}
                  </a>
                );
              })}
            </div>
          </Section>
        )}

        {result.risks.length > 0 && (
          <Section
            icon={<AlertTriangle className="w-3.5 h-3.5 text-[#d29922]" />}
            title={`Risks & Breaking Changes (${result.risks.length})`}
            isOpen={expandedSections.risks}
            onToggle={() => onToggleSection('risks')}
          >
            <div className="space-y-1.5">
              {result.risks.map((risk, i) => (
                <div
                  key={i}
                  className="flex gap-2 text-xs text-[#c9d1d9] bg-[#161b22] border border-[#d29922]/30 rounded-md px-2.5 py-2 leading-relaxed"
                >
                  <Shield className="w-3.5 h-3.5 text-[#d29922] flex-shrink-0 mt-0.5" />
                  <span>{risk}</span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

function AnalysisBadge({ source }: { source: NonNullable<ImpactResponse['source']> }) {
  const labels = {
    demo: ['Demo Mode', 'bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/20'],
    local: ['Local mock analysis', 'bg-[#d29922]/10 text-[#d29922] border-[#d29922]/20'],
    fallback: ['AI fallback', 'bg-[#d29922]/10 text-[#d29922] border-[#d29922]/20'],
    ai: ['AI analysis', 'bg-[#3fb950]/10 text-[#3fb950] border-[#3fb950]/20'],
  } as const;
  const [label, classes] = labels[source];
  return <span className={`text-[10px] border px-2 py-0.5 rounded-full ${classes}`}>{label}</span>;
}

function Section({
  icon,
  title,
  isOpen,
  onToggle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between mb-2 group"
      >
        <div className="flex items-center gap-2 text-[#8b949e] group-hover:text-[#e6edf3] transition-colors">
          {icon}
          <span className="text-xs font-semibold">{title}</span>
        </div>
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 text-[#8b949e]" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-[#8b949e]" />
        )}
      </button>
      {isOpen && children}
    </div>
  );
}
