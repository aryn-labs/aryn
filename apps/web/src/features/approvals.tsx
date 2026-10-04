import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Fingerprint, ShieldCheck } from "lucide-react";
import { date } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Empty, PageHeading, Status } from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel } from "../components/workspace";
export function Approvals({ data }: Shared) {
  const [view, setView] = useState("pending");
  const navigate = useNavigate();
  const candidates = data.versions.filter(
    (v) => ["draft", "approved"].includes(v.status) && v.bench_eligible,
  );
  return (
    <>
      <PageHeading
        eyebrow="KENDALI MANUSIA"
        title="Persetujuan"
        description="Tinjau hasil Bench dan konfigurasi yang tepat sebelum publikasi."
      />
      <div className="tabs">
        <button
          className={view === "pending" ? "selected" : ""}
          onClick={() => setView("pending")}
        >
          Perlu ditinjau <span className="count-pill">{candidates.length}</span>
        </button>
        <button
          className={view === "history" ? "selected" : ""}
          onClick={() => setView("history")}
        >
          Riwayat persetujuan{" "}
          <span className="count-pill">{data.approvals.length}</span>
        </button>
      </div>
      <Panel
        title={
          view === "pending" ? "Versi siap ditinjau" : "Persetujuan tercatat"
        }
      >
        {view === "pending" ? (
          candidates.length ? (
            <div className="approval-list">
              {candidates.map((v) => (
                <div key={v.id}>
                  <div className="approval-icon">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <strong>
                      {
                        data.blueprints.find((b) => b.id === v.blueprint_id)
                          ?.name
                      }
                    </strong>
                    <small>v{v.version_number} · Bench terakhir lulus</small>
                    <code className="hash-short">{v.payload_hash}</code>
                  </div>
                  <Status value={v.status} />
                  <Button
                    variant="secondary"
                    onClick={() =>
                      navigate(`/factory/${v.blueprint_id}?versi=${v.id}`)
                    }
                  >
                    Tinjau versi
                    <ArrowRight size={14} />
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Tidak ada versi yang menunggu tinjauan"
              description="Versi baru muncul di sini setelah evaluasi Bench terakhir lulus seluruh skenario."
            />
          )
        ) : data.approvals.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent / versi</th>
                  <th>Disetujui oleh</th>
                  <th>Catatan</th>
                  <th>Waktu</th>
                </tr>
              </thead>
              <tbody>
                {data.approvals.map((a) => {
                  const v = data.versions.find((v) => v.id === a.target_id);
                  return (
                    <tr key={a.id}>
                      <td>
                        <Link
                          to={`/factory/${v?.blueprint_id}?versi=${a.target_id}`}
                        >
                          {data.blueprints.find((b) => b.id === v?.blueprint_id)
                            ?.name || a.target_id}
                        </Link>
                        <small className="table-sub mono">
                          v{v?.version_number}
                        </small>
                      </td>
                      <td className="mono">{a.approved_by}</td>
                      <td>
                        {a.comments}
                        {!a.verified && (
                          <small className="table-sub">
                            Persetujuan belum berlaku untuk bukti saat ini.
                          </small>
                        )}
                      </td>
                      <td className="subtle">{date(a.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Belum ada persetujuan"
            description="Keputusan manusia beserta hash konfigurasi akan tersimpan di sini."
          />
        )}
      </Panel>
      <div className="page-footnote">
        <Fingerprint size={15} />
        Persetujuan terikat SHA-256. Agent tidak dapat menyetujui atau
        memublikasikan dirinya sendiri.
      </div>
    </>
  );
}
