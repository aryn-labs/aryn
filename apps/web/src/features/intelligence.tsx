import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { workspaceKey } from "../lib/workspace-types";
import type { Shared } from "../lib/types";
import { date } from "../lib/utils";
import {
  evidenceStatuses,
  incidentStatuses,
  type Bundle,
  type Source,
  type Page,
  type Fixture,
  type Incident,
  type IncidentDetail,
  type TimelineEvent,
  type Capsule,
  type Replay,
} from "../lib/intelligence-types";
import { PageHeading, Notice, Busy, Empty, Status } from "../components/shared";
import { Panel as WorkspacePanel } from "../components/workspace";
import { Button } from "../components/ui/button";
import "./intelligence.css";

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <WorkspacePanel title={title} subtitle={subtitle}>
      <div className="intelligence-body">{children}</div>
    </WorkspacePanel>
  );
}
function ReadError({ error, retry }: { error: Error; retry: () => void }) {
  const status = error instanceof ApiError ? error.status : 0;
  return (
    <Panel
      title={
        status === 403
          ? "Akses evidence dibatasi"
          : status === 404
            ? "Sumber daya tidak tersedia"
            : "Data belum dapat diverifikasi"
      }
    >
      <Notice tone="error">{error.message}</Notice>
      <p>
        Periksa scope proyek dan koneksi sebelum menggunakan evidence atau
        melakukan aksi.
      </p>
      <Button onClick={retry}>Muat ulang data</Button>
    </Panel>
  );
}
function Pager({
  after,
  next,
  change,
}: {
  after: string;
  next?: string | null;
  change: (value: string) => void;
}) {
  return (
    <div className="intelligence-actions">
      <Button
        type="button"
        variant="secondary"
        disabled={!after}
        onClick={() => change("")}
      >
        Halaman pertama
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={!next}
        onClick={() => change(next!)}
      >
        Halaman berikutnya
      </Button>
    </div>
  );
}
function useActions(shared: Shared) {
  const client = useQueryClient();
  const org = shared.workspace.organization.id;
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      api<Record<string, unknown>>(
        `/projects/${shared.project}${path}`,
        body ?? {},
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["studio", org, shared.project] }),
    retry: false,
  });
  useEffect(() => {
    const guard = (event: Event) => {
      if (mutation.isPending) event.preventDefault();
    };
    window.addEventListener("aryn:scope-change", guard);
    return () => window.removeEventListener("aryn:scope-change", guard);
  }, [mutation.isPending]);
  return {
    ...mutation,
    action: (path: string, body?: unknown) =>
      mutation.mutateAsync({ path, body }),
  };
}
export function EvidenceLinks({
  organization,
  project,
  kind,
  id,
}: {
  organization: string;
  project: string;
  kind: "run" | "artifact" | "workflow_run" | "incident" | "capsule" | "replay";
  id: string;
}) {
  const [after, change] = useState("");
  const query = useQuery({
    queryKey: workspaceKey(
      organization,
      project,
      "evidence-links",
      kind,
      id,
      after,
    ),
    queryFn: ({ signal }) =>
      api<Page<Bundle>>(
        `/projects/${project}/brief-links?kind=${kind}&id=${encodeURIComponent(id)}&after=${encodeURIComponent(after)}`,
        undefined,
        signal,
      ),
    enabled: !!id,
    retry: false,
  });
  return (
    <Panel title="Evidence Brief terkait">
      {query.error ? (
        <ReadError error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Busy />
      ) : (
        <>
          <ul>
            {query.data.items.map((b) => (
              <li key={b.id}>
                <Link to={`/brief/${b.id}`}>{b.title}</Link> ·{" "}
                {b.evaluation.status}
              </li>
            ))}
          </ul>
          {!query.data.items.length && (
            <p>Belum ada EvidenceBundle yang mereferensikan ID ini.</p>
          )}
          <Pager after={after} next={query.data.next} change={change} />
        </>
      )}
    </Panel>
  );
}
export function Brief(shared: Shared) {
  const location = useLocation(),
    navigate = useNavigate();
  const id = location.pathname.split("/")[2] || "",
    base = `/projects/${shared.project}`;
  const [q, search] = useState(""),
    [status, filter] = useState(""),
    [after, change] = useState("");
  const [title, setTitle] = useState(""),
    [question, setQuestion] = useState(""),
    [predicate, setPredicate] = useState("contains_text"),
    [literal, setLiteral] = useState(""),
    [minimum, setMinimum] = useState(1),
    [selected, setSelected] = useState<string[]>([]),
    [sourceAfter, sourcePage] = useState("");
  const params = new URLSearchParams(location.search);
  const [sourceKind, setSourceKind] = useState<Source["source_ref"]["kind"]>(
      params.get("source_kind") === "run" ? "run" : "artifact",
    ),
    [sourceId, setSourceId] = useState(params.get("source_id") || "");
  const [workflowRun, setWorkflowRun] = useState(
    params.get("workflow_run") || "",
  );
  const [documentTitle, setDocumentTitle] = useState(""),
    [documentText, setDocumentText] = useState("");
  const org = shared.workspace.organization.id,
    mutation = useActions(shared),
    canEdit = !!shared.data.permissions["version:create"];
  const list = useQuery({
    queryKey: workspaceKey(org, shared.project, "brief", q, status, after),
    queryFn: ({ signal }) =>
      api<Page<Bundle>>(
        `${base}/brief?${new URLSearchParams({ q, status, after })}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const detail = useQuery({
    queryKey: workspaceKey(org, shared.project, "brief-detail", id),
    queryFn: ({ signal }) =>
      api<Bundle>(`${base}/brief/${id}`, undefined, signal),
    enabled: !!id,
    retry: false,
  });
  const sources = useQuery({
    queryKey: workspaceKey(org, shared.project, "brief-sources", sourceAfter),
    queryFn: ({ signal }) =>
      api<Page<Source>>(
        `${base}/brief/sources?after=${encodeURIComponent(sourceAfter)}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const error = id ? detail.error : list.error;
  const [healthTarget, setHealthTarget] = useState("");
  return (
    <div className="intelligence-workspace">
      <PageHeading
        eyebrow="INTELLIGENCE · BRIEF"
        title={
          id
            ? (!detail.error && detail.data?.title) || "EvidenceBundle"
            : "Brief"
        }
        description="Evidence terverifikasi, counterevidence, dan abstensi yang dapat ditelusuri."
      >
        <Link to="/brief">Seluruh bundle</Link>
      </PageHeading>
      {mutation.error && <Notice tone="error">{mutation.error.message}</Notice>}
      {error ? (
        <ReadError
          error={error}
          retry={() => void (id ? detail : list).refetch()}
        />
      ) : id ? (
        detail.data ? (
          <BundleView
            bundle={detail.data}
            base={base}
            organization={org}
            project={shared.project}
          />
        ) : (
          <Busy />
        )
      ) : (
        <>
          <Panel title="EvidenceBundle">
            <div className="intelligence-filters">
              <label>
                Cari bundle
                <input
                  value={q}
                  maxLength={100}
                  onChange={(e) => {
                    search(e.target.value);
                    change("");
                  }}
                />
              </label>
              <label>
                Status saat dikumpulkan
                <select
                  value={status}
                  onChange={(e) => {
                    filter(e.target.value);
                    change("");
                  }}
                >
                  <option value="">Semua status</option>
                  {evidenceStatuses.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            {list.isPending ? (
              <Busy />
            ) : list.data?.items.length ? (
              <div className="intelligence-table-wrap">
                <table>
                  <caption>
                    Bundle dalam proyek aktif · status terkini diverifikasi
                    ulang
                  </caption>
                  <thead>
                    <tr>
                      <th>Bundle</th>
                      <th>Status terkini</th>
                      <th>Coverage</th>
                      <th>Dikumpulkan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((b) => (
                      <tr key={b.id}>
                        <td>
                          <Link to={`/brief/${b.id}`}>{b.title}</Link>
                        </td>
                        <td>
                          <Status value={b.evaluation.status} />
                        </td>
                        <td>
                          {b.evaluation.coverage}/
                          {b.evaluation.required_coverage}
                        </td>
                        <td>{date(b.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Belum ada evidence bundle"
                description="Kumpulkan sumber yang diizinkan, lalu evaluasi hipotesis. Ketiadaan evidence menghasilkan abstensi."
              />
            )}
            <Pager after={after} next={list.data?.next} change={change} />
          </Panel>
          {canEdit && (
            <div className="intelligence-columns">
              <Panel title="Kumpulkan sumber internal">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void mutation
                      .action("/brief/sources", {
                        title: sourceId,
                        source_ref: { kind: sourceKind, id: sourceId },
                      })
                      .then(() => setSourceId(""))
                      .catch(() => {});
                  }}
                >
                  <label>
                    Jenis sumber
                    <select
                      value={sourceKind}
                      onChange={(e) =>
                        setSourceKind(e.target.value as typeof sourceKind)
                      }
                    >
                      <option value="artifact">Artifact ARYN</option>
                      <option value="run">Core Run</option>
                      <option value="demo_observation">
                        Observasi demo Relay
                      </option>
                      <option value="document">Dokumen demo</option>
                    </select>
                  </label>
                  <label>
                    ID sumber
                    <input
                      value={sourceId}
                      pattern="[A-Za-z0-9_-]{1,64}"
                      required
                      maxLength={64}
                      onChange={(e) => setSourceId(e.target.value)}
                    />
                  </label>
                  <Button disabled={mutation.isPending || !sourceId}>
                    Verifikasi & kumpulkan sumber
                  </Button>
                </form>
                <p>
                  Sumber diperiksa Core; referensi ID saja tidak membuktikan
                  authenticity.
                </p>
              </Panel>
              <Panel title="Dokumen demo scoped">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void mutation
                      .action("/brief/documents", {
                        title: documentTitle,
                        text: documentText,
                      })
                      .then((d) =>
                        mutation.action("/brief/sources", {
                          title: documentTitle,
                          source_ref: { kind: "document", id: d.id },
                        }),
                      )
                      .then(() => {
                        setDocumentText("");
                        setDocumentTitle("");
                      })
                      .catch(() => {});
                  }}
                >
                  <label>
                    Judul dokumen
                    <input
                      required
                      maxLength={160}
                      value={documentTitle}
                      onChange={(e) => setDocumentTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    Isi dokumen demo
                    <textarea
                      required
                      maxLength={16000}
                      value={documentText}
                      onChange={(e) => setDocumentText(e.target.value)}
                    />
                  </label>
                  <Button disabled={mutation.isPending}>
                    Simpan & kumpulkan dokumen
                  </Button>
                </form>
                <p>
                  Input pengguna dilabeli demo; provenance ini tidak membuktikan
                  kebenaran eksternal.
                </p>
              </Panel>
            </div>
          )}
          <Panel title="Evaluasi hipotesis">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void mutation
                  .action("/brief", {
                    title,
                    hypothesis: {
                      question,
                      predicate,
                      text: predicate === "contains_text" ? literal : "",
                      minimum_sources: minimum,
                      target_id:
                        predicate === "service_healthy" ? healthTarget : null,
                    },
                    source_ids: selected,
                    workflow_run_id: workflowRun || null,
                  })
                  .then((b) => navigate(`/brief/${b.id}`))
                  .catch(() => {});
              }}
            >
              <div className="intelligence-columns">
                <label>
                  Judul bundle
                  <input
                    required
                    maxLength={160}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </label>
                <label>
                  Pertanyaan hipotesis
                  <input
                    required
                    maxLength={500}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                  />
                </label>
                <label>
                  Predikat terukur
                  <select
                    value={predicate}
                    onChange={(e) => setPredicate(e.target.value)}
                  >
                    <option value="contains_text">
                      Pencarian teks literal
                    </option>
                    <option value="run_completed">Core Run selesai</option>
                    <option value="service_healthy">Health fixture demo</option>
                  </select>
                </label>
                <label>
                  Minimum origin sumber berbeda
                  <input
                    type="number"
                    min={1}
                    max={8}
                    required
                    value={minimum}
                    onChange={(e) => setMinimum(Number(e.target.value))}
                  />
                </label>
              </div>
              <label>
                ID workflow run terkait (opsional)
                <input
                  maxLength={64}
                  pattern="[A-Za-z0-9_-]{1,64}"
                  value={workflowRun}
                  onChange={(e) => setWorkflowRun(e.target.value)}
                />
              </label>
              {predicate === "contains_text" && (
                <label>
                  Teks literal
                  <input
                    required
                    maxLength={200}
                    value={literal}
                    onChange={(e) => setLiteral(e.target.value)}
                  />
                </label>
              )}
              {predicate === "service_healthy" && (
                <label>
                  ID target health demo
                  <input
                    required
                    pattern="[A-Za-z0-9_-]{1,64}"
                    maxLength={64}
                    value={healthTarget}
                    onChange={(e) => setHealthTarget(e.target.value)}
                  />
                </label>
              )}
              <fieldset>
                <legend>Sumber evidence (maksimum 16)</legend>
                {sources.error ? (
                  <Notice tone="error">{sources.error.message}</Notice>
                ) : sources.isPending ? (
                  <Busy />
                ) : (
                  sources.data?.items.map((s) => (
                    <label className="intelligence-check" key={s.id}>
                      <input
                        type="checkbox"
                        checked={selected.includes(s.id)}
                        disabled={
                          !canEdit ||
                          (!selected.includes(s.id) && selected.length >= 16)
                        }
                        onChange={(e) =>
                          setSelected((ids) =>
                            e.target.checked
                              ? [...ids, s.id]
                              : ids.filter((i) => i !== s.id),
                          )
                        }
                      />
                      <span>
                        {s.title}
                        <small>
                          {s.quality} · {s.source_ref.kind} · {s.id}
                        </small>
                      </span>
                    </label>
                  ))
                )}
                {!sources.data?.items.length && (
                  <p>
                    Belum ada sumber. Bundle kosong akan menghasilkan abstensi.
                  </p>
                )}
              </fieldset>
              <p>
                {selected.length} sumber dipilih. Core menghitung coverage dari
                origin yang berbeda.
              </p>
              <Pager
                after={sourceAfter}
                next={sources.data?.next}
                change={sourcePage}
              />
              <Button disabled={!canEdit || mutation.isPending}>
                Evaluasi & simpan bundle
              </Button>
            </form>
          </Panel>
        </>
      )}
    </div>
  );
}
function BundleView({
  bundle: b,
  base,
  organization,
  project,
}: {
  bundle: Bundle;
  base: string;
  organization: string;
  project: string;
}) {
  const e = b.evaluation;
  return (
    <>
      <Panel title="Hipotesis & coverage">
        <Status value={e.status} />
        <h3>{b.hypothesis.question}</h3>
        <p>
          Predikat: {b.hypothesis.predicate}
          {b.hypothesis.text && ` · Literal: ${b.hypothesis.text}`}
        </p>
        <p>
          Coverage: {e.coverage}/{e.required_coverage} origin fresh
          terverifikasi · {Math.max(0, e.required_coverage - e.coverage)} sumber
          masih diperlukan.
        </p>
        {e.abstention && <Notice tone="warning">{e.abstention}</Notice>}
        <dl className="definition-grid">
          <dt>Status koleksi</dt>
          <dd>{b.status}</dd>
          <dt>Dikumpulkan</dt>
          <dd>{date(b.created_at)}</dd>
          <dt>Diverifikasi ulang</dt>
          <dd>{date(e.evaluated_at)}</dd>
          <dt>Digest immutable</dt>
          <dd className="intelligence-wrap mono">{b.digest}</dd>
        </dl>
        {b.workflow && (
          <Link
            to={`/workflows/${b.workflow.workflow_id}?run=${b.workflow.id}`}
          >
            Workflow run · {b.workflow.id}
          </Link>
        )}
        <a href={`/api${base}/brief/${b.id}/download`} download>
          Download evidence JSON
        </a>
      </Panel>
      <Panel
        title="Evidence & counterevidence"
        subtitle="Integritas dan freshness diperiksa ulang pada setiap pembacaan."
      >
        {!e.items.length && (
          <Empty
            title="Tidak ada evidence"
            description="Evaluasi abstain. Tidak ada diagnosis yang diasumsikan."
          />
        )}
        {e.items.map((item) => (
          <EvidenceCard
            key={item.source_id}
            item={item}
            base={base}
            organization={organization}
            project={project}
          />
        ))}
      </Panel>
    </>
  );
}
function EvidenceCard({
  item,
  base,
  organization,
  project,
}: {
  item: Bundle["evaluation"]["items"][number];
  base: string;
  organization: string;
  project: string;
}) {
  const [open, setOpen] = useState(false);
  const source = useQuery({
    queryKey: workspaceKey(
      organization,
      project,
      "source-inspection",
      item.source_id,
    ),
    queryFn: ({ signal }) =>
      api<Source & { freshness: string }>(
        `${base}/brief/sources/${item.source_id}`,
        undefined,
        signal,
      ),
    enabled: open && item.integrity === "VERIFIED",
    retry: false,
  });
  const s = source.error ? undefined : source.data;
  return (
    <article className={`evidence-card evidence-${item.relationship}`}>
      <h3>
        {item.relationship === "support"
          ? "Evidence pendukung"
          : item.relationship === "conflict"
            ? "Counterevidence"
            : "Evidence netral"}
      </h3>
      <p className="intelligence-wrap mono">{item.source_id}</p>
      <p>
        {item.integrity} · {item.freshness}
      </p>
      <p>{item.reason}</p>
      {item.excerpt && <pre className="intelligence-json">{item.excerpt}</pre>}
      <p>
        Diamati: {item.observed_at ? date(item.observed_at) : "Tidak tersedia"}{" "}
        · Dikumpulkan:{" "}
        {item.collected_at ? date(item.collected_at) : "Tidak tersedia"}
      </p>
      <Button
        variant="secondary"
        disabled={item.integrity !== "VERIFIED"}
        onClick={() => setOpen(!open)}
      >
        {open ? "Tutup sumber" : "Periksa provenance sumber"}
      </Button>
      {open && (
        <div>
          {source.error ? (
            <Notice tone="error">{source.error.message}</Notice>
          ) : !s ? (
            <Busy />
          ) : (
            <>
              <h4>{s.title}</h4>
              <p>
                Quality: {s.quality} · Sanitized: {String(s.sanitized)} ·
                Freshness: {s.freshness}
              </p>
              <dl className="definition-grid">
                <dt>Origin</dt>
                <dd className="intelligence-wrap">
                  {s.source_ref.kind} · {s.source_ref.id}
                </dd>
                <dt>Digest origin</dt>
                <dd className="intelligence-wrap mono">{s.source_digest}</dd>
                <dt>Digest snapshot</dt>
                <dd className="intelligence-wrap mono">{s.digest}</dd>
                <dt>Batas usia</dt>
                <dd>{s.max_age_seconds} detik</dd>
              </dl>
              {s.source_ref.kind === "run" && (
                <Link to={`/runs/${s.source_ref.id}`}>Core Run asal</Link>
              )}
              {s.source_ref.kind === "artifact" && (
                <Link to={`/outputs/${s.source_ref.id}`}>Artifact asal</Link>
              )}
            </>
          )}
        </div>
      )}
    </article>
  );
}

export function Relay(shared: Shared) {
  const location = useLocation(),
    navigate = useNavigate(),
    org = shared.workspace.organization.id,
    base = `/projects/${shared.project}`;
  const id = location.pathname.split("/")[2] || "";
  const [q, search] = useState(""),
    [status, filter] = useState(""),
    [after, change] = useState("");
  const [demoName, setDemoName] = useState(""),
    [demoId, setDemoId] = useState(""),
    [blocking, setBlocking] = useState(false),
    [reason, setReason] = useState(""),
    [consent, setConsent] = useState(false),
    [timelineAfter, timelinePage] = useState("");
  const executionKey = useRef<{ proposal: string; key: string } | null>(null);
  const mutation = useActions(shared),
    canRun = !!shared.data.permissions["run:create"],
    canEdit = !!shared.data.permissions["version:create"],
    canApprove = !!shared.data.permissions["version:approve"];
  const list = useQuery({
    queryKey: workspaceKey(org, shared.project, "relay", q, status, after),
    queryFn: ({ signal }) =>
      api<Page<Incident>>(
        `${base}/relay?${new URLSearchParams({ q, status, after })}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const detail = useQuery({
    queryKey: workspaceKey(org, shared.project, "relay-detail", id),
    queryFn: ({ signal }) =>
      api<IncidentDetail>(`${base}/relay/${id}`, undefined, signal),
    enabled: !!id,
    retry: false,
    refetchInterval: 5000,
  });
  const demos = useQuery({
    queryKey: workspaceKey(org, shared.project, "relay-demos"),
    queryFn: ({ signal }) =>
      api<Page<Fixture>>(
        `${base}/relay/demo-fixtures?limit=100`,
        undefined,
        signal,
      ),
    enabled: !id && canEdit,
    retry: false,
  });
  const timeline = useQuery({
    queryKey: workspaceKey(
      org,
      shared.project,
      "relay-timeline",
      id,
      timelineAfter,
    ),
    queryFn: ({ signal }) =>
      api<Page<TimelineEvent>>(
        `${base}/relay/${id}/timeline?after=${encodeURIComponent(timelineAfter)}`,
        undefined,
        signal,
      ),
    enabled: !!id,
    retry: false,
  });
  // A failed read removes all action controls; cached records cannot authorize.
  const d = detail.error ? undefined : detail.data,
    error = id ? detail.error : list.error;
  useEffect(() => {
    setConsent(false);
  }, [d?.proposal?.payload_hash]);
  const selectedDemo = demos.data?.items.find((f) => f.id === demoId);
  const action = (suffix: string, body: unknown) =>
    mutation.action(`/relay/${id}/${suffix}`, body).catch(() => {});
  return (
    <div className="intelligence-workspace">
      <PageHeading
        eyebrow="RELIABILITY · RELAY"
        title={id ? d?.title || "Incident" : "Relay"}
        description="Investigasi read-only, persetujuan Core, dan recovery fixture demo terverifikasi."
      >
        <Link to="/relay">Seluruh incident</Link>
      </PageHeading>
      <Notice>
        Disposable demo saja. Aksi tetap restart_demo pada state database
        proyek; tidak ada akses host atau remediation production.
      </Notice>
      {mutation.error && <Notice tone="error">{mutation.error.message}</Notice>}
      {error ? (
        <ReadError
          error={error}
          retry={() => void (id ? detail : list).refetch()}
        />
      ) : id ? (
        !d ? (
          <Busy />
        ) : (
          <>
            <Panel title="Incident & original signal">
              <Status value={d.status} />
              <dl className="definition-grid">
                <dt>Severity</dt>
                <dd>{d.severity}</dd>
                <dt>Owner</dt>
                <dd className="intelligence-wrap mono">{d.owner_id}</dd>
                <dt>Diterima</dt>
                <dd>{date(d.created_at)}</dd>
                <dt>Diperbarui</dt>
                <dd>{date(d.updated_at)}</dd>
                <dt>Target demo</dt>
                <dd className="intelligence-wrap mono">
                  {d.target_id} · revision {d.fixture.revision}
                </dd>
                <dt>Health terkini</dt>
                <dd>
                  {d.fixture.running && !d.fixture.blocking_fault
                    ? "Healthy"
                    : "Unhealthy"}
                </dd>
                <dt>Original signal</dt>
                <dd className="intelligence-wrap mono">{d.signal_id}</dd>
                <dt>Dedup key</dt>
                <dd>{d.signal.dedup_key}</dd>
              </dl>
              <p>Original evidence: {d.signal.source_id}</p>
              {["OPEN", "INVESTIGATING", "PROPOSED", "DEGRADED"].includes(
                d.status,
              ) && (
                <Button
                  disabled={!canRun || !canEdit || mutation.isPending}
                  onClick={() =>
                    void action("investigate", {
                      expected_revision: d.revision,
                    })
                  }
                >
                  Investigasi read-only
                </Button>
              )}
              {d.status === "OUTCOME_UNKNOWN" && (
                <>
                  <Notice tone="warning">
                    Hasil belum diketahui. Aksi tidak diulang otomatis;
                    rekonsiliasi hanya memeriksa state dan health aktual.
                  </Notice>
                  <Button
                    disabled={!canApprove || mutation.isPending}
                    onClick={() =>
                      void action("reconcile", {
                        expected_revision: d.revision,
                      })
                    }
                  >
                    Rekonsiliasi health
                  </Button>
                </>
              )}
              {d.status === "RECOVERED" && (
                <Button
                  disabled={!canRun || mutation.isPending}
                  onClick={() =>
                    void action("close", { expected_revision: d.revision })
                  }
                >
                  Tutup incident terverifikasi
                </Button>
              )}
            </Panel>
            {d.bundle && (
              <>
                <Panel title="Hasil investigasi">
                  <Link to={`/brief/${d.bundle.id}`}>
                    Buka EvidenceBundle · {d.bundle.id}
                  </Link>
                  <p>
                    {d.bundle.evaluation.status} · Coverage{" "}
                    {d.bundle.evaluation.coverage}/
                    {d.bundle.evaluation.required_coverage}
                  </p>
                  {d.bundle.evaluation.abstention && (
                    <Notice tone="warning">
                      {d.bundle.evaluation.abstention}
                    </Notice>
                  )}
                  <p>
                    Kesimpulan hanya membahas health demo terukur. Root cause
                    production belum tersedia.
                  </p>
                </Panel>
                {d.status === "INVESTIGATING" && (
                  <Panel title="Proposal recovery terbatas">
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action("proposals", {
                          expected_revision: d.revision,
                          target_id: d.target_id,
                          target_revision: d.fixture.revision,
                          bundle_id: d.bundle_id,
                          action: "restart_demo",
                          reason,
                        });
                      }}
                    >
                      <p>
                        Action: restart_demo · Target revision{" "}
                        {d.fixture.revision} · Parameters: kosong.
                      </p>
                      <label>
                        Alasan proposal
                        <textarea
                          required
                          maxLength={1000}
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                        />
                      </label>
                      <Button
                        disabled={
                          !canRun ||
                          mutation.isPending ||
                          d.bundle!.evaluation.status ===
                            "INSUFFICIENT_EVIDENCE"
                        }
                      >
                        Buat proposal exact target
                      </Button>
                    </form>
                  </Panel>
                )}
              </>
            )}
            {d.proposal && (
              <Panel title="Review proposal & approval Core">
                <dl className="definition-grid">
                  <dt>Aksi</dt>
                  <dd>{d.proposal.action}</dd>
                  <dt>Target dan revisi</dt>
                  <dd className="intelligence-wrap">
                    {d.proposal.target_id} · {d.proposal.target_revision}
                  </dd>
                  <dt>Parameter</dt>
                  <dd>{JSON.stringify(d.proposal.parameters)}</dd>
                  <dt>Reversible intent</dt>
                  <dd>{d.proposal.reversible_intent}</dd>
                  <dt>Preconditions</dt>
                  <dd>{d.proposal.preconditions}</dd>
                  <dt>Health contract</dt>
                  <dd>
                    running = true dan blocking_fault = false, observasi
                    independen.
                  </dd>
                  <dt>Payload hash</dt>
                  <dd
                    className="intelligence-wrap mono"
                    data-testid="proposal-hash"
                  >
                    {d.proposal.payload_hash}
                  </dd>
                  <dt>Evidence digest</dt>
                  <dd className="intelligence-wrap mono">
                    {d.proposal.bundle_digest}
                  </dd>
                </dl>
                <p>{d.proposal.reason}</p>
                {d.status === "PROPOSED" && (
                  <>
                    <p>
                      {d.approval
                        ? `Approval Core terverifikasi: ${d.approval.approval_id} · ${d.approval.approved_by}`
                        : "Belum ada approval Core terverifikasi untuk hash ini."}
                    </p>
                    <label>
                      Alasan review manusia
                      <textarea
                        maxLength={1000}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </label>
                    <Button
                      disabled={
                        !canApprove ||
                        !reason.trim() ||
                        mutation.isPending ||
                        !!d.approval
                      }
                      onClick={() =>
                        void action("approve", {
                          payload_hash: d.proposal!.payload_hash,
                          reason,
                        })
                      }
                    >
                      Setujui hash proposal
                    </Button>
                    <label className="intelligence-check">
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(e) => setConsent(e.target.checked)}
                      />
                      <span>
                        Saya mengonfirmasi target demo dan hash proposal yang
                        ditampilkan.
                      </span>
                    </label>
                    <Button
                      disabled={
                        !canRun || !d.approval || !consent || mutation.isPending
                      }
                      onClick={() => {
                        if (executionKey.current?.proposal !== d.proposal!.id)
                          executionKey.current = {
                            proposal: d.proposal!.id,
                            key: crypto.randomUUID(),
                          };
                        void action("execute", {
                          proposal_id: d.proposal!.id,
                          payload_hash: d.proposal!.payload_hash,
                          idempotency_key: executionKey.current.key,
                        });
                      }}
                    >
                      Jalankan recovery demo
                    </Button>
                  </>
                )}
                {d.execution && (
                  <>
                    <h3>Execution evidence</h3>
                    <p>
                      {d.execution.status} · Revision{" "}
                      {d.execution.before_revision} →{" "}
                      {d.execution.after_revision ?? "belum diketahui"}
                    </p>
                    <p className="intelligence-wrap">
                      Core approval: {d.execution.approval.approval_id} ·{" "}
                      {d.execution.approval.approved_by}
                    </p>
                    {d.execution.error_code && (
                      <Notice tone="warning">{d.execution.error_code}</Notice>
                    )}
                  </>
                )}
                <h3>Verifikasi health independen</h3>
                {d.verification ? (
                  <p>
                    {d.verification.recovered
                      ? "RECOVERED · health contract terpenuhi"
                      : "DEGRADED · health contract gagal"}{" "}
                    · Observasi {d.verification.observation_id} · Target
                    revision {d.verification.target_revision}
                  </p>
                ) : (
                  <p>
                    Belum diverifikasi. Selesainya aksi belum membuktikan
                    recovery.
                  </p>
                )}
              </Panel>
            )}
            <Panel title="Timeline immutable">
              {timeline.error ? (
                <Notice tone="error">{timeline.error.message}</Notice>
              ) : timeline.isPending ? (
                <Busy />
              ) : (
                <>
                  <ol className="incident-timeline">
                    {[...timeline.data.items].reverse().map((t) => (
                      <li key={t.id}>
                        <strong>
                          {t.sequence}. {t.event}
                        </strong>
                        <p>
                          {t.from_status || "signal"} → {t.to_status}
                        </p>
                        <time>{date(t.created_at)}</time>
                        <p className="intelligence-wrap">
                          Aktor: {t.actor_id} · Referensi:{" "}
                          {t.reference_id || "Tidak tersedia"}
                        </p>
                      </li>
                    ))}
                  </ol>
                  <Pager
                    after={timelineAfter}
                    next={timeline.data.next}
                    change={timelinePage}
                  />
                </>
              )}
            </Panel>
            {d.capsule && (
              <Panel title="IncidentCapsule">
                <p className="intelligence-wrap mono">
                  {d.capsule.id} · {d.capsule.digest}
                </p>
                <p>
                  Snapshot asli sebelum aksi, sanitized, dan recovery
                  terverifikasi.
                </p>
                <div className="intelligence-actions">
                  <a
                    href={`/api${base}/relay/capsules/${d.capsule.id}/download`}
                    download
                  >
                    Download capsule JSON
                  </a>
                  <Link to={`/bench/replays?capsule=${d.capsule.id}`}>
                    Replay aman di Bench
                  </Link>
                  <Link to="/factory">
                    Factory · candidate harus melalui draft dan governance biasa
                  </Link>
                </div>
              </Panel>
            )}
          </>
        )
      ) : (
        <>
          <Panel title="Incident proyek aktif">
            <div className="intelligence-filters">
              <label>
                Cari incident
                <input
                  maxLength={100}
                  value={q}
                  onChange={(e) => {
                    search(e.target.value);
                    change("");
                  }}
                />
              </label>
              <label>
                Status incident
                <select
                  value={status}
                  onChange={(e) => {
                    filter(e.target.value);
                    change("");
                  }}
                >
                  <option value="">Semua status</option>
                  {incidentStatuses.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            {list.isPending ? (
              <Busy />
            ) : list.data?.items.length ? (
              <div className="intelligence-table-wrap">
                <table>
                  <caption>Signal demo yang benar-benar diterima</caption>
                  <thead>
                    <tr>
                      <th>Incident</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Owner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((i) => (
                      <tr key={i.id}>
                        <td>
                          <Link to={`/relay/${i.id}`}>{i.title}</Link>
                        </td>
                        <td>{i.severity}</td>
                        <td>
                          <Status value={i.status} />
                        </td>
                        <td className="intelligence-wrap">{i.owner_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="Belum ada incident"
                description="Tidak ada failure telemetry yang diterima dalam proyek ini. Buat fixture demo secara eksplisit untuk mencoba recovery."
              />
            )}
            <Pager after={after} next={list.data?.next} change={change} />
          </Panel>
          {canEdit && (
            <Panel title="Fixture demo disposable">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void mutation
                    .action("/relay/demo-fixtures", { name: demoName })
                    .then((r) => {
                      setDemoId((r.fixture as Fixture).id);
                      setDemoName("");
                    })
                    .catch(() => {});
                }}
              >
                <label>
                  Nama fixture demo
                  <input
                    required
                    maxLength={100}
                    value={demoName}
                    onChange={(e) => setDemoName(e.target.value)}
                  />
                </label>
                <Button disabled={mutation.isPending}>
                  Buat fixture healthy
                </Button>
              </form>
              {demos.error && (
                <Notice tone="error">{demos.error.message}</Notice>
              )}
              <label>
                Target fixture demo
                <select
                  value={demoId}
                  onChange={(e) => setDemoId(e.target.value)}
                >
                  <option value="">Pilih target</option>
                  {demos.data?.items.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} · r{f.revision} ·{" "}
                      {f.running && !f.blocking_fault ? "healthy" : "unhealthy"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="intelligence-check">
                <input
                  type="checkbox"
                  checked={blocking}
                  onChange={(e) => setBlocking(e.target.checked)}
                />
                <span>
                  Simulasikan blocking fault yang tetap gagal setelah restart.
                </span>
              </label>
              <div className="intelligence-actions">
                <Button
                  disabled={!selectedDemo || mutation.isPending}
                  onClick={() =>
                    void mutation
                      .action(`/relay/demo-fixtures/${demoId}`, {
                        expected_revision: selectedDemo!.revision,
                        running: false,
                        blocking_fault: blocking,
                      })
                      .catch(() => {})
                  }
                >
                  Hentikan fixture demo
                </Button>
                <Button
                  disabled={
                    !canRun ||
                    !selectedDemo ||
                    (selectedDemo.running && !selectedDemo.blocking_fault) ||
                    mutation.isPending
                  }
                  onClick={() =>
                    void mutation
                      .action("/relay/signals", {
                        target_id: demoId,
                        dedup_key: `demo-${demoId}-${selectedDemo!.revision}`,
                        severity: "medium",
                      })
                      .then((i) => navigate(`/relay/${i.id}`))
                      .catch(() => {})
                  }
                >
                  Terima signal demo
                </Button>
              </div>
              {demos.data?.next && (
                <p>
                  100 fixture terbaru ditampilkan. Gunakan API terpaginasikan
                  untuk inventory lebih besar.
                </p>
              )}
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

export function CapsuleReplays(shared: Shared) {
  const location = useLocation(),
    org = shared.workspace.organization.id,
    base = `/projects/${shared.project}`,
    navigate = useNavigate();
  const id = location.pathname.split("/")[3] || "",
    capsuleId = new URLSearchParams(location.search).get("capsule") || "";
  const [after, change] = useState("");
  const mutation = useActions(shared);
  const list = useQuery({
    queryKey: workspaceKey(org, shared.project, "capsule-replays", after),
    queryFn: ({ signal }) =>
      api<Page<Replay>>(
        `${base}/bench/replays?after=${encodeURIComponent(after)}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const detail = useQuery({
    queryKey: workspaceKey(org, shared.project, "capsule-replay", id),
    queryFn: ({ signal }) =>
      api<Replay>(`${base}/bench/replays/${id}`, undefined, signal),
    enabled: !!id,
    retry: false,
  });
  const capsule = useQuery({
    queryKey: workspaceKey(org, shared.project, "replay-capsule", capsuleId),
    queryFn: ({ signal }) =>
      api<Capsule>(
        `${base}/relay/capsules/${encodeURIComponent(capsuleId)}`,
        undefined,
        signal,
      ),
    enabled: !!capsuleId,
    retry: false,
  });
  const c = capsule.error ? undefined : capsule.data,
    r = detail.error ? undefined : detail.data,
    error = id ? detail.error : list.error;
  return (
    <div className="intelligence-workspace">
      <PageHeading
        eyebrow="BENCH · DIAGNOSTIC REPLAY"
        title="Capsule replay"
        description="Replay deterministik di memory, tanpa model/provider dan tanpa mutasi recovery live."
      >
        <Link to="/bench">Bench evaluasi agent</Link>
        <Link to="/bench/replays">Riwayat replay</Link>
      </PageHeading>
      {mutation.error && <Notice tone="error">{mutation.error.message}</Notice>}
      {capsule.error && (
        <ReadError error={capsule.error} retry={() => void capsule.refetch()} />
      )}
      {c && (
        <Panel title="Capsule terverifikasi">
          <Link to={`/relay/${c.incident_id}`}>
            Incident asal · {c.incident_id}
          </Link>
          <Link to={`/brief/${c.bundle_id}`}>EvidenceBundle asal</Link>
          <p className="intelligence-wrap mono">
            {c.id} · {c.digest}
          </p>
          <p>
            Scenario {c.scenario_id} · v{c.scenario_version}. Snapshot sebelum
            aksi: {JSON.stringify(c.snapshot)}.
          </p>
          <Button
            disabled={
              !shared.data.permissions["run:create"] || mutation.isPending
            }
            onClick={() =>
              void mutation
                .action(`/bench/capsules/${c.id}/replay`)
                .then((replay) => navigate(`/bench/replays/${replay.id}`))
                .catch(() => {})
            }
          >
            Jalankan replay memory
          </Button>
        </Panel>
      )}
      {error ? (
        <ReadError
          error={error}
          retry={() => void (id ? detail : list).refetch()}
        />
      ) : id ? (
        !r ? (
          <Busy />
        ) : (
          <>
            <Panel title="Hasil replay">
              <Status value={r.passed ? "bench_passed" : "failed"} />
              <p>
                Backend: {r.backend} · Model/provider: tidak digunakan · Live
                recovery write calls: {r.live_write_calls}
              </p>
              <Notice>
                Diagnostic evidence ini tidak mengizinkan promotion atau
                publication agent.
              </Notice>
              <p>
                Scenario {r.scenario_id} · v{r.scenario_version} ·{" "}
                {date(r.created_at)}
              </p>
              <p className="intelligence-wrap mono">
                Digest report: {r.digest}
              </p>
              <Link to={`/bench/replays?capsule=${r.capsule_id}`}>
                Capsule asli · {r.capsule_id}
              </Link>
              <ul>
                {r.graders.map((g, i) => (
                  <li key={i}>
                    <strong>
                      {g.grader_id || String(g.name || g.grader || "Grader")}
                    </strong>{" "}
                    · {g.passed ? "PASS" : "FAIL"}
                    <p>{g.reason}</p>
                    <details>
                      <summary>Evidence grader</summary>
                      <pre className="intelligence-json">
                        {JSON.stringify(g, null, 2)}
                      </pre>
                    </details>
                  </li>
                ))}
              </ul>
            </Panel>
            <EvidenceLinks
              organization={org}
              project={shared.project}
              kind="replay"
              id={r.id}
            />
          </>
        )
      ) : (
        <Panel title="Riwayat replay">
          {list.isPending ? (
            <Busy />
          ) : list.data?.items.length ? (
            <ul>
              {list.data.items.map((replay) => (
                <li key={replay.id}>
                  <Link to={`/bench/replays/${replay.id}`}>{replay.id}</Link> ·{" "}
                  {replay.passed ? "PASS" : "FAIL"} · {date(replay.created_at)}
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              title="Belum ada replay"
              description="Tutup incident yang sudah recovered, lalu gunakan capsule terverifikasi untuk replay aman."
            />
          )}
          <Pager after={after} next={list.data?.next} change={change} />
        </Panel>
      )}
    </div>
  );
}
