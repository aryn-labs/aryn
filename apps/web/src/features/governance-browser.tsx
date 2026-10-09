import type { Shared } from "../lib/types";
import { PageHeading } from "../components/shared";
import { Panel } from "../components/workspace";
import { ResourceBrowser } from "./resource-browser";

export function GovernanceBrowser({ workspace, project }: Shared) {
  return (
    <>
      <PageHeading
        eyebrow="OTORITAS CORE"
        title="Tata Kelola"
        description="Audit terautentikasi dalam scope proyek. Payload detail telah disanitasi server."
      />
      <Panel title="Jejak audit">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="audits"
          title="audit"
          audit
          statuses={[
            "attempted",
            "allowed",
            "denied",
            "completed",
            "failed",
            "cancelled",
          ]}
        />
      </Panel>
    </>
  );
}
