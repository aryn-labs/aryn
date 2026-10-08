import { gatewayStatus } from "../lib/studio-state";
import {
  Check,
  FileText,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
} from "lucide-react";
import type { Snapshot, Workspace } from "../lib/types";
import { number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Notice, PageHeading } from "../components/shared";
import { Panel } from "../components/workspace";
export function SettingsPage({
  workspace,
  data,
  theme,
  setTheme,
  refresh,
}: {
  workspace: Workspace;
  data: Snapshot;
  theme: string;
  setTheme: (s: string) => void;
  refresh: () => void;
}) {
  return (
    <>
      <PageHeading
        title="Pengaturan"
        description="Preferensi tampilan dan kesiapan lingkungan lokal."
      />
      <div className="settings-layout">
        <Panel
          title="Tampilan"
          subtitle="Preferensi tersimpan pada browser ini."
        >
          <div className="settings-content">
            <div className="field-caption">TEMA ANTARMUKA</div>
            <div className="theme-options">
              {[
                ["dark", "Gelap", Moon],
                ["light", "Terang", Sun],
              ].map(([id, label, Icon]) => {
                const ThemeIcon = Icon as typeof Moon;
                return (
                  <button
                    key={String(id)}
                    aria-pressed={theme === id}
                    className={theme === id ? "selected" : ""}
                    onClick={() => setTheme(String(id))}
                  >
                    <ThemeIcon size={20} />
                    {String(label)}
                    {theme === id && <Check size={15} />}
                  </button>
                );
              })}
            </div>
            <p className="subtle">
              Geist untuk antarmuka. Geist Mono untuk ID, output teknis, dan
              audit.
            </p>
          </div>
        </Panel>
        <Panel
          title="Lingkungan development"
          action={
            <Button variant="ghost" size="sm" onClick={refresh}>
              <RefreshCw size={14} />
              Periksa kembali
            </Button>
          }
        >
          <div className="settings-content">
            <Notice>
              Ini adalah akses development lokal, tanpa autentikasi produksi.
              Layanan hanya berjalan di loopback.
            </Notice>
            <dl className="definition-grid">
              <dt>API Studio</dt>
              <dd className="mono">{window.location.origin}</dd>
              <dt>ARYN Runtime</dt>
              <dd>{workspace.runtime.message}</dd>
              <dt>Batas output per eksekusi</dt>
              <dd>{number(data.budget?.max_tokens_per_run || 4096)} token</dd>
              <dt>Token tercatat</dt>
              <dd>{number(data.budget?.cumulative_tokens || 0)}</dd>
              <dt>Toolset aktif</dt>
              <dd>
                {workspace.runtime.enabled_toolsets?.length
                  ? workspace.runtime.enabled_toolsets.join(", ")
                  : workspace.runtime.ready
                    ? "Tidak ada"
                    : "Belum dapat diperiksa"}
              </dd>
              <dt>Model Gateway</dt>
              <dd className={`text-${gatewayStatus(workspace).tone}`}>
                {gatewayStatus(workspace).label}
              </dd>
              <dt>Backend runtime</dt>
              <dd>Hermes</dd>
              <dt>Model ditemukan</dt>
              <dd>{workspace.models.length}</dd>
            </dl>
            <p className="subtle">
              Credential provider dikelola oleh Model Gateway. ARYN hanya
              menggunakan endpoint gateway dan credential akses gateway opsional
              di server. Kunci tidak dikirim ke browser, database, audit, atau
              log.
            </p>
          </div>
        </Panel>
      </div>
    </>
  );
}

export function Unavailable({ module }: { module: string }) {
  const descriptions: Record<string, string> = {
    Brief:
      "Layanan evidence bundle, provenance, dan pemeriksaan kontradiksi belum tersedia.",
    Relay:
      "Layanan investigasi, proposal remediasi, dan verifikasi pemulihan belum tersedia.",
    "Workflow Builder":
      "Graph workflow executable dan TaskExecution belum tersedia.",
    Automations:
      "Scheduler Core dengan recurrence dan occurrence durable belum tersedia.",
    Capabilities:
      "Registry capability belum tersedia. Native tool grants tetap dibatasi Core.",
    Outputs:
      "Registry artifact dan deliverable umum belum tersedia. Hasil run existing dapat dibaca melalui Eksekusi.",
    "Agent Operations":
      "Permukaan Operations belum tersedia. Penugasan dan eksekusi existing tersedia melalui Eksekusi.",
  };
  return (
    <>
      <PageHeading
        title={module}
        description="Permukaan kerja ARYN dengan otoritas Core."
      />
      <Panel title="Belum tersedia di Studio">
        <div className="unavailable">
          <div className="empty-icon">
            <FileText size={28} />
          </div>
          <span className="subtle-label">BELUM DIIMPLEMENTASIKAN</span>
          <h2>Belum tersedia</h2>
          <p>
            {descriptions[module] ||
              "Detail atau editor baru untuk resource ini belum tersedia. Tampilan existing tetap dapat diakses melalui navigasi utama."}
          </p>
          <div className="unavailable-footer">
            <ShieldCheck size={16} />
            <span>
              Tidak ada aksi fitur yang dapat dijalankan pada halaman ini.
            </span>
          </div>
        </div>
      </Panel>
    </>
  );
}
