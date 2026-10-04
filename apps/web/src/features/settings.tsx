import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  FileText,
  Moon,
  Radio,
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
              <dt>Hermes</dt>
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
              <dt>Gemini</dt>
              <dd>Spesifikasi tersedia; belum terintegrasi live.</dd>
              <dt>Ollama</dt>
              <dd>Belum tersedia.</dd>
            </dl>
            <p className="subtle">
              Kredensial Hermes dibaca server dari lingkungan lokal yang sudah
              ada. Kunci dan identity signing secret tidak dikirim ke browser.
            </p>
          </div>
        </Panel>
      </div>
    </>
  );
}

export function Unavailable({ module }: { module: string }) {
  return (
    <>
      <PageHeading
        title={module}
        description={
          module === "Brief"
            ? "Bukti, provenance, dan sintesis yang dapat diverifikasi."
            : "Investigasi insiden dan remediasi dengan persetujuan."
        }
      />
      <Panel title="Belum tersedia di Studio">
        <div className="unavailable">
          <div className="empty-icon">
            {module === "Brief" ? <FileText size={28} /> : <Radio size={28} />}
          </div>
          <span className="subtle-label">BELUM DIIMPLEMENTASIKAN</span>
          <h2>
            {module === "Brief"
              ? "Fondasi bukti akan hadir di sini."
              : "Investigasi akan memiliki ruang kerjanya sendiri."}
          </h2>
          <p>
            {module === "Brief"
              ? "Layanan Brief belum diimplementasikan di repository. Belum ada evidence bundle, kutipan, atau pemeriksaan kontradiksi yang dapat dijalankan."
              : "Layanan Relay belum diimplementasikan di repository. Investigasi, tindakan remediasi, dan pembuktian pemulihan belum dapat dijalankan."}
          </p>
          <div className="unavailable-footer">
            <ShieldCheck size={16} />
            <span>
              Fokus Studio saat ini: Factory → Bench → Persetujuan → Eksekusi.
            </span>
          </div>
          <Link to="/factory" className="text-link">
            Buka Agent Factory
            <ArrowRight size={15} />
          </Link>
        </div>
      </Panel>
    </>
  );
}
