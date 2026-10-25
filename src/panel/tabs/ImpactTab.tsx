import { Search, Zap } from 'lucide-react';
import type { RepoContext } from '../../lib/messages';

interface Props {
  repoContext: RepoContext | null;
}

export default function ImpactTab({ repoContext }: Props) {
  if (!repoContext) {
    return (
      <EmptyState
        icon={<Zap className="w-8 h-8 text-[#30363d]" />}
        title="No repository detected"
        description="Navigate to a public GitHub repository to begin analysis."
      />
    );
  }

  return (
    <div className="flex flex-col h-full p-3 gap-3 overflow-y-auto">
      {/* ── Change request input ── */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[#8b949e] uppercase tracking-wider">
          Describe your change
        </label>
        <div className="relative">
          <textarea
            className="w-full bg-[#161b22] border border-[#30363d] rounded-md px-3 py-2 text-sm text-[#e6edf3] placeholder-[#484f58] resize-none focus:outline-none focus:border-[#58a6ff] transition-colors"
            rows={3}
            placeholder="e.g. Add role-based access control"
          />
        </div>
        <button className="w-full flex items-center justify-center gap-2 bg-[#238636] hover:bg-[#2ea043] text-white text-sm font-medium py-2 rounded-md transition-colors">
          <Search className="w-4 h-4" />
          Analyze Impact
        </button>
      </div>

      {/* ── Placeholder state ── */}
      <EmptyState
        icon={<Zap className="w-8 h-8 text-[#30363d]" />}
        title="Ready to analyze"
        description={`Describe a change for ${repoContext.owner}/${repoContext.repo} and click Analyze.`}
      />
    </div>
  );
}

function EmptyState({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
      {icon}
      <p className="text-sm font-medium text-[#8b949e]">{title}</p>
      <p className="text-xs text-[#484f58] leading-relaxed">{description}</p>
    </div>
  );
}
