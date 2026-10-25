import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { ExternalLink, FileCode } from 'lucide-react';
import clsx from 'clsx';

export type ImpactHighlight = 'direct' | 'indirect' | 'none';

export interface FileNodeData {
  path: string;
  filename: string;
  dir: string;
  impactType: ImpactHighlight;
  summary: string;
  githubUrl?: string;
  onOpenGithub?: (url: string) => void;
}

const HIGHLIGHT_STYLES: Record<
  ImpactHighlight,
  {
    border: string;
    bg: string;
    badge: string;
    badgeText: string;
    glow: string;
    textColor: string;
  }
> = {
  direct: {
    border: 'border-[#f85149]',
    bg: 'bg-[#2b1011]',
    badge: 'bg-[#f85149] text-white',
    badgeText: 'Direct Impact',
    glow: 'shadow-[0_0_12px_rgba(248,81,73,0.35)]',
    textColor: 'text-[#ff7b72]',
  },
  indirect: {
    border: 'border-[#d29922]',
    bg: 'bg-[#281e09]',
    badge: 'bg-[#d29922] text-[#0d1117]',
    badgeText: 'Indirect Impact',
    glow: 'shadow-[0_0_12px_rgba(210,153,34,0.35)]',
    textColor: 'text-[#e3b341]',
  },
  none: {
    border: 'border-[#30363d]',
    bg: 'bg-[#161b22]',
    badge: '',
    badgeText: '',
    glow: '',
    textColor: 'text-[#c9d1d9]',
  },
};

function FileNode({ data }: NodeProps<FileNodeData>) {
  const styles = HIGHLIGHT_STYLES[data.impactType];

  return (
    <div
      className={clsx(
        'group relative w-[180px] rounded-md border text-left p-2 transition-all cursor-pointer select-none',
        styles.border,
        styles.bg,
        styles.glow,
      )}
      onClick={() => {
        if (data.githubUrl && data.onOpenGithub) {
          data.onOpenGithub(data.githubUrl);
        }
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-[#58a6ff] !w-2 !h-2 !border-none"
      />

      <div className="flex items-start justify-between gap-1 mb-1">
        <div className="flex items-center gap-1 min-w-0">
          <FileCode className={clsx('w-3.5 h-3.5 flex-shrink-0', styles.textColor)} />
          <span className="text-[10px] text-[#8b949e] font-mono truncate">{data.dir || './'}</span>
        </div>
        {data.githubUrl && (
          <ExternalLink className="w-2.5 h-2.5 text-[#8b949e] group-hover:text-[#58a6ff] flex-shrink-0" />
        )}
      </div>

      <div className="font-mono text-xs font-semibold text-[#e6edf3] truncate mb-1">
        {data.filename}
      </div>

      {data.impactType !== 'none' && (
        <span
          className={clsx(
            'inline-block px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider',
            styles.badge,
          )}
        >
          {styles.badgeText}
        </span>
      )}

      {data.impactType === 'none' && data.summary && (
        <p className="text-[9px] text-[#8b949e] line-clamp-1">
          {data.summary}
        </p>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-[#58a6ff] !w-2 !h-2 !border-none"
      />
    </div>
  );
}

export default memo(FileNode);
