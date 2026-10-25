import { useState } from 'react';
import { ExternalLink, ChevronDown, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { AffectedFile, ImpactLevel } from '../../core/types';

const LEVEL_STYLES: Record<ImpactLevel, { badge: string; dot: string; border: string }> = {
  high: {
    badge: 'bg-[#f85149]/10 text-[#f85149] border border-[#f85149]/25',
    dot: 'bg-[#f85149]',
    border: 'border-l-[#f85149]',
  },
  medium: {
    badge: 'bg-[#d29922]/10 text-[#d29922] border border-[#d29922]/25',
    dot: 'bg-[#d29922]',
    border: 'border-l-[#d29922]',
  },
  low: {
    badge: 'bg-[#3fb950]/10 text-[#3fb950] border border-[#3fb950]/25',
    dot: 'bg-[#3fb950]',
    border: 'border-l-[#3fb950]',
  },
};

interface Props {
  file: AffectedFile;
  owner?: string;
  repo?: string;
  branch?: string;
}

export default function FileImpactCard({ file, owner, repo, branch = 'main' }: Props) {
  const [expanded, setExpanded] = useState(false);
  const styles = LEVEL_STYLES[file.impact];

  const parts = file.path.split('/');
  const filename = parts.pop() ?? file.path;
  const dir = parts.length > 0 ? parts.join('/') + '/' : '';

  const githubUrl =
    owner && repo
      ? `https://github.com/${owner}/${repo}/blob/${branch}/${file.path}`
      : undefined;

  return (
    <div
      className={clsx(
        'rounded-md overflow-hidden border border-[#30363d] border-l-2 bg-[#161b22] transition-all',
        styles.border,
      )}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[#1c2128] transition-colors"
      >
        <div className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0 mt-px', styles.dot)} />
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-[#8b949e]">{dir}</span>
          <span className="text-xs font-mono font-semibold text-[#e6edf3]">{filename}</span>
        </div>

        {githubUrl && (
          <a
            href={githubUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex-shrink-0 p-0.5 text-[#8b949e] hover:text-[#58a6ff] transition-colors"
            title="Open on GitHub"
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        )}

        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-[#8b949e] flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-[#8b949e] flex-shrink-0" />
        )}
      </button>

      {/* Expandable body */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2.5 border-t border-[#30363d] pt-2.5">
          <div>
            <p className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider mb-1">
              Why this file
            </p>
            <p className="text-xs text-[#c9d1d9] leading-relaxed">{file.reason}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider mb-1">
              Recommended change
            </p>
            <p className="text-xs text-[#c9d1d9] leading-relaxed">{file.recommendedChange}</p>
          </div>
        </div>
      )}
    </div>
  );
}
