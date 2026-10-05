import { useSearchParams } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, X } from "lucide-react";
import type { Evaluation } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import {
  Empty,
  Notice,
  PageHeading,
  Status,
  scenarioNames,
  failureReason,
} from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel } from "../components/workspace";
export function evaluationStatus(evaluation: Evaluation) {
  if (
    !evaluation.passed ||
    evaluation.score < 1 ||
    evaluation.passed_scenarios < evaluation.total_scenarios
  )
    return "failed";
  return evaluation.verified ? "bench_passed" : "bench_unverified";
}
export function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  const status = evaluationStatus(evaluation);
  const unverified = status === "bench_unverified";
  const passed = status === "bench_passed";
  return (
    <Panel
      id="evaluasi-bench"
      title={
        unverified
          ? "Evaluasi tidak terverifikasi"
          : passed
            ? "Evaluasi lulus"
            : "Evaluasi belum lulus"
      }
      subtitle={`${date(evaluation.evaluated_at)} · ${evaluation.provenance.evaluation_version || "Provenance belum tersedia"}`}
      action={
        <div className="flex items-center gap-3">
          <Status value={status} />
          <span
            className={`score ${unverified ? "text-warning" : passed ? "text-success" : "text-error"}`}
          >
            {Math.round(evaluation.score * 100)}%
            <small>
              {evaluation.passed_scenarios}/{evaluation.total_scenarios}{" "}
              skenario
            </small>
          </span>
        </div>
      }
    >
      <div className="evaluation-notice">
        <Notice tone={unverified ? "warning" : passed ? "success" : "error"}>
          {unverified
            ? "Hasil historis tetap disimpan, tetapi bukti/provenance sudah tidak valid atau berasal dari format lama. Hasil ini tidak dapat digunakan untuk persetujuan atau publikasi. Jalankan Bench pada versi yang valid untuk memperoleh bukti terverifikasi."
            : passed
              ? "Seluruh skenario memenuhi kriteria. Versi dapat ditinjau untuk persetujuan."
              : "Publikasi diblokir. Tinjau respons dan alasan setiap kegagalan, lalu buat versi yang diperbaiki."}
        </Notice>
      </div>
      <div className="scenario-results">
        {evaluation.details.map((s) => (
          <details key={s.scenario_id} className="scenario-result">
            <summary>
              <div
                className={
                  s.passed ? "scenario-check success" : "scenario-check error"
                }
              >
                {s.passed ? <Check size={15} /> : <X size={15} />}
              </div>
              <div>
                <strong>
                  {scenarioNames[s.scenario_id] || "Skenario evaluasi"}
                </strong>
                <small>{failureReason(s.failure_reason)}</small>
              </div>
              <span className="mono subtle">{s.latency_seconds}s</span>
              <Status value={s.passed ? "completed" : "failed"} />
              <ChevronDown size={15} />
            </summary>
            <div className="scenario-output">
              <div className="output-meta">
                <span>
                  {evaluation.verified
                    ? "RESPONS MODEL AKTUAL"
                    : "RESPONS HISTORIS TERSIMPAN"}
                </span>
                <code>{s.actual_model || "Model belum dilaporkan"}</code>
                <span>{number(s.total_tokens || 0)} token</span>
              </div>
              <pre className="prompt-output">
                {s.actual_output || "Tidak ada respons dari runtime."}
              </pre>
            </div>
          </details>
        ))}
      </div>
      <div className="panel-footnote mono">
        {evaluation.id} · Model diminta:{" "}
        {evaluation.provenance.requested_model || "Tidak tercatat"}
      </div>
    </Panel>
  );
}

export function BenchPage({ data }: Pick<Shared, "data">) {
  const [params, setParams] = useSearchParams();
  const selected = data.evaluations.find(
    (e) => e.id === params.get("evaluasi"),
  );

  const viewEvaluation = (evalId: string) => {
    setParams({ evaluasi: evalId });
    setTimeout(() => {
      const target = document.getElementById("evaluasi-bench");
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        target.classList.remove("highlight-pulse");
        void target.offsetWidth;
        target.classList.add("highlight-pulse");
        setTimeout(() => target.classList.remove("highlight-pulse"), 1600);
      }
    }, 60);
  };

  return (
    <>
      <PageHeading
        eyebrow="EVALUASI"
        title="Bench"
        description="Bukti keselamatan dan kualitas, sebelum sebuah versi dipublikasikan."
      />
      <Notice>
        Suite riset v1 menjalankan empat skenario teks pada model yang dipilih.
        Seluruh toolset runtime harus nonaktif. Hasil ini bukan audit keamanan
        menyeluruh.
      </Notice>
      <Panel
        className="mt-6"
        title="Riwayat evaluasi"
        subtitle="Skor dan respons disimpan di database proyek."
      >
        {data.evaluations.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent / versi</th>
                  <th>Hasil</th>
                  <th>Skor</th>
                  <th>Skenario</th>
                  <th>Dievaluasi</th>
                  <th>
                    <span className="sr-only">Aksi</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.evaluations.map((e) => {
                  const v = data.versions.find((v) => v.id === e.version_id);
                  const isCurrent = selected?.id === e.id;
                  return (
                    <tr
                      key={e.id}
                      className={isCurrent ? "table-row-selected" : ""}
                    >
                      <td>
                        <strong>
                          {data.blueprints.find((b) => b.id === e.blueprint_id)
                            ?.name || e.blueprint_id}
                        </strong>
                        <small className="table-sub mono">
                          v{v?.version_number}
                        </small>
                      </td>
                      <td>
                        <Status value={evaluationStatus(e)} />
                      </td>
                      <td className="mono">{Math.round(e.score * 100)}%</td>
                      <td>
                        {e.passed_scenarios}/{e.total_scenarios}
                      </td>
                      <td className="subtle">{date(e.evaluated_at)}</td>
                      <td>
                        <Button
                          variant={isCurrent ? "secondary" : "ghost"}
                          size="sm"
                          onClick={() => viewEvaluation(e.id)}
                          aria-label={`Lihat hasil evaluasi ${e.id}`}
                        >
                          Lihat hasil
                          <ChevronRight size={14} />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Belum ada evaluasi Bench"
            description="Buat versi di Agent Factory, lalu jalankan evaluasi untuk melihat respons model dan skor aktual."
            action="Buka Agent Factory"
            onAction={() => window.location.assign("/factory")}
          />
        )}
      </Panel>
      {selected && (
        <div className="mt-6">
          <EvaluationPanel evaluation={selected} />
        </div>
      )}
    </>
  );
}
