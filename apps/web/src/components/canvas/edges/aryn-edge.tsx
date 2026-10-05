import type { ComponentType } from "react";
import { BaseEdge, getBezierPath } from "@xyflow/react";

export function ArynEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}: any) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const status = (data?.status as string) || "idle";
  const animated = Boolean(data?.animated || status === "running");

  return (
    <>
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          strokeWidth: 2,
          ...style,
        }}
        className={`aryn-edge aryn-edge-${status} ${animated ? "aryn-edge-animated" : ""}`}
      />
      {animated && (
        <circle r="3" className="aryn-edge-flow-dot">
          <animateMotion
            dur="2s"
            repeatCount="indefinite"
            path={edgePath}
          />
        </circle>
      )}
    </>
  );
}

export const edgeTypes: Record<string, ComponentType<any>> = {
  aryn: ArynEdge,
};
