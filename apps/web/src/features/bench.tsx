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
export function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  return (
    <Panel
      title={
        !evaluation.verified
          ? "Bukti evaluasi belum terverifikasi"
          : evaluation.verified && evaluation.passed
            ? "Evaluasi lulus"
            : "Evaluasi belum lulus"
      }
      subtitle={`${date(evaluation.evaluated_at)} · ${evaluation.provenance.evaluation_version || "Provenance belum tersedia"}`}
      action={
        <span
          className={`score ${evaluation.verified && evaluation.passed ? "text-success" : "text-error"}`}
        >
          {Math.round(evaluation.score * 100)}%
          <small>
            {evaluation.passed_scenarios}/{evaluation.total_scenarios} skenario
          </small>
        </span>
      }
    >
      <div className="evaluation-notice">
        <Notice
          tone={evaluation.verified && evaluation.passed ? "success" : "error"}
        >
          {!evaluation.verified
            ? "Bukti evaluasi belum terverifikasi untuk konfigurasi dan suite saat ini. Publikasi diblokir."
            : evaluation.passed
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
                <span>RESPONS MODEL AKTUAL</span>
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

export function BenchPage({ data }: Shared) {
  const [params, setParams] = useSearchParams();
  const selected = data.evaluations.find(
    (e) => e.id === params.get("evaluasi"),
  );
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
                  return (
                    <tr key={e.id}>
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
                        <Status
                          value={
                            e.verified && e.passed ? "completed" : "failed"
                          }
                        />
                      </td>
                      <td className="mono">{Math.round(e.score * 100)}%</td>
                      <td>
                        {e.passed_scenarios}/{e.total_scenarios}
                      </td>
                      <td className="subtle">{date(e.evaluated_at)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setParams({ evaluasi: e.id })}
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
