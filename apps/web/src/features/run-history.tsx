import { Link } from "react-router-dom";
import type { Shared } from "../lib/types";
import { PageHeading } from "../components/shared";
import { Panel } from "../components/workspace";
import { ResourceBrowser } from "./resource-browser";

export function RunHistory({ workspace, project }: Shared) {
  return (
    <>
      <PageHeading
        eyebrow="CORE RUN HISTORY"
        title="Eksekusi"
        description="Riwayat tersimpan dengan status dan provenance aktual. Output dibaca ketika console dibuka."
      >
        <Link to="/runs/new">Eksekusi baru</Link>
      </PageHeading>
      <Panel title="Riwayat eksekusi">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="runs"
          title="run"
          statuses={[
            "queued",
            "started",
            "running",
            "stopping",
            "completed",
            "failed",
            "cancelled",
            "outcome_unknown",
          ]}
          link={(item) => `/runs/${item.id}`}
          extra={(item) => (
            <>
              <p className="mono">
                {String(item.references.model || "Belum tersedia")}
              </p>
              <p>
                Token{" "}
                {item.references.total_tokens == null
                  ? "Tidak tersedia"
                  : String(item.references.total_tokens)}{" "}
                · {String(item.references.usage_availability)}
              </p>
            </>
          )}
        />
      </Panel>
    </>
  );
}
