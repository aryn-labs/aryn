import { type ReactNode } from "react";
import { Activity, Check, ChevronRight } from "lucide-react";
import type { Audit } from "../lib/types";
import { date } from "../lib/utils";
import { Empty, Status } from "./shared";

const steps = [
  "Blueprint",
  "Versi",
  "Bench",
  "Persetujuan",
  "Publikasi",
  "Penugasan",
  "Eksekusi",
];

export const eventNames: Record<string, string> = {
  "factory.blueprint.created": "Blueprint dibuat",
  "factory.version.created": "Versi disimpan",
  "bench.evaluation.completed": "Evaluasi Bench selesai",
  "factory.version.approved": "Versi disetujui",
  "factory.version.published": "Versi dipublikasikan",
  "factory.agent.assigned": "Agent ditugaskan",
  "core.approval.granted": "Persetujuan Core dicatat",
  "core.run.initiated": "Eksekusi dimulai",
  "core.run.completed": "Eksekusi selesai",
  "core.run.failed": "Eksekusi gagal",
  "core.run.recovered": "Eksekusi terputus dipulihkan sebagai gagal",
  "core.run.cancelled": "Pembatalan dikonfirmasi runtime",
  "core.run.cancellation.requested": "Pembatalan diminta; belum dikonfirmasi",
  "core.run.cancellation.unavailable": "Pembatalan runtime belum tersedia",
  "core.run.denied": "Eksekusi ditolak",
  "studio.run.assignment": "Hasil dikaitkan dengan penugasan",
  "studio.permission.denied": "Akses proyek ditolak",
  "bench.evaluation.interrupted": "Evaluasi terhenti",
  "bench.baseline.accepted": "Baseline diterima",
  "bench.baseline.superseded": "Baseline digantikan",
  "bench.regression.compared": "Baseline dan candidate dibandingkan",
  "bench.regression.critical": "Regression kritis terdeteksi",
  "bench.promotion.blocked": "Promotion diblokir oleh regression gate",
};

export function Panel({
  id,
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  id?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Lifecycle({ current = 0 }: { current?: number }) {
  return (
    <ol className="lifecycle" aria-label="Tahapan siklus agent">
      {steps.map((s, i) => (
        <li
          key={s}
          className={i < current ? "done" : i === current ? "current" : ""}
        >
          <span>{i < current ? <Check size={12} /> : i + 1}</span>
          {s}
          {i < steps.length - 1 && (
            <ChevronRight size={13} className="step-arrow" />
          )}
        </li>
      ))}
    </ol>
  );
}

export function AuditList({
  events,
  compact = false,
}: {
  events: Audit[];
  compact?: boolean;
}) {
  return events.length ? (
    <div className="audit-list">
      {(compact ? events.slice(0, 6) : events).map((e) => (
        <div className="audit-event" key={e.id}>
          <div className={`event-dot event-${e.status}`}>
            <Activity size={14} />
          </div>
          <div className="event-content">
            <div className="event-top">
              <span>{eventNames[e.event_type] || "Aktivitas Core"}</span>
              {!compact && <Status value={e.status} />}
            </div>
            <div className="event-meta">
              <span className="mono">{e.resource_id}</span>
              <time>{date(e.occurred_at)}</time>
            </div>
            {!compact && (
              <details className="audit-details">
                <summary className="audit-toggle">
                  <ChevronRight
                    size={13}
                    className="audit-chevron"
                    aria-hidden="true"
                  />
                  <span className="audit-show-label">Detail audit</span>
                  <span className="audit-hide-label">Tutup detail</span>
                </summary>
                <div className="audit-detail-body">
                  <div className="audit-detail-heading">
                    <span>Peristiwa Core</span>
                    <code>{e.event_type}</code>
                  </div>
                  <dl className="definition-grid">
                    <dt>Aktor</dt>
                    <dd className="mono">{e.actor_id}</dd>
                    <dt>Korelasi</dt>
                    <dd className="mono">{e.correlation_id}</dd>
                    <dt>Integritas</dt>
                    <dd className="mono wrap">{e.integrity_reference}</dd>
                  </dl>
                  <pre className="code-output">
                    {JSON.stringify(e.redacted_payload, null, 2)}
                  </pre>
                </div>
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  ) : (
    <Empty
      title="Belum ada aktivitas"
      description="Setiap aksi yang diproses Core akan meninggalkan jejak audit di sini."
    />
  );
}
