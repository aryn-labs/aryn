import { gatewayStatus } from "../lib/studio-state";
import { Check, Moon, RefreshCw, Sun } from "lucide-react";
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
          title={
            workspace.mode === "hosted"
              ? "Lingkungan Hosted"
              : "Lingkungan Local"
          }
          action={
            <Button variant="ghost" size="sm" onClick={refresh}>
              <RefreshCw size={14} />
              Periksa kembali
            </Button>
          }
        >
          <div className="settings-content">
            <Notice>
              {workspace.mode === "hosted"
                ? "Identity berasal dari sesi Hosted server. Kesiapan IdP/TLS/VPS production memerlukan UAT terpisah."
                : "Local development eksplisit melalui loopback. Saat perangkat atau Core mati, pekerjaan terjadwal tidak berjalan."}
            </Notice>
            <dl className="definition-grid">
              <dt>API Studio</dt>
              <dd className="mono">{window.location.origin}</dd>
              <dt>ARYN Runtime</dt>
              <dd>{workspace.runtime.message}</dd>
              <dt>Batas output per eksekusi</dt>
              <dd>
                {data.budget
                  ? number(data.budget.max_tokens_per_run)
                  : "Belum tersedia"}{" "}
                token
              </dd>
              <dt>Token tercatat</dt>
              <dd>
                {data.budget
                  ? number(data.budget.cumulative_tokens)
                  : "Belum tersedia"}
              </dd>
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
