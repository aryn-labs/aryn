import { Link } from "react-router-dom";
import type { Shared } from "../lib/types";
import { PageHeading, Notice } from "../components/shared";
import { Panel } from "../components/workspace";
import { ResourceBrowser } from "./resource-browser";
import { executionReady } from "../lib/studio-state";
import { number } from "../lib/utils";

export function Operations({ workspace, project, data }: Shared) {
  const ready = executionReady(workspace);
  return (
    <>
      <PageHeading
        eyebrow="MANUAL OPERATIONS"
        title="Agent Operations"
        description="Agent published dan assignment aktif. Eksekusi dimulai manual melalui Core."
      />
      <Notice tone={ready ? "success" : "warning"}>
        Runtime {ready ? "siap" : "belum siap"} · {workspace.runtime.message} ·
        Gateway {workspace.gateway.reason}
      </Notice>
      <Panel title="Budget Core">
        <p>
          Batas per run:{" "}
          {data.budget
            ? number(data.budget.max_tokens_per_run)
            : "Tidak tersedia"}{" "}
          token · Penggunaan:{" "}
          {data.budget
            ? number(data.budget.cumulative_tokens)
            : "Tidak tersedia"}{" "}
          · Reservation:{" "}
          {data.budget?.reserved_tokens == null
            ? "Tidak tersedia"
            : number(data.budget.reserved_tokens)}
        </p>
        <p>
          Biaya provider dan entitlement hanya tersedia jika ada evidence; nilai
          tidak diperkirakan.
        </p>
      </Panel>
      <Panel title="Assignment operasional">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="assignments"
          title="assignment"
          statuses={["active", "inactive"]}
          link={(item) => `/factory/${item.references.blueprint_id}`}
          extra={(item) => (
            <>
              <p className="mono">
                v{String(item.references.version_number || "—")} ·{" "}
                {String(item.references.model || "—")}
              </p>
              {item.status === "active" &&
              item.verified &&
              ready &&
              data.permissions["run:create"] ? (
                <Link to={`/runs/new?penugasan=${item.id}`}>
                  Jalankan melalui Core
                </Link>
              ) : (
                <span>Tinjau readiness dan evidence sebelum eksekusi.</span>
              )}
            </>
          )}
        />
      </Panel>
      <Panel title="Agent published">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="versions"
          title="versi published"
          initialStatus="published"
          statuses={["published"]}
          link={(item) =>
            `/factory/${item.references.blueprint_id}/versions/${item.id}`
          }
          extra={(item) => (
            <span className="mono">{String(item.references.model || "—")}</span>
          )}
        />
      </Panel>
      <Panel title="Run terbaru">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="runs"
          title="run"
          statuses={[
            "running",
            "completed",
            "failed",
            "cancelled",
            "outcome_unknown",
          ]}
          link={(item) => `/runs/${item.id}`}
          extra={(item) => (
            <>
              <p>
                Reservation{" "}
                {String(item.references.reserved_tokens ?? "Tidak tersedia")}{" "}
                token ·{" "}
                {item.references.usage_settled ? "settled" : "belum settled"}
              </p>
              <details>
                <summary>Effective limits dari captured claim</summary>
                <pre className="canonical-definition">
                  {item.verified
                    ? JSON.stringify(item.references.effective_limits, null, 2)
                    : "Evidence belum terverifikasi"}
                </pre>
              </details>
              {item.verified && item.references.workflow && (
                <Link
                  to={`/workflows/${String((item.references.workflow as { workflow_id: string }).workflow_id)}?run=${String((item.references.workflow as { run_id: string }).run_id)}`}
                >
                  Workflow timeline
                </Link>
              )}
            </>
          )}
        />
      </Panel>
    </>
  );
}
