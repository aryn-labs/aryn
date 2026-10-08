import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleDashed,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { Button } from "./ui/button";
const labels: Record<string, string> = {
  draft: "Draf",
  evaluating: "Dievaluasi",
  approved: "Disetujui",
  published: "Dipublikasikan",
  rejected: "Ditolak",
  deprecated: "Diarsipkan",
  completed: "Selesai",
  failed: "Gagal",
  outcome_unknown: "Hasil belum dapat dipastikan",
  bench_passed: "Lulus",
  bench_unverified: "Tidak Terverifikasi",
  queued: "Antre",
  started: "Dimulai",
  running: "Berjalan",
  cancelled: "Dibatalkan",
  stopping: "Pembatalan diminta",
  attempted: "Dicoba",
  active: "Aktif",
  allowed: "Diizinkan",
  denied: "Ditolak",
};
export function Status({ value }: { value: string }) {
  return (
    <span className={`status status-${value}`}>
      <span />
      {labels[value] || value}
    </span>
  );
}
export const statusLabel = (value: string) => labels[value] || value;
export function Empty({
  title,
  description,
  action,
  onAction,
}: {
  title: string;
  description: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <CircleDashed size={25} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && (
        <Button variant="secondary" onClick={onAction}>
          {action}
          <ArrowRight size={15} />
        </Button>
      )}
    </div>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: React.ReactNode;
  tone?: "info" | "error" | "success" | "warning";
}) {
  return (
    <div
      className={`notice notice-${tone}`}
      role={tone === "error" ? "alert" : undefined}
    >
      {tone === "error" || tone === "warning" ? (
        <AlertTriangle size={17} />
      ) : tone === "success" ? (
        <Check size={17} />
      ) : (
        <ShieldCheck size={17} />
      )}
      <div>{children}</div>
    </div>
  );
}
export function Busy({ label = "Memuat data proyek…" }: { label?: string }) {
  return (
    <div className="busy" role="status">
      <Loader2 className="spin" size={20} />
      {label}
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export const scenarioNames: Record<string, string> = {
  scen_safety_injection_defense: "Ketahanan terhadap prompt injection",
  scen_tool_confinement_defense: "Pembatasan akses tool host",
  scen_research_accuracy_synthesis: "Akurasi dan sintesis riset",
  scen_grounded_abstention: "Abstensi tanpa bukti faktual",
};
export function failureReason(value?: string) {
  if (!value) return "Seluruh kriteria terpenuhi.";
  if (value.startsWith("Triggered forbidden pattern"))
    return "Respons memuat pola yang dilarang oleh skenario keselamatan.";
  if (value.startsWith("Did not match expected pattern"))
    return "Respons belum memenuhi pola jawaban yang diharapkan.";
  if (value.startsWith("Latency"))
    return "Waktu respons melebihi batas skenario.";
  if (value.startsWith("Runtime run status"))
    return "Runtime belum menyelesaikan skenario.";
  if (
    value.includes("ModelIdentityError") ||
    value.startsWith("Runtime model differs")
  )
    return "Model aktual berbeda dengan model yang disetujui. Evaluasi ditolak.";
  return "Eksekusi skenario gagal. Periksa kesiapan ARYN Runtime dan model yang dipilih.";
}
