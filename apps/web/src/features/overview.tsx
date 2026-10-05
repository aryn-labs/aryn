import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  ChevronRight,
  GitBranch,
  Plus,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { number } from "../lib/utils";
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

  return (
    <div className="overview-page">
      <div className="studio-hero">
        <div className="studio-hero-meta">
          <span className="studio-live-pill">
            <span className="pulse-indicator" />
            STUDIO AKTIF · WORKSPACE CENTRAL
          </span>
        </div>
        <PageHeading
          eyebrow="ARYN STUDIO"
          title="Ruang kerja agent Anda."
          description="Rancang, evaluasi, dan operasikan agent dengan kendali yang jelas."
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

      <div className="overview-strip">
        <div
          className="stat-card stat-card-interactive"
          tabIndex={0}
          onClick={() => navigate("/factory")}
          role="button"
          aria-label="Buka Agent Factory"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/factory");
            }
          }}
        >
          <div className="stat-top">
            <div className="stat-icon-wrapper stat-icon-violet">
              <Bot size={18} />
            </div>
            <span className="stat-pill-tag">Factory</span>
          </div>
          <strong className="stat-number">{number(data.blueprints.length)}</strong>
          <span className="stat-title">Blueprint agent</span>
          <p className="stat-subtext">Definisi arsitektur & peran aktif</p>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <div className="stat-icon-wrapper stat-icon-cyan">
              <GitBranch size={18} />
            </div>
            <span className="stat-pill-tag stat-pill-cyan">Governed</span>
          </div>
          <strong className="stat-number">{number(published)}</strong>
          <span className="stat-title">Versi dipublikasikan</span>
          <p className="stat-subtext">Lulus Bench & disetujui Core</p>
        </div>

        <div
          className="stat-card stat-card-interactive"
          tabIndex={0}
          onClick={() => navigate("/runs")}
          role="button"
          aria-label="Buka riwayat Eksekusi"
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              navigate("/runs");
            }
          }}
        >
          <div className="stat-top">
            <div className="stat-icon-wrapper stat-icon-blue">
              <Workflow size={18} />
            </div>
            <span className="stat-pill-tag stat-pill-blue">Runtime</span>
          </div>
          <strong className="stat-number">{number(data.runs.length)}</strong>
          <span className="stat-title">Eksekusi tersimpan</span>
          <p className="stat-subtext">Riwayat eksekusi terverifikasi Core</p>
        </div>

        <div className="stat-card">
          <div className="stat-top">
            <div className="stat-icon-wrapper stat-icon-emerald">
              <ShieldCheck size={18} />
            </div>
            <span className="stat-pill-tag stat-pill-emerald">Core Security</span>
          </div>
          <strong className="stat-number text-success">
            {workspace.runtime.ready ? "100%" : "Siaga"}
          </strong>
          <span className="stat-title">Integritas Audit</span>
          <p className="stat-subtext">Kebijakan lokal terisolasi & diaudit</p>
        </div>

        <div className="data-source">
          <span className="connection-dot" />
          <span>Data proyek aktual</span>
        </div>
      </div>

      <div className="overview-content">
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
                            {bp.description || "Blueprint riset teks"}
                          </small>
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
              <AuditList events={data.audit.slice(0, 4)} compact />
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
