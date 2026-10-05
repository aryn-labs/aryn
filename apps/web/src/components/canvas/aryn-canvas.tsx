import React, { useCallback, useEffect, useRef, useState } from "react";
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
import type {
  Assignment,
  Audit,
  Evaluation,
  Run,
  Version,
  Workspace,
} from "../../lib/types";
import { useReducedMotion } from "../../lib/motion";

interface ArynCanvasProps {
  mode: CanvasMode;
  initialNodes: Node[];
  initialEdges: Edge[];
  // Selected version / run / evaluation
  version?: Version | null;
  workspace?: Workspace;
  run?: Run | null;
  assignment?: Assignment;
  versions?: Version[];
  pending?: boolean;
  error?: string;
  onCreateVersion?: (body: unknown) => Promise<void>;
  auditEvents?: Audit[];
  evaluation?: Evaluation | null;
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
  assignment,
  versions,
  pending,
  error,
  onCreateVersion,
  auditEvents,
  evaluation,
  onRunBench,
  onApproveVersion,
  onPublishVersion,
  className = "",
  showInspectorByDefault = false,
}: ArynCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    () =>
      initialNodes.find(
        (n) => n.type === (mode === "bench" ? "evaluation" : "agent"),
      )?.id || null,
  );
  const [showInspector, setShowInspector] = useState(showInspectorByDefault);
  const [showMinimap, setShowMinimap] = useState(false);
  const inspectorToggle = useRef<HTMLButtonElement>(null);

  const { fitView, zoomIn, zoomOut } = useReactFlow();
  const reducedMotion = useReducedMotion();

  // Sync nodes and edges when initial props change
  useEffect(() => {
    setNodes((current) =>
      initialNodes.map((node) => ({
        ...node,
        position:
          current.find((n) => n.id === node.id)?.position || node.position,
      })),
    );
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  // Handle node selection
  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
    setShowInspector(true);
  }, []);

  const handleSelectNodeFromData = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    setShowInspector(true);
  }, []);

  // Enrich node data with selection callback
  const enrichedNodes = nodes.map((node) => ({
    ...node,
    ariaRole: "group" as const,
    draggable: mode === "factory",
    connectable: false,
    deletable: false,
    data: {
      ...(node.data as BaseNodeData),
      selected: node.id === selectedNodeId,
      onSelectNode: handleSelectNodeFromData,
    },
  }));

  const selectedNode = enrichedNodes.find((n) => n.id === selectedNodeId)
    ?.data as BaseNodeData | null;

  return (
    <div className={`aryn-studio-canvas-container ${className}`}>
      {/* Canvas Top Bar */}
      <div className="canvas-header-bar">
        <div className="canvas-mode-indicator">
          <span className={`canvas-mode-pill mode-${mode}`}>
            {mode === "factory" && "STUDIO ARSITEKTUR"}
            {mode === "execution" && "HASIL EKSEKUSI"}
            {mode === "bench" && "BENCH EVALUASI"}
          </span>
          <span className="canvas-sub-tag">
            {mode === "factory"
              ? "Tata letak sementara · konfigurasi melalui versi baru"
              : "Hanya baca · pan, zoom, dan inspector"}
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
            onClick={() =>
              fitView({ padding: 0.2, duration: reducedMotion ? 0 : 400 })
            }
          >
            <RotateCcw size={14} />
            <span className="text-xs">Pusatkan</span>
          </Button>
          <Button
            size="sm"
            variant={showMinimap ? "secondary" : "ghost"}
            aria-label="Peta mini"
            aria-pressed={showMinimap}
            onClick={() => setShowMinimap(!showMinimap)}
          >
            <Maximize2 size={14} />
            <span className="text-xs">Minimap</span>
          </Button>
          <Button
            ref={inspectorToggle}
            size="sm"
            variant={showInspector ? "secondary" : "ghost"}
            aria-label="Panel inspector"
            aria-pressed={showInspector}
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
            fitViewOptions={{
              padding: 0.18,
              maxZoom: 1,
              // Start Factory with readable configuration nodes; Pusatkan shows the whole architecture.
              nodes:
                mode === "factory"
                  ? initialNodes.filter((n) =>
                      ["node-input", "node-agent", "node-model"].includes(n.id),
                    )
                  : undefined,
            }}
            minZoom={0.2}
            maxZoom={1.6}
            proOptions={{ hideAttribution: true }}
            className="aryn-flow-viewport"
            nodesDraggable={mode === "factory"}
            nodesConnectable={false}
            edgesReconnectable={false}
            nodesFocusable={false}
            edgesFocusable={false}
            deleteKeyCode={null}
            aria-label={`Canvas ARYN ${mode === "factory" ? "arsitektur" : "hanya baca"}`}
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
            onClose={() => {
              setShowInspector(false);
              inspectorToggle.current?.focus();
            }}
            version={version}
            workspace={workspace}
            onRunBench={onRunBench}
            onApproveVersion={onApproveVersion}
            onPublishVersion={onPublishVersion}
            run={run}
            assignment={assignment}
            versions={versions}
            pending={pending}
            error={error}
            onCreateVersion={onCreateVersion}
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
      <CanvasInner
        key={`${props.mode}:${props.run?.id || props.evaluation?.id || props.version?.id || "empty"}`}
        {...props}
      />
    </ReactFlowProvider>
  );
}
