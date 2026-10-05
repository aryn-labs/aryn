import React, { useCallback, useEffect, useState } from "react";
import {
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Maximize2,
  Minus,
  Plus,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import { Button } from "../ui/button";
import { nodeTypes } from "./nodes/custom-nodes";
import { edgeTypes } from "./edges/aryn-edge";
import { CanvasInspector } from "./canvas-inspector";
import type { BaseNodeData, CanvasMode } from "./types";
import type { Audit, Evaluation, Run, Version, Workspace } from "../../lib/types";

interface ArynCanvasProps {
  mode: CanvasMode;
  initialNodes: Node[];
  initialEdges: Edge[];
  // Selected version / run / evaluation
  version?: Version | null;
  workspace?: Workspace;
  run?: Run | null;
  auditEvents?: Audit[];
  evaluation?: Evaluation | null;
  onNewVersionFromConfig?: (config: {
    systemPrompt: string;
    model: string;
    temperature: number;
    maxTokens: number;
  }) => void;
  onRunBench?: () => void;
  onApproveVersion?: () => void;
  onPublishVersion?: () => void;
  className?: string;
  showInspectorByDefault?: boolean;
}

function CanvasInner({
  mode,
  initialNodes,
  initialEdges,
  version,
  workspace,
  run,
  auditEvents,
  evaluation,
  onNewVersionFromConfig,
  onRunBench,
  onApproveVersion,
  onPublishVersion,
  className = "",
  showInspectorByDefault = false,
}: ArynCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showInspector, setShowInspector] = useState(showInspectorByDefault);
  const [showMinimap, setShowMinimap] = useState(false);

  const { fitView, zoomIn, zoomOut } = useReactFlow();

  // Sync nodes and edges when initial props change
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  // Handle node selection
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNodeId(node.id);
      setShowInspector(true);
    },
    [],
  );

  const handleSelectNodeFromData = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    setShowInspector(true);
  }, []);

  // Enrich node data with selection callback
  const enrichedNodes = nodes.map((node) => ({
    ...node,
    data: {
      ...(node.data as BaseNodeData),
      selected: node.id === selectedNodeId,
      onSelectNode: handleSelectNodeFromData,
    },
  }));

  const selectedNode =
    enrichedNodes.find((n) => n.id === selectedNodeId)?.data as BaseNodeData | null;

  return (
    <div className={`aryn-studio-canvas-container ${className}`}>
      {/* Canvas Top Bar */}
      <div className="canvas-header-bar">
        <div className="canvas-mode-indicator">
          <span className={`canvas-mode-pill mode-${mode}`}>
            <span className="pulse-indicator" />
            {mode === "factory" && "STUDIO ARSITEKTUR"}
            {mode === "execution" && "LIVE RUN ENGINE"}
            {mode === "bench" && "BENCH EVALUASI"}
          </span>
          <span className="canvas-sub-tag">
            {nodes.length} node · {edges.length} koneksi
          </span>
        </div>

        <div className="canvas-quick-controls">
          <Button
            size="sm"
            variant="ghost"
            aria-label="Perkecil zoom"
            onClick={() => zoomOut()}
          >
            <Minus size={14} />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Perbesar zoom"
            onClick={() => zoomIn()}
          >
            <Plus size={14} />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label="Pusatkan canvas"
            onClick={() => fitView({ padding: 0.2, duration: 400 })}
          >
            <RotateCcw size={14} />
            <span className="text-xs">Pusatkan</span>
          </Button>
          <Button
            size="sm"
            variant={showMinimap ? "secondary" : "ghost"}
            aria-label="Peta mini"
            onClick={() => setShowMinimap(!showMinimap)}
          >
            <Maximize2 size={14} />
            <span className="text-xs">Minimap</span>
          </Button>
          <Button
            size="sm"
            variant={showInspector ? "secondary" : "ghost"}
            aria-label="Panel inspector"
            onClick={() => setShowInspector(!showInspector)}
          >
            <SlidersHorizontal size={14} />
            <span className="text-xs">Inspector</span>
          </Button>
        </div>
      </div>

      <div className="canvas-workspace">
        <div className="canvas-flow-area">
          <ReactFlow
            nodes={enrichedNodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            nodeTypes={nodeTypes as any}
            edgeTypes={edgeTypes as any}
            fitView
            fitViewOptions={{ padding: 0.18 }}
            minZoom={0.2}
            maxZoom={1.6}
            proOptions={{ hideAttribution: true }}
            className="aryn-flow-viewport"
            aria-label="Canvas Diagram Interaktif ARYN Studio"
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1.2}
              className="aryn-canvas-bg-dots"
            />
            {showMinimap && (
              <MiniMap
                nodeStrokeColor="#8b7cf6"
                nodeColor="#152037"
                maskColor="rgba(7, 10, 19, 0.75)"
                className="aryn-minimap"
              />
            )}
          </ReactFlow>
        </div>

        {showInspector && (
          <CanvasInspector
            mode={mode}
            selectedNode={selectedNode}
            onClose={() => setShowInspector(false)}
            version={version}
            workspace={workspace}
            onNewVersionFromConfig={onNewVersionFromConfig}
            onRunBench={onRunBench}
            onApproveVersion={onApproveVersion}
            onPublishVersion={onPublishVersion}
            run={run}
            auditEvents={auditEvents}
            evaluation={evaluation}
          />
        )}
      </div>
    </div>
  );
}

export function ArynCanvas(props: ArynCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
