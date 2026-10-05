import { useNavigate } from "react-router-dom";
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
import type { Shared } from "../lib/types";
import { Panel, AuditList } from "../components/workspace";
import { AgentFlow } from "../components/agent-flow";

export function Overview({ data, workspace, openBlueprint }: Shared) {
  const navigate = useNavigate();
  const published = data.versions.filter(
    (v) => v.status === "published",
  ).length;

  const pendingApprovals = data.versions.filter(
    (v) => v.status === "draft" && v.bench_eligible,
  ).length;

  const activeProject =
    workspace.projects.find((p) => p.id === workspace.organization?.id) ||
    workspace.projects[0];

  return (
    <div className="overview-page studio-control-center">
      {/* Studio Control Center Hero */}
      <div className="studio-hero">
        <div className="studio-hero-meta">
          <span className="studio-live-pill">
            <span className="pulse-indicator" />
            CONTROL CENTER · ARYN STUDIO OPERATIONAL
          </span>
          <span className="studio-project-tag">
            <Radio size={12} />
            {activeProject?.name || "Laboratorium Riset"}
          </span>
        </div>
        <PageHeading
          eyebrow="ARYN STUDIO CONTROL CENTER"
          title="Ruang kerja agent Anda."
          description="Pusat kendali operasional arsitektur agen, verifikasi Bench, dan telemetri runtime terisolasi."
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
        <div
          className="hud-card hud-card-interactive"
          tabIndex={0}
          role="button"
          aria-label="Buka Agent Factory"
          onClick={() => navigate("/factory")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/factory");
            }
          }}
        >
          <div className="hud-header">
            <div className="hud-icon hud-icon-violet">
              <Bot size={17} />
            </div>
            <span className="hud-badge hud-badge-violet">Factory</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">{number(data.blueprints.length)}</strong>
            <span className="hud-title">Blueprint Agent</span>
            <p className="hud-desc">Arsitektur & peran aktif</p>
          </div>
          <div className="hud-footer">
            <span>{published} versi dipublikasikan</span>
            <ChevronRight size={14} />
          </div>
        </div>

        {/* Runtime & Hermes Confinement */}
        <div
          className="hud-card hud-card-interactive"
          tabIndex={0}
          role="button"
          aria-label="Buka riwayat Eksekusi"
          onClick={() => navigate("/runs")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/runs");
            }
          }}
        >
          <div className="hud-header">
            <div className="hud-icon hud-icon-cyan">
              <Workflow size={17} />
            </div>
            <span className="hud-badge hud-badge-cyan">Runtime</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">{number(data.runs.length)}</strong>
            <span className="hud-title">Eksekusi Tersimpan</span>
            <p className="hud-desc">Jejak eksekusi terverifikasi Core</p>
          </div>
          <div className="hud-footer">
            <span className="text-success flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
              Hermes {workspace.runtime.ready ? "Siap Confinement" : "Siaga"}
            </span>
            <ChevronRight size={14} />
          </div>
        </div>

        {/* Governance & Core Integrity */}
        <div
          className="hud-card hud-card-interactive"
          tabIndex={0}
          role="button"
          aria-label="Buka Tata Kelola"
          onClick={() => navigate("/governance")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/governance");
            }
          }}
        >
          <div className="hud-header">
            <div className="hud-icon hud-icon-emerald">
              <ShieldCheck size={17} />
            </div>
            <span className="hud-badge stat-pill-emerald">Core Security</span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric text-success">
              {workspace.runtime.ready ? "100%" : "Siaga"}
            </strong>
            <span className="hud-title">Integritas Audit</span>
            <p className="hud-desc">Kebijakan lokal terisolasi & diaudit</p>
          </div>
          <div className="hud-footer">
            <span>{number(data.audit.length)} jejak peristiwa</span>
            <ChevronRight size={14} />
          </div>
        </div>

        {/* Bench & Pending Approvals */}
        <div
          className="hud-card hud-card-interactive"
          tabIndex={0}
          role="button"
          aria-label="Buka Persetujuan"
          onClick={() => navigate("/approvals")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/approvals");
            }
          }}
        >
          <div className="hud-header">
            <div className="hud-icon hud-icon-amber">
              <Beaker size={17} />
            </div>
            <span className="hud-badge hud-badge-amber">
              {pendingApprovals > 0 ? "Perlu Tinjauan" : "Siaga"}
            </span>
          </div>
          <div className="hud-body">
            <strong className="hud-metric">
              {number(pendingApprovals)}
            </strong>
            <span className="hud-title">Menunggu Persetujuan</span>
            <p className="hud-desc">Lulus Bench & siap tinjauan Core</p>
          </div>
          <div className="hud-footer">
            <span>{data.evaluations.length} evaluasi Bench</span>
            <ChevronRight size={14} />
          </div>
        </div>
      </div>

      <div className="overview-content">
        {/* Lifecycle Studio Flow Panel */}
        <Panel
          className="overview-flow-panel"
          title="Dari ide ke eksekusi"
          subtitle="Tujuh tahap untuk merancang, memvalidasi, dan mengoperasikan agent."
          action={<span className="subtle-label">7 TAHAP</span>}
        >
          <AgentFlow />
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
                            {bp.description || bp.slug || "Blueprint riset teks"}
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
                subtitle="Hasil pemrosesan model aktual melalui Hermes."
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
                    <div
                      key={r.id}
                      className="recent-run-item"
                      onClick={() => navigate(`/runs?hasil=${r.id}`)}
                    >
                      <div className="run-stream-top">
                        <span className="mono text-xs text-secondary">{r.id}</span>
                        <Status value={r.status} />
                      </div>
                      <p className="run-stream-prompt line-clamp-2">{r.prompt}</p>
                      <div className="run-stream-meta">
                        <span className="mono text-xs">{r.model}</span>
                        <span className="text-xs text-secondary">
                          {number(r.total_tokens || 0)} token
                        </span>
                        <span className="text-xs text-secondary">{date(r.created_at)}</span>
                      </div>
                    </div>
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
