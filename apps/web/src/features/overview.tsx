import { Link } from "react-router-dom";
import { Plus, Radio } from "lucide-react";
import type { Workspace } from "../lib/types";
import type { ResourceItem, WorkspaceSummary } from "../lib/workspace-types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Empty, PageHeading, Status } from "../components/shared";
import { Panel } from "../components/workspace";
import { gatewayStatus, runtimeTone } from "../lib/studio-state";

export function Overview({
  summary,
  workspace,
  project,
  openBlueprint,
}: {
  summary: WorkspaceSummary;
  workspace: Workspace;
  project: string;
  openBlueprint: () => void;
}) {
  const active = workspace.projects.find((item) => item.id === project);
  const metrics = [
    ["blueprints", "Blueprint Agent", "/factory"],
    ["runs", "Eksekusi Tersimpan", "/runs"],
    ["audits", "Jejak Core", "/governance"],
    ["assigned", "Agent ditugaskan", "/runs"],
  ];
  return (
    <div className="overview-page workspace-overview">
      <div className="studio-hero">
        <div className="studio-hero-meta">
          <span className="studio-live-pill">ARYN STUDIO</span>
          <span className="studio-project-tag">
            <Radio size={12} />
            {active?.name || project}
          </span>
        </div>
        <PageHeading
          title="Ruang kerja agent Anda."
          description="Perhatian, inventaris, dan aktivitas nyata dalam proyek aktif."
        >
          {summary.permissions["blueprint:create"] && (
            <Button onClick={openBlueprint}>
              <Plus size={16} />
              Buat agent
            </Button>
          )}
        </PageHeading>
        <p className="workspace-freshness">
          Lingkup {workspace.organization.name} / {active?.name || project} ·
          Diperbarui {date(summary.refreshed_at)} ·{" "}
          {Intl.DateTimeFormat().resolvedOptions().timeZone}
        </p>
        {summary.metrics.blueprints.value === 0 && (
          <p className="workspace-freshness">
            Agent pertama Anda dimulai di sini
          </p>
        )}
      </div>
      <Panel
        title="Perlu perhatian"
        subtitle="Temuan Core dengan jalur untuk memeriksa sumbernya."
      >
        {summary.attention.length ? (
          <ul className="attention-list">
            {summary.attention.map((item) => (
              <li key={item.code}>
                <Link to={item.route}>
                  <strong>{number(item.count)}</strong>
                  <span>{item.description}</span>
                  <span aria-hidden="true">→</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="Tidak ada temuan perhatian"
            description="Tidak ada run gagal atau hasil tidak pasti tercatat; pemeriksaan candidate dibatasi pada lima versi terbaru yang memiliki evaluasi."
          />
        )}
      </Panel>
      <div className="control-center-hud">
        {metrics.map(([key, label, route]) => {
          const metric = summary.metrics[key];
          return (
            <Link
              key={key}
              to={route}
              className="hud-card hud-card-interactive"
            >
              <div className="hud-body">
                <strong className="hud-metric">
                  {metric?.value == null
                    ? "Tidak tersedia"
                    : number(metric.value)}
                </strong>
                <span className="hud-title">{label}</span>
                <p className="hud-desc">{metric?.definition}</p>
              </div>
              <div className="hud-footer">
                {key === "runs" ? (
                  <>
                    <span className={`text-${runtimeTone(workspace.runtime)}`}>
                      ARYN Runtime{" "}
                      {workspace.runtime.ready ? "siap" : "belum siap"}
                    </span>
                    <span className={`text-${gatewayStatus(workspace).tone}`}>
                      {gatewayStatus(workspace).label}
                    </span>
                  </>
                ) : (
                  <span>
                    {key === "assigned"
                      ? `${summary.metrics.published.value ?? "Tidak tersedia"} versi berstatus published`
                      : metric?.source}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
      <div className="workspace-columns">
        <Panel
          title="Eksekusi terbaru"
          subtitle="Metadata tersimpan; output dimuat saat membuka detail."
          action={
            <Link className="text-link" to="/runs">
              Lihat semua
            </Link>
          }
        >
          <Recent items={summary.latest_runs} resource="runs" />
        </Panel>
        <Panel
          title="Aktivitas terbaru"
          subtitle="Autentikasi evidence diperiksa untuk setiap item yang ditampilkan."
          action={
            <Link className="text-link" to="/governance">
              Lihat semua
            </Link>
          }
        >
          <Recent items={summary.latest_audits} resource="audits" />
        </Panel>
        <Panel
          title="Penggunaan & ketersediaan"
          subtitle={summary.usage.source}
        >
          <dl className="definition-grid">
            <dt>Token tercatat</dt>
            <dd>
              {summary.usage.tokens == null
                ? "Tidak tersedia"
                : number(summary.usage.tokens)}
            </dd>
            <dt>Token dicadangkan</dt>
            <dd>
              {summary.budget?.reserved_tokens == null
                ? "Tidak tersedia"
                : number(summary.budget.reserved_tokens)}
            </dd>
            <dt>Biaya provider</dt>
            <dd>Tidak tersedia</dd>
            <dt>Entitlement</dt>
            <dd>Belum terverifikasi</dd>
            <dt>Runtime</dt>
            <dd>{workspace.runtime.message}</dd>
            <dt>Model</dt>
            <dd>{gatewayStatus(workspace).label}</dd>
          </dl>
        </Panel>
        <Panel
          title="Jalur kerja"
          subtitle="Aksi tersedia mengikuti izin efektif dari Core."
        >
          <div className="workspace-shortcuts">
            <Link to="/projects">Projects & Divisions</Link>
            <Link to="/factory">Agent Factory</Link>
            <Link to="/bench">Tinjau Bench</Link>
            {summary.permissions["version:approve"] && (
              <Link to="/approvals">Tinjau persetujuan</Link>
            )}
            {summary.permissions["run:create"] && (
              <Link to="/runs">Jalankan agent yang ditugaskan</Link>
            )}
          </div>
        </Panel>
      </div>
      <Panel
        title="Siklus agent"
        subtitle="Jalur baca untuk memeriksa konfigurasi dan evidence; membuka langkah tidak melakukan mutasi."
      >
        <ol
          className="workspace-lifecycle"
          aria-label="Alur agent dari blueprint hingga eksekusi"
        >
          {[
            ["Blueprint", "/factory", "Agent Factory"],
            ["Versi", "/factory", "Agent Factory"],
            ["Bench", "/bench", "Bench"],
            ["Persetujuan", "/approvals", "Persetujuan"],
            ["Publikasi", "/factory", "Agent Factory"],
            ["Penugasan", "/factory", "Agent Factory"],
            ["Eksekusi", "/runs", "Eksekusi"],
          ].map(([label, route, destination], index) => (
            <li key={label}>
              <Link
                to={route}
                aria-label={`Tahap ${index + 1}: ${label} — buka ${destination}`}
              >
                <span>{index + 1}</span>
                {label}
              </Link>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}
function Recent({
  items,
  resource,
}: {
  items: ResourceItem[];
  resource: "runs" | "audits";
}) {
  return items.length ? (
    <ul className="workspace-recent">
      {items.map((item) => (
        <li key={item.id}>
          <Link
            to={
              resource === "runs"
                ? `/runs/${encodeURIComponent(item.id)}`
                : `/governance?resource=${encodeURIComponent((item.references.resource_id as string) || item.id)}`
            }
          >
            <strong>{item.name}</strong>
            <span>{item.status && <Status value={item.status} />}</span>
            <small>
              {item.verified
                ? resource === "runs"
                  ? "Captured claim terverifikasi"
                  : "Audit terautentikasi"
                : "Evidence belum terverifikasi"}{" "}
              · {date(item.created_at)}
            </small>
            {resource === "runs" && (
              <small>
                {item.references.total_tokens == null
                  ? "Penggunaan tidak tersedia"
                  : `${number(item.references.total_tokens as number)} token tercatat`}
              </small>
            )}
          </Link>
        </li>
      ))}
    </ul>
  ) : (
    <Empty
      title="Belum ada aktivitas"
      description="Data akan muncul setelah aktivitas Core tersimpan pada proyek ini."
    />
  );
}
