import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { Shared, Snapshot, Version } from "../lib/types";
import { api } from "../lib/api";
import { workspaceKey } from "../lib/workspace-types";
import { serializeDefinition } from "../lib/agent-editor-types";
import { Busy, Notice, PageHeading, Status } from "../components/shared";
import { Panel } from "../components/workspace";
import { ResourceBrowser } from "./resource-browser";
import "./agent-editor.css";

const definitionFields = [
  "schema_version",
  "role",
  "objective",
  "owner",
  "metadata",
  "system_prompt",
  "model",
  "temperature",
  "max_tokens",
  "tool_grants",
  "output_contract",
  "constraints",
  "model_policy",
  "tool_policy",
  "budget_policy",
  "evaluation_reference",
] as const;
export function versionDiff(before: Version, after: Version) {
  return definitionFields
    .filter(
      (field) =>
        serializeDefinition(before[field]) !==
        serializeDefinition(after[field]),
    )
    .map((field) => ({ field, before: before[field], after: after[field] }));
}
export function VersionDetail({
  versionId,
  blueprintId,
  data,
  workspace,
  project,
}: Shared & { versionId: string; blueprintId: string }) {
  const version = data.versions.find(
    (item) => item.id === versionId && item.blueprint_id === blueprintId,
  );
  const [comparison, setComparison] = useState("");
  const other = useQuery({
    queryKey: workspaceKey(
      workspace.organization.id,
      project,
      "version-diff",
      blueprintId,
      comparison,
    ),
    queryFn: ({ signal }) =>
      api<Snapshot>(
        `/projects/${project}/lifecycle?blueprint_id=${encodeURIComponent(blueprintId)}&version_id=${encodeURIComponent(comparison)}`,
        undefined,
        signal,
      ),
    enabled: !!comparison,
    retry: false,
  });
  if (!version || version.configuration_loaded === false)
    return (
      <Notice tone="error">
        Versi tidak tersedia dalam blueprint dan scope ini.
      </Notice>
    );
  const compared = other.data?.versions.find((item) => item.id === comparison);
  return (
    <>
      <PageHeading
        eyebrow="IMMUTABLE AGENT VERSION"
        title={`Versi ${version.version_number}`}
        description="Konfigurasi kanonis, hash, serta receipt governance aktual."
      >
        <Link to={`/factory/${blueprintId}`}>Agent Detail</Link>
      </PageHeading>
      <Panel title="Identitas dan provenance">
        <Link to={`/factory/${blueprintId}?versi=${version.id}`}>
          Tinjau approval, publication, assignment, dan rollback
        </Link>
        <Status value={version.status} />
        <p className="mono">{version.id}</p>
        <p className="mono">{version.payload_hash}</p>
        <Notice tone={version.integrity_valid ? "success" : "error"}>
          {version.integrity_valid
            ? "Integritas kanonis terverifikasi"
            : "Integritas tidak valid; aksi governance diblokir"}
        </Notice>
        <p>
          Bench:{" "}
          {version.bench_eligible
            ? "terverifikasi dan lulus"
            : "belum eligible"}{" "}
          · Core approval:{" "}
          {version.governance_valid ? "berlaku" : "belum berlaku"}
        </p>
        <pre className="canonical-definition">
          {JSON.stringify(version.registry, null, 2)}
        </pre>
        <Link to={`/bench?versi=${version.id}`}>Buka Bench dan regression</Link>
        <p>
          <Link to={`/factory/${blueprintId}/builder?source=${version.id}`}>
            Buat working copy dari versi ini
          </Link>
        </p>
        <p>
          Artefak versi ini hanya dapat dibaca; penyuntingan membuat candidate
          baru dengan hash sendiri.
        </p>
      </Panel>
      <Panel title="Konfigurasi lengkap">
        <dl>
          {definitionFields.map((field) => (
            <div key={field}>
              <dt>{field.replaceAll("_", " ")}</dt>
              <dd>
                <pre className="canonical-definition">
                  {typeof version[field] === "string"
                    ? version[field]
                    : JSON.stringify(version[field], null, 2)}
                </pre>
              </dd>
            </div>
          ))}
        </dl>
      </Panel>
      <Panel title="Perbandingan versi">
        <label>
          Bandingkan dengan versi ID
          <input
            value={comparison}
            onChange={(e) => setComparison(e.target.value)}
            maxLength={64}
          />
        </label>
        {other.isFetching && <Busy />}
        {other.error && <Notice tone="error">{other.error.message}</Notice>}
        {compared && !other.error && (
          <div className="table-scroll">
            <table className="definition-diff">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Versi pembanding</th>
                  <th>Versi ini</th>
                </tr>
              </thead>
              <tbody>
                {versionDiff(compared, version).map((change) => (
                  <tr key={change.field}>
                    <td>{change.field}</td>
                    <td>{JSON.stringify(change.before, null, 2)}</td>
                    <td>{JSON.stringify(change.after, null, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {versionDiff(compared, version).length === 0 && (
              <p>Konfigurasi sama.</p>
            )}
          </div>
        )}
      </Panel>
      <Panel title="Version Registry">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="versions"
          title="versi agent"
          blueprint={blueprintId}
          statuses={[
            "draft",
            "approved",
            "published",
            "rejected",
            "deprecated",
          ]}
          link={(item) => `/factory/${blueprintId}/versions/${item.id}`}
        />
      </Panel>
    </>
  );
}
