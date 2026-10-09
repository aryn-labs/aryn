import type { Shared } from "../lib/types";
import { PageHeading, Notice } from "../components/shared";
import { Panel } from "../components/workspace";
import { ResourceBrowser } from "./resource-browser";
import { Link } from "react-router-dom";

export function ApprovalQueue({ workspace, project, data }: Shared) {
  return (
    <>
      <PageHeading
        eyebrow="CORE HUMAN APPROVAL"
        title="Persetujuan"
        description="Approval mengikat actor dan scope ke payload hash serta evaluation yang tepat."
      />
      <p>
        Reviewer sesi: {workspace.user.id} · Scope {workspace.organization.id}/
        {project}. Core memverifikasi kewenangan pada setiap aksi.
      </p>
      {!data.permissions["version:approve"] && (
        <Notice>
          Peran ini hanya dapat membaca. Approval membutuhkan kewenangan Core.
        </Notice>
      )}
      <Panel title="Candidate untuk ditinjau">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="versions"
          title="candidate"
          initialStatus="draft"
          statuses={["draft", "approved", "published"]}
          link={(item) =>
            `/factory/${item.references.blueprint_id}/versions/${item.id}`
          }
          extra={(item) => (
            <>
              <code>{String(item.references.payload_hash)}</code>
              <p>
                Evaluation{" "}
                {String(
                  (
                    item.references.registry as
                      { evaluation_id?: string } | undefined
                  )?.evaluation_id || "Belum tersedia",
                )}{" "}
                · Scope {item.organization_id}/{item.project_id}
              </p>
              <p>
                {item.verified
                  ? "Bench terverifikasi; tinjau hasil, regression, dan hash."
                  : "Promotion diblokir sampai Bench dan evidence terverifikasi."}
              </p>
              <Link
                to={`/factory/${item.references.blueprint_id}?versi=${item.id}`}
              >
                Tinjau lifecycle versi ini
              </Link>
            </>
          )}
        />
      </Panel>
      <Panel title="Riwayat approval Core">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="approvals"
          title="approval"
          statuses={["approved", "rejected", "pending"]}
          extra={(item) => (
            <>
              <p>
                Actor {String(item.references.actor_id)} · Scope{" "}
                {item.organization_id}/{item.project_id}
              </p>
              <code>{String(item.references.payload_hash)}</code>
              <p>Evaluation {String(item.references.evaluation_id || "—")}</p>
            </>
          )}
        />
      </Panel>
    </>
  );
}
