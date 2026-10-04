import { Link, useNavigate } from "react-router-dom";
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
import { Panel, Lifecycle, AuditList } from "../components/workspace";
export function Overview({ data, workspace, openBlueprint }: Shared) {
  const navigate = useNavigate();
  const published = data.versions.filter(
    (v) => v.status === "published",
  ).length;
  return (
    <>
      <PageHeading
        eyebrow="ARYN STUDIO"
        title="Ruang kerja agent Anda."
        description="Rancang, evaluasi, dan operasikan agent dengan kendali yang jelas."
      >
        <Button
          onClick={openBlueprint}
          disabled={!data.permissions["run:create"]}
        >
          <Plus size={16} />
          Buat agent
        </Button>
      </PageHeading>
      <div className="overview-strip">
        <div>
          <Bot size={17} />
          <strong>{number(data.blueprints.length)}</strong>
          <span>Blueprint agent</span>
        </div>
        <div>
          <GitBranch size={17} />
          <strong>{number(published)}</strong>
          <span>Versi dipublikasikan</span>
        </div>
        <div>
          <Workflow size={17} />
          <strong>{number(data.runs.length)}</strong>
          <span>Eksekusi tersimpan</span>
        </div>
        <span className="data-source">Data proyek aktual</span>
      </div>
      <div className="overview-layout">
        <div>
          <Panel
            title="Dari ide ke eksekusi"
            subtitle="Satu alur, dengan evaluasi dan persetujuan di setiap batas."
            action={<span className="subtle-label">ALUR AGENT</span>}
          >
            <div className="workflow-intro">
              <div className="workflow-glyph">
                <Bot size={26} />
              </div>
              <div>
                <h3>Agent yang siap bekerja, dapat ditelusuri.</h3>
                <p>
                  Mulai dari blueprint. Simpan versi, jalankan Bench, lalu
                  publikasikan setelah mendapat persetujuan Core.
                </p>
              </div>
            </div>
            <Lifecycle />
            <div className="workflow-footer">
              <span>
                <ShieldCheck size={15} />
                Versi tetap · lingkup proyek · audit
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
          <Panel
            className="mt-6"
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
                {data.blueprints.slice(0, 5).map((bp) => {
                  const v = data.versions.find((v) => v.blueprint_id === bp.id);
                  return (
                    <button
                      className="agent-overview-item"
                      key={bp.id}
                      onClick={() => navigate(`/factory/${bp.id}`)}
                    >
                      <div className="agent-icon">
                        <Bot size={19} />
                      </div>
                      <div>
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
                      <ChevronRight size={16} />
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
        <div>
          <Panel
            title="Kesiapan lingkungan"
            subtitle="Status koneksi saat ini."
          >
            <div className="readiness">
              <div>
                <span className="connection-dot" />
                <span>ARYN API</span>
                <Status value="active" />
              </div>
              <div>
                <span
                  className={`connection-dot ${!workspace.runtime.ready ? "warning" : ""}`}
                />
                <span>Hermes {workspace.runtime.version || ""}</span>
                <span
                  className={`subtle ${workspace.runtime.ready ? "text-success" : ""}`}
                >
                  {workspace.runtime.ready ? "Siap" : "Belum siap"}
                </span>
              </div>
              <p>{workspace.runtime.message}</p>
            </div>
            <div className="security-note">
              <ShieldCheck size={16} />
              <p>
                Identitas development diterbitkan server. Seluruh operasi
                diproses melalui ARYN Core.
              </p>
            </div>
          </Panel>
          <Panel
            className="mt-6"
            title="Aktivitas terbaru"
            action={
              <Link
                to="/governance"
                className="icon-link"
                aria-label="Lihat seluruh audit"
              >
                <ArrowRight size={16} />
              </Link>
            }
          >
            <AuditList events={data.audit} compact />
          </Panel>
        </div>
      </div>
    </>
  );
}
