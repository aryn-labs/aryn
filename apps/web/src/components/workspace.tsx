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
  "core.run.denied": "Eksekusi ditolak",
  "studio.run.assignment": "Hasil dikaitkan dengan penugasan",
  "studio.permission.denied": "Akses proyek ditolak",
  "bench.evaluation.interrupted": "Evaluasi terhenti",
};

export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
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
              <time>{date(e.occurred_at)}</time>
            </div>
            <div className="event-meta mono">{e.resource_id}</div>
            {!compact && (
              <details>
                <summary>
                  Detail audit <span className="mono">{e.event_type}</span>
                </summary>
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
              </details>
            )}
          </div>
          <Status value={e.status} />
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
