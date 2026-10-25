import { Network } from 'lucide-react';
import type { RepoContext } from '../../lib/messages';

interface Props {
  repoContext: RepoContext | null;
}

export default function DependencyMapTab({ repoContext }: Props) {
  if (!repoContext) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <Network className="w-8 h-8 text-[#30363d]" />
        <p className="text-sm font-medium text-[#8b949e]">No repository detected</p>
        <p className="text-xs text-[#484f58] leading-relaxed">
          Navigate to a public GitHub repository to see the dependency map.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
      <Network className="w-8 h-8 text-[#58a6ff] opacity-40" />
      <p className="text-sm font-medium text-[#8b949e]">Dependency map</p>
      <p className="text-xs text-[#484f58] leading-relaxed">
        Graph for <span className="text-[#58a6ff]">{repoContext.owner}/{repoContext.repo}</span> will appear here after analysis.
      </p>
    </div>
  );
}
