import { useMemo, useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { Network, AlertCircle, Info, Search, X } from 'lucide-react';
import type { DependencyGraph, ImpactResponse, RepoMeta } from '../../core/types';
import type { RepoContext } from '../../lib/messages';
import { computeIndirectImpact } from '../../core/graphUtils';
import FileNode, { type FileNodeData, type ImpactHighlight } from '../components/FileNode';

const nodeTypes = {
  fileNode: FileNode,
};

interface Props {
  repoContext: RepoContext | null;
  graph: DependencyGraph;
  currentRepo: RepoMeta;
  isDemoMode: boolean;
  impactResult: ImpactResponse | null;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 80;

function getLayoutedElements(nodes: Node<FileNodeData>[], edges: Edge[]) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: 'TB', nodesep: 35, ranksep: 55 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

export default function DependencyMapTab({
  repoContext,
  graph,
  currentRepo,
  isDemoMode,
  impactResult,
}: Props) {
  const directImpactPaths = useMemo(() => {
    if (!impactResult) return new Set<string>();
    return new Set(impactResult.affectedFiles.map((f) => f.path));
  }, [impactResult]);

  const indirectImpactPaths = useMemo(() => {
    if (!impactResult || directImpactPaths.size === 0) return new Set<string>();
    return computeIndirectImpact(Array.from(directImpactPaths), graph, 2);
  }, [impactResult, directImpactPaths, graph]);

  const owner = repoContext?.owner ?? currentRepo.owner;
  const repo = repoContext?.repo ?? currentRepo.repo;
  const branch = currentRepo.branch;
  const ref = currentRepo.sha || branch;
  const [query, setQuery] = useState('');

  const handleOpenGithub = useCallback((url: string) => {
    if (chrome.tabs?.create) {
      chrome.tabs.create({ url });
      return;
    }
    window.open(url, '_blank', 'noreferrer');
  }, []);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filePaths = Object.keys(graph).filter((path) => path.toLowerCase().includes(normalizedQuery));
    // Cap at 150 nodes for performance
    const cappedPaths = filePaths.slice(0, 150);

    const rawNodes: Node<FileNodeData>[] = cappedPaths.map((filePath) => {
      const nodeData = graph[filePath];
      const parts = filePath.split('/');
      const filename = parts.pop() ?? filePath;
      const dir = parts.length > 0 ? parts.join('/') + '/' : '';

      let impactType: ImpactHighlight = 'none';
      if (directImpactPaths.has(filePath)) {
        impactType = 'direct';
      } else if (indirectImpactPaths.has(filePath)) {
        impactType = 'indirect';
      }

      const githubUrl =
        owner && repo
          ? `https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/blob/${encodeURIComponent(ref)}/${filePath.split('/').map(encodeURIComponent).join('/')}`
          : undefined;

      return {
        id: filePath,
        type: 'fileNode',
        data: {
          path: filePath,
          filename,
          dir,
          impactType,
          summary: nodeData?.summary ?? '',
          githubUrl,
          onOpenGithub: handleOpenGithub,
        },
        position: { x: 0, y: 0 },
      };
    });

    const rawEdges: Edge[] = [];
    const cappedSet = new Set(cappedPaths);

    cappedPaths.forEach((filePath) => {
      const nodeData = graph[filePath];
      if (!nodeData) return;

      nodeData.imports.forEach((importedPath) => {
        if (!cappedSet.has(importedPath)) return;

        const isDirect = directImpactPaths.has(filePath) || directImpactPaths.has(importedPath);
        const isIndirect = indirectImpactPaths.has(filePath) || indirectImpactPaths.has(importedPath);

        let strokeColor = '#30363d';
        if (isDirect) {
          strokeColor = '#f85149';
        } else if (isIndirect) {
          strokeColor = '#d29922';
        }

        rawEdges.push({
          id: `${filePath}->${importedPath}`,
          source: filePath,
          target: importedPath,
          animated: isDirect,
          style: {
            stroke: strokeColor,
            strokeWidth: isDirect ? 2 : 1.2,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: strokeColor,
            width: 12,
            height: 12,
          },
        });
      });
    });

    return getLayoutedElements(rawNodes, rawEdges);
  }, [graph, directImpactPaths, indirectImpactPaths, owner, repo, ref, query, handleOpenGithub]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // A repository fetch can finish while this tab is visible.
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const nodeCount = Object.keys(graph).length;

  if (nodeCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <Network className="w-8 h-8 text-[#30363d]" />
        <p className="text-sm font-medium text-[#8b949e]">No dependency data yet</p>
        <p className="text-xs text-[#484f58] leading-relaxed">
          Select a repository or turn on Demo Mode to inspect module relationships.
        </p>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full bg-[#0d1117]">
      {/* Overlay status bar */}
      <div className="absolute top-2 left-2 z-10 flex flex-wrap items-center gap-2 bg-[#161b22]/90 backdrop-blur border border-[#30363d] px-2.5 py-1.5 rounded-md text-[11px] shadow-lg pointer-events-auto">
        <span className="font-semibold text-[#e6edf3]">
          {nodeCount} files
        </span>
        <span className="text-[#30363d]">|</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#f85149]" />
          <span className="text-[#8b949e]">Direct ({directImpactPaths.size})</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#d29922]" />
          <span className="text-[#8b949e]">Indirect ({indirectImpactPaths.size})</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[#484f58]" />
          <span className="text-[#8b949e]">Unaffected</span>
        </div>
      </div>

      <div className="absolute top-12 left-2 z-10 flex items-center gap-1.5 bg-[#161b22]/90 backdrop-blur border border-[#30363d] px-2 py-1.5 rounded-md shadow-lg">
        <Search className="w-3.5 h-3.5 text-[#8b949e]" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter files…"
          aria-label="Filter dependency map files"
          className="w-28 bg-transparent text-[11px] text-[#e6edf3] placeholder-[#8b949e] outline-none"
        />
        {query && (
          <button type="button" onClick={() => setQuery('')} className="text-[#8b949e] hover:text-[#e6edf3]" title="Clear filter">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {isDemoMode && (
        <div className="absolute top-2 right-2 z-10 bg-[#161b22]/90 backdrop-blur border border-[#30363d] px-2 py-1 rounded text-[10px] text-[#58a6ff] flex items-center gap-1 shadow-lg">
          <Info className="w-3 h-3" />
          <span>Demo Repository</span>
        </div>
      )}

      <div className="absolute bottom-2 left-2 z-10 bg-[#161b22]/90 border border-[#30363d] px-2 py-1 rounded text-[10px] text-[#8b949e] flex items-center gap-1">
        <AlertCircle className="w-3 h-3 text-[#58a6ff]" />
        <span>{query ? `${nodes.length} matching files` : 'Click any node to open file on GitHub'}</span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.5}
      >
        <Background color="#21262d" gap={16} size={1} />
        <Controls className="!bg-[#161b22] !border-[#30363d] !rounded-md overflow-hidden !fill-[#c9d1d9]" />
        <MiniMap
          nodeColor={(n) => {
            const d = n.data as FileNodeData;
            if (d.impactType === 'direct') return '#f85149';
            if (d.impactType === 'indirect') return '#d29922';
            return '#30363d';
          }}
          maskColor="rgba(13, 17, 23, 0.7)"
          className="!bg-[#161b22] !border-[#30363d] !rounded-md overflow-hidden"
        />
      </ReactFlow>
    </div>
  );
}
