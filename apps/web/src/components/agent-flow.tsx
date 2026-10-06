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
    phase: "rancang",
  },
  {
    title: "Versi",
    description: "Konfigurasi tetap",
    icon: GitBranch,
    path: "/factory",
    module: "Agent Factory",
    phase: "rancang",
  },
  {
    title: "Bench",
    description: "Wajib lulus",
    icon: FlaskConical,
    path: "/bench",
    module: "Bench",
    phase: "validasi",
  },
  {
    title: "Persetujuan",
    description: "Tinjauan Core",
    icon: ShieldCheck,
    path: "/approvals",
    module: "Persetujuan",
    phase: "validasi",
  },
  {
    title: "Publikasi",
    description: "Versi siap pakai",
    icon: Upload,
    path: "/factory",
    module: "Agent Factory",
    phase: "operasikan",
  },
  {
    title: "Penugasan",
    description: "Lingkup proyek",
    icon: UsersRound,
    path: "/factory",
    module: "Agent Factory",
    phase: "operasikan",
  },
  {
    title: "Eksekusi",
    description: "ARYN Runtime dan audit",
    icon: Play,
    path: "/runs",
    module: "Eksekusi",
    phase: "operasikan",
  },
];

export function AgentFlow() {
  return (
    <div className="agent-flow">
      <div className="flow-phases" aria-hidden="true">
        <span className="phase-pill phase-rancang">
          <span className="phase-dot" />
          Rancang
        </span>
        <span className="phase-pill phase-validasi">
          <span className="phase-dot" />
          Validasi
        </span>
        <span className="phase-pill phase-operasikan">
          <span className="phase-dot" />
          Operasikan
        </span>
      </div>
      <ol
        className="flow-chart"
        aria-label="Alur agent dari blueprint hingga eksekusi"
      >
        {stages.map((stage, index) => (
          <li
            className={`flow-step flow-step-${index + 1} phase-${stage.phase}`}
            key={stage.title}
            data-phase={stage.phase}
          >
            <Link
              className="flow-node"
              to={stage.path}
              aria-label={`Tahap ${index + 1}: ${stage.title} — buka ${stage.module}`}
            >
              <div className="flow-node-top" aria-hidden="true">
                <div className="flow-icon-wrap">
                  <stage.icon size={17} />
                </div>
                <span className="flow-step-idx">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <div className="flow-node-label">
                <strong>{stage.title}</strong>
                <span>{stage.description}</span>
              </div>
            </Link>
            {index < stages.length - 1 && (
              <span className="flow-connector" aria-hidden="true">
                <span className="flow-connector-line" />
                <ArrowRight size={14} className="flow-connector-arrow" />
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
