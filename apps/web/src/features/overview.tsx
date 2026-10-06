import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Beaker,
  Bot,
  ChevronRight,
  Plus,
  Radio,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Empty, PageHeading, Status } from "../components/shared";
import { needsApproval, runtimeTone, gatewayStatus } from "../lib/studio-state";
import type { Shared } from "../lib/types";
import { Panel, AuditList } from "../components/workspace";
import { AgentFlow } from "../components/agent-flow";

export function Overview({ data, workspace, project, openBlueprint }: Shared) {
  const navigate = useNavigate();
  const published = data.versions.filter(
    (v) => v.status === "published",
  ).length;

  const pendingApprovals = data.versions.filter(needsApproval).length;

  const activeProject = workspace.projects.find((p) => p.id === project);

  return (
    <div className="overview-page studio-control-center">
      {/* Studio Control Center Hero */}
      <div className="studio-hero">
        <div className="studio-hero-meta">
          <span className="studio-live-pill">PUSAT KENDALI · ARYN STUDIO</span>
          <span className="studio-project-tag">
            <Radio size={12} />
            {activeProject?.name || "Proyek tidak tersedia"}
          </span>
        </div>
        <PageHeading
          eyebrow="ARYN STUDIO CONTROL CENTER"
          title="Ruang kerja agent Anda."
          description="Rancang agent, tinjau evidence, dan telusuri eksekusi pada proyek aktif."
        >
          <Button
            onClick={openBlueprint}
            disabled={!data.permissions["run:create"]}
            className="btn-studio-primary"
          >
            <Plus size={16} />
            Buat agent
          </Button>
        </PageHeading>
      </div>

      {/* Spatial Control & Telemetry HUD */}
      <div className="control-center-hud">
        {/* Workspace Context Card */}
        <Link className="hud-card hud-card-interactive" to="/factory">
          <div className="hud-header">
            <div className="hud-icon hud-icon-violet">
              <Bot size={17} />
            </div>
            <span className="hud-badge hud-badge-violet">Factory</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">
              {number(data.blueprints.length)}
            </strong>
            <span className="hud-title">Blueprint Agent</span>
            <p className="hud-desc">Definisi agent dalam proyek aktif</p>
          </div>
          <div className="hud-footer">
            <span>{published} versi dipublikasikan</span>
            <ChevronRight size={14} />
          </div>
        </Link>

        {/* Runtime & ARYN Runtime Confinement */}
        <Link className="hud-card hud-card-interactive" to="/runs">
          <div className="hud-header">
            <div className="hud-icon hud-icon-cyan">
              <Workflow size={17} />
            </div>
            <span className="hud-badge hud-badge-cyan">Runtime</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">{number(data.runs.length)}</strong>
            <span className="hud-title">Eksekusi Tersimpan</span>
            <p className="hud-desc">Hasil dan status tersimpan dari Core</p>
          </div>
          <div className="hud-footer">
            <span className={`text-${runtimeTone(workspace.runtime)}`}>
              ARYN Runtime{" "}
              {workspace.runtime.ready
                ? "siap"
                : workspace.runtime.connected
                  ? "belum siap"
                  : "tidak tersedia"}
            </span>
            <span className={`text-${gatewayStatus(workspace).tone}`}>
              {gatewayStatus(workspace).label}
            </span>
            <ChevronRight size={14} />
          </div>
        </Link>

        {/* Governance & Core Integrity */}
        <Link className="hud-card hud-card-interactive" to="/governance">
          <div className="hud-header">
            <div className="hud-icon hud-icon-emerald">
              <ShieldCheck size={17} />
            </div>
            <span className="hud-badge stat-pill-emerald">Core Security</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">{number(data.audit.length)}</strong>
            <span className="hud-title">Jejak Core</span>
            <p className="hud-desc">
              Peristiwa aplikasi tersimpan pada proyek aktif
            </p>
          </div>
          <div className="hud-footer">
            <span>
              {data.versions.filter((v) => v.integrity_valid).length} versi
              dengan integritas valid
            </span>
            <ChevronRight size={14} />
          </div>
        </Link>

        {/* Bench & Pending Approvals */}
        <Link className="hud-card hud-card-interactive" to="/approvals">
          <div className="hud-header">
            <div className="hud-icon hud-icon-amber">
              <Beaker size={17} />
            </div>
            <span className="hud-badge hud-badge-amber">
              {pendingApprovals > 0 ? "Perlu Tinjauan" : "Siaga"}
            </span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">{number(pendingApprovals)}</strong>
            <span className="hud-title">Menunggu Persetujuan</span>
            <p className="hud-desc">Lulus Bench & siap tinjauan Core</p>
          </div>
          <div className="hud-footer">
            <span>{data.evaluations.length} evaluasi Bench</span>
            <ChevronRight size={14} />
          </div>
        </Link>
      </div>

      <div className="overview-content">
        {/* Lifecycle Studio Flow Panel */}
        <Panel
          className="overview-flow-panel"
          title="Dari ide ke eksekusi"
          subtitle="Tujuh tahap untuk merancang, memvalidasi, dan mengoperasikan agent."
          action={<span className="subtle-label">7 TAHAP</span>}
        >
          <AgentFlow data={data} />
          <div className="workflow-footer">
            <span className="workflow-assurance">
              <ShieldCheck size={15} />
              Bench lulus dan persetujuan Core sebelum publikasi
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/factory")}
            >
              Buka Agent Factory
              <ArrowRight size={15} />
            </Button>
          </div>
        </Panel>

        {/* Spatial Agents Matrix & Live Telemetry Stream */}
        <div className="overview-layout">
          <div className="overview-primary">
            <Panel
              title="Agent di proyek ini"
              subtitle="Blueprint dan konfigurasi yang benar-benar tersimpan."
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate("/factory")}
                >
                  Lihat semua
                  <ArrowRight size={14} />
                </Button>
              }
            >
              {data.blueprints.length ? (
                <div className="agent-overview-list">
                  {data.blueprints.slice(0, 4).map((bp) => {
                    const v = data.versions.find(
                      (v) => v.blueprint_id === bp.id,
                    );
                    const assignments = data.assignments.filter(
                      (a) => a.blueprint_id === bp.id,
                    );
                    return (
                      <button
                        className="agent-overview-item"
                        key={bp.id}
                        onClick={() => navigate(`/factory/${bp.id}`)}
                      >
                        <div className="agent-icon">
                          <Bot size={19} />
                        </div>
                        <div className="agent-meta">
                          <strong>{bp.name}</strong>
                          <small>
                            {bp.description ||
                              bp.slug ||
                              "Blueprint riset teks"}
                          </small>
                          <div className="agent-sub-pills">
                            {v && (
                              <span className="mono text-xs text-secondary">
                                v{v.version_number}
                              </span>
                            )}
                            {assignments.length > 0 && (
                              <span className="text-xs text-secondary">
                                · {assignments.length} penugasan
                              </span>
                            )}
                          </div>
                        </div>
                        {v ? (
                          <Status value={v.status} />
                        ) : (
                          <span className="subtle">Belum ada versi</span>
                        )}
                        <ChevronRight size={16} className="agent-arrow" />
                      </button>
                    );
                  })}
                </div>
              ) : (
                <Empty
                  title="Agent pertama Anda dimulai di sini"
                  description="Buat blueprint untuk mendefinisikan agent riset. Tidak ada agent atau aktivitas contoh yang ditambahkan otomatis."
                  action="Buat blueprint"
                  onAction={openBlueprint}
                />
              )}
            </Panel>

            {/* Recent Execution Runs Stream */}
            {data.runs.length > 0 && (
              <Panel
                className="mt-6"
                title="Eksekusi terbaru"
                subtitle="Hasil pemrosesan model aktual melalui ARYN Runtime."
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate("/runs")}
                  >
                    Buka Eksekusi
                    <ArrowRight size={14} />
                  </Button>
                }
              >
                <div className="recent-runs-stream">
                  {data.runs.slice(0, 3).map((r) => (
                    <Link
                      key={r.id}
                      className="recent-run-item"
                      to={`/runs?hasil=${encodeURIComponent(r.id)}`}
                    >
                      <div className="run-stream-top">
                        <span className="mono text-xs text-secondary">
                          {r.id}
                        </span>
                        <Status value={r.status} />
                      </div>
                      <p className="run-stream-prompt line-clamp-2">
                        {r.prompt}
                      </p>
                      <div className="run-stream-meta">
                        <span className="mono text-xs">{r.model}</span>
                        <span className="text-xs text-secondary">
                          {number(r.total_tokens || 0)} token
                        </span>
                        <span className="text-xs text-secondary">
                          {date(r.created_at)}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              </Panel>
            )}
          </div>

          <div className="overview-secondary">
            <Panel
              title="Aktivitas terbaru"
              subtitle="Peristiwa Core terbaru di proyek ini."
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate("/governance")}
                >
                  Lihat semua
                  <ArrowRight size={14} />
                </Button>
              }
            >
              <AuditList events={data.audit.slice(0, 5)} compact />
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
