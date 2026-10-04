import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  FlaskConical,
  GitBranch,
  Play,
  ShieldCheck,
  Upload,
  UsersRound,
} from "lucide-react";

const stages = [
  {
    title: "Blueprint",
    description: "Tujuan dan peran",
    icon: BookOpen,
    path: "/factory",
    module: "Agent Factory",
  },
  {
    title: "Versi",
    description: "Konfigurasi tetap",
    icon: GitBranch,
    path: "/factory",
    module: "Agent Factory",
  },
  {
    title: "Bench",
    description: "Wajib lulus",
    icon: FlaskConical,
    path: "/bench",
    module: "Bench",
  },
  {
    title: "Persetujuan",
    description: "Tinjauan Core",
    icon: ShieldCheck,
    path: "/approvals",
    module: "Persetujuan",
  },
  {
    title: "Publikasi",
    description: "Versi siap pakai",
    icon: Upload,
    path: "/factory",
    module: "Agent Factory",
  },
  {
    title: "Penugasan",
    description: "Lingkup proyek",
    icon: UsersRound,
    path: "/factory",
    module: "Agent Factory",
  },
  {
    title: "Eksekusi",
    description: "Hermes dan audit",
    icon: Play,
    path: "/runs",
    module: "Eksekusi",
  },
];

export function AgentFlow() {
  return (
    <div className="agent-flow">
      <div className="flow-phases" aria-hidden="true">
        <span>Rancang</span>
        <span>Validasi</span>
        <span>Operasikan</span>
      </div>
      <ol
        className="flow-chart"
        aria-label="Alur agent dari blueprint hingga eksekusi"
      >
        {stages.map((stage, index) => (
          <li className={`flow-step flow-step-${index + 1}`} key={stage.title}>
            <Link
              className="flow-node"
              to={stage.path}
              aria-label={`Tahap ${index + 1}: ${stage.title} — buka ${stage.module}`}
            >
              <div className="flow-node-top" aria-hidden="true">
                <stage.icon size={18} />
                <span>{String(index + 1).padStart(2, "0")}</span>
              </div>
              <div className="flow-node-label">
                <strong>{stage.title}</strong>
                <span>{stage.description}</span>
              </div>
            </Link>
            {index < stages.length - 1 && (
              <span className="flow-connector" aria-hidden="true">
                <ArrowRight size={14} />
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
