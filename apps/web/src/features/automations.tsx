import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { workspaceKey, routeIdentifier } from "../lib/workspace-types";
import type { Shared } from "../lib/types";
import type { Page } from "../lib/intelligence-types";
import type {
  Automation,
  AutomationInput,
  AutomationTarget,
  Occurrence,
  AutomationEvent,
  CapabilityRegistry,
} from "../lib/automation-types";
import { PageHeading, Notice, Empty, Busy, Status } from "../components/shared";
import { Panel as WorkspacePanel } from "../components/workspace";
import { Button } from "../components/ui/button";
import { date } from "../lib/utils";
import "./intelligence.css";

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <WorkspacePanel title={title}>
      <div className="intelligence-body">{children}</div>
    </WorkspacePanel>
  );
}
function ReadError({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <Panel
      title={
        error instanceof ApiError && error.status === 403
          ? "Akses proyek dibatasi"
          : "Data belum dapat diverifikasi"
      }
    >
      <Notice tone="error">{error.message}</Notice>
      <Button onClick={retry}>Muat ulang data</Button>
    </Panel>
  );
}
function Pager({
  after,
  next,
  set,
}: {
  after: string;
  next?: string | null;
  set: (value: string) => void;
}) {
  return (
    <div className="intelligence-actions">
      <Button variant="secondary" disabled={!after} onClick={() => set("")}>
        Halaman pertama
      </Button>
      <Button variant="secondary" disabled={!next} onClick={() => set(next!)}>
        Halaman berikutnya
      </Button>
    </div>
  );
}
function useRead<T>(
  shared: Shared,
  resource: string,
  path: string,
  enabled = true,
) {
  return useQuery({
    queryKey: workspaceKey(
      shared.workspace.organization.id,
      shared.project,
      resource,
      path,
    ),
    queryFn: ({ signal }) =>
      api<T>(`/projects/${shared.project}${path}`, undefined, signal),
    enabled,
    retry: false,
  });
}
function useAction(shared: Shared) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) =>
      api<Record<string, unknown>>(`/projects/${shared.project}${path}`, body),
    retry: false,
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ["studio", shared.workspace.organization.id, shared.project],
      }),
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
    action: (path: string, body: unknown) =>
      mutation.mutateAsync({ path, body }),
  };
}
const policy = {
  overlap: "skip",
  missed: "skip",
  catch_up_limit: 1,
  max_runs_per_day: 24,
  max_tokens_per_task: 4096,
  max_attempts: 1,
  backoff_seconds: 60,
} as const;

function ScheduleForm({
  shared,
  saved,
  done,
}: {
  shared: Shared;
  saved?: Automation;
  done: (id: string) => void;
}) {
  const initial = saved?.configuration;
  const [title, setTitle] = useState(initial?.title || "");
  const [input, setInput] = useState(initial?.input || "");
  const [consent, setConsent] = useState(initial?.allow_remote_model || false);
  const [kind, setKind] = useState<"agent" | "workflow">(
    initial?.target.kind || "agent",
  );
  const [target, setTarget] = useState<AutomationTarget | null>(
    initial?.target || null,
  );
  const [after, setAfter] = useState("");
  const [schedule, setSchedule] = useState(
    initial?.schedule || {
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      kind: "daily" as const,
      start_at: new Date().toISOString(),
      interval_minutes: 60,
      local_time: "09:00",
      weekdays: [0, 1, 2, 3, 4],
    },
  );
  const [limits, setLimits] = useState<AutomationInput["policy"]>(
    initial?.policy || { ...policy },
  );
  const [preview, setPreview] = useState<{ utc: string; local: string }[]>([]);
  const action = useAction(shared);
  const targets = useRead<
    Page<{
      label: string;
      target: AutomationTarget | null;
      available: boolean;
      reason: string | null;
    }>
  >(
    shared,
    "automation-targets",
    `/automation-targets?kind=${kind}&after=${encodeURIComponent(after)}`,
  );
  if (targets.error)
    return (
      <ReadError error={targets.error} retry={() => void targets.refetch()} />
    );
  const updateSchedule = (value: Partial<typeof schedule>) => {
    setSchedule({ ...schedule, ...value });
    setPreview([]);
  };
  return (
    <Panel
      title={
        saved
          ? "Edit definisi · approval akan diperiksa kembali"
          : "Buat jadwal Core"
      }
    >
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!target || !consent) return;
          try {
            const result = await action.action(
              `/automations${saved ? `/${saved.id}` : ""}`,
              {
                title,
                input,
                target,
                allow_remote_model: consent,
                schedule,
                policy: limits,
                expected_revision: saved?.revision ?? null,
              },
            );
            done(String(result.id));
          } catch {
            /* Typed transport error remains visible. */
          }
        }}
      >
        <label>
          Nama jadwal
          <input
            value={title}
            required
            maxLength={160}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <div className="intelligence-columns">
          <label>
            Jenis target
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as "agent" | "workflow");
                setTarget(null);
                setAfter("");
              }}
            >
              <option value="agent">Agent assignment</option>
              <option value="workflow">Workflow version</option>
            </select>
          </label>
          <label>
            Target terverifikasi
            <select
              value={target ? `${target.id}:${target.version_id}` : ""}
              required
              onChange={(e) =>
                setTarget(
                  targets.data?.items.find(
                    (item) =>
                      item.target &&
                      `${item.target.id}:${item.target.version_id}` ===
                        e.target.value,
                  )?.target || null,
                )
              }
            >
              <option value="">Pilih target yang dipin</option>
              {initial &&
                !targets.data?.items.some(
                  (item) =>
                    item.target?.id === initial.target.id &&
                    item.target?.version_id === initial.target.version_id,
                ) && (
                  <option
                    value={`${initial.target.id}:${initial.target.version_id}`}
                  >
                    Target tersimpan · {initial.target.version_id}
                  </option>
                )}
              {targets.data?.items.map((item, index) => (
                <option
                  key={item.target?.id || index}
                  disabled={!item.available}
                  value={
                    item.target
                      ? `${item.target.id}:${item.target.version_id}`
                      : `unavailable-${index}`
                  }
                >
                  {item.label}
                  {item.reason ? ` · ${item.reason}` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        {targets.isPending && <Busy label="Memverifikasi target proyek…" />}
        <Pager after={after} next={targets.data?.next} set={setAfter} />
        {targets.data?.items.length === 0 && (
          <Notice>
            Belum ada target terverifikasi. Publish dan assign agent melalui
            Factory, atau freeze workflow terlebih dahulu.
          </Notice>
        )}
        {target && (
          <p className="mono intelligence-wrap">
            Versi {target.version_id} · hash {target.payload_hash} · activation{" "}
            {target.activation_id || "graph pins"}
          </p>
        )}
        <label>
          Input pekerjaan
          <textarea
            value={input}
            required
            maxLength={8000}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <div className="intelligence-columns">
          <label>
            Timezone IANA
            <input
              value={schedule.timezone}
              required
              onChange={(e) => updateSchedule({ timezone: e.target.value })}
            />
          </label>
          <label>
            Recurrence
            <select
              value={schedule.kind}
              onChange={(e) =>
                updateSchedule({ kind: e.target.value as typeof schedule.kind })
              }
            >
              <option value="interval">Interval UTC</option>
              <option value="daily">Harian · waktu lokal</option>
              <option value="weekly">Mingguan · waktu lokal</option>
            </select>
          </label>
        </div>
        <label>
          Mulai dari · timestamp dengan offset
          <input
            value={schedule.start_at}
            required
            onChange={(e) => updateSchedule({ start_at: e.target.value })}
          />
        </label>
        {schedule.kind === "interval" ? (
          <label>
            Interval menit
            <input
              type="number"
              min={1}
              max={10080}
              value={schedule.interval_minutes}
              onChange={(e) =>
                updateSchedule({ interval_minutes: Number(e.target.value) })
              }
            />
          </label>
        ) : (
          <label>
            Jam lokal
            <input
              type="time"
              required
              value={schedule.local_time}
              onChange={(e) => updateSchedule({ local_time: e.target.value })}
            />
          </label>
        )}
        {schedule.kind === "weekly" && (
          <fieldset>
            <legend>Hari lokal</legend>
            {[
              "Senin",
              "Selasa",
              "Rabu",
              "Kamis",
              "Jumat",
              "Sabtu",
              "Minggu",
            ].map((day, index) => (
              <label className="intelligence-check" key={day}>
                <input
                  type="checkbox"
                  checked={schedule.weekdays.includes(index)}
                  onChange={(e) =>
                    updateSchedule({
                      weekdays: e.target.checked
                        ? [...schedule.weekdays, index].sort()
                        : schedule.weekdays.filter((value) => value !== index),
                    })
                  }
                />
                {day}
              </label>
            ))}
          </fieldset>
        )}
        <div className="intelligence-columns">
          <label>
            Saat overlap
            <select
              value={limits.overlap}
              onChange={(e) =>
                setLimits({
                  ...limits,
                  overlap: e.target.value as "skip" | "queue",
                })
              }
            >
              <option value="skip">Lewati occurrence baru</option>
              <option value="queue">Antre hingga hasil diketahui</option>
            </select>
          </label>
          <label>
            Occurrence terlewat
            <select
              value={limits.missed}
              onChange={(e) =>
                setLimits({
                  ...limits,
                  missed: e.target.value as "skip" | "catch_up",
                })
              }
            >
              <option value="skip">Lewati</option>
              <option value="catch_up">Catch-up terbaru terbatas</option>
            </select>
          </label>
        </div>
        <div className="intelligence-columns">
          {(
            [
              ["catch_up_limit", "Maksimum catch-up", 1, 3],
              ["max_runs_per_day", "Maksimum occurrence per hari UTC", 1, 100],
              ["max_tokens_per_task", "Batas token per task Core", 128, 32768],
              ["max_attempts", "Maksimum readiness attempts", 1, 3],
              ["backoff_seconds", "Backoff awal · detik", 60, 3600],
            ] as const
          ).map(([field, label, min, max]) => (
            <label key={field}>
              {label}
              <input
                type="number"
                min={min}
                max={max}
                required
                value={limits[field]}
                onChange={(e) =>
                  setLimits({ ...limits, [field]: Number(e.target.value) })
                }
              />
            </label>
          ))}
        </div>
        <Notice>
          DST gap dilewati; fold pertama dijalankan sekali. Retry hanya sebelum
          admission Core. Unknown runtime tidak di-retry. Batas token adalah
          admission dan pemeriksaan usage Core, tanpa jaminan hard cap provider.
        </Notice>
        <label className="intelligence-check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          Izinkan eksekusi model target sesuai jadwal dan budget yang direview.
          Model/provider aktual tetap diperiksa Core.
        </label>
        {action.error && <Notice tone="error">{action.error.message}</Notice>}
        <div className="intelligence-actions">
          <Button
            type="button"
            variant="secondary"
            disabled={action.isPending}
            onClick={async () => {
              try {
                const result = await action.action("/automation-preview", {
                  schedule,
                });
                setPreview(result.instants as { utc: string; local: string }[]);
              } catch {
                /* visible error */
              }
            }}
          >
            Preview jadwal server
          </Button>
          <Button disabled={action.isPending || !target || !consent}>
            Simpan jadwal paused
          </Button>
        </div>
        {preview.length > 0 && (
          <ol aria-label="Preview occurrence">
            {preview.map((value) => (
              <li key={value.utc}>
                {value.local} · UTC {value.utc}
              </li>
            ))}
          </ol>
        )}
      </form>
    </Panel>
  );
}

function AutomationDetail({ shared, id }: { shared: Shared; id: string }) {
  const query = useRead<Automation>(shared, "automation", `/automations/${id}`);
  const [occAfter, setOccAfter] = useState("");
  const [eventAfter, setEventAfter] = useState("");
  const occurrences = useRead<Page<Occurrence>>(
    shared,
    "automation-occurrences",
    `/automations/${id}/occurrences?after=${encodeURIComponent(occAfter)}`,
    !!query.data && !query.error,
  );
  const events = useRead<Page<AutomationEvent>>(
    shared,
    "automation-events",
    `/automations/${id}/events?after=${encodeURIComponent(eventAfter)}`,
    !!query.data && !query.error,
  );
  const action = useAction(shared);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [manualKey, setManualKey] = useState<string>(() => crypto.randomUUID());
  const navigate = useNavigate();
  useEffect(() => {
    setConfirmed(false);
  }, [query.data?.payload_hash, !!query.error]);
  const error = query.error || occurrences.error || events.error;
  if (error)
    return (
      <ReadError
        error={error}
        retry={() => {
          void query.refetch();
          void occurrences.refetch();
          void events.refetch();
        }}
      />
    );
  if (!query.data || occurrences.isPending || events.isPending) return <Busy />;
  const saved = query.data,
    canManage =
      shared.data.permissions["version:approve"] &&
      saved.owner_actor_id === shared.workspace.user.id;
  const act = async (suffix: string, body: unknown) => {
    try {
      await action.action(`/automations/${id}${suffix}`, body);
    } catch {
      /* visible transport error */
    }
  };
  return (
    <div className="intelligence-workspace">
      <PageHeading
        title={saved.title}
        description="Definisi tersimpan, keputusan scheduling dan run linkage dari Core."
      >
        <Link to="/automations">Semua jadwal</Link>
        <Button
          variant="secondary"
          onClick={() => {
            void query.refetch();
            void occurrences.refetch();
            void events.refetch();
          }}
        >
          Periksa kembali
        </Button>
      </PageHeading>
      <Panel title="Authority & schedule">
        <Status value={saved.status} />
        <dl className="definition-grid">
          <dt>Owner</dt>
          <dd>{saved.owner_actor_id}</dd>
          <dt>Timezone</dt>
          <dd>{saved.configuration.schedule.timezone}</dd>
          <dt>Next occurrence UTC</dt>
          <dd>{saved.next_run_at}</dd>
          <dt>Last occurrence</dt>
          <dd>{saved.last_occurrence_id || "Belum ada"}</dd>
          <dt>Revision</dt>
          <dd>{saved.revision}</dd>
          <dt>Exact configuration hash</dt>
          <dd className="mono" data-testid="automation-hash">
            {saved.payload_hash}
          </dd>
          <dt>Core approval</dt>
          <dd>
            {saved.approval_verified
              ? "Terverifikasi untuk owner dan payload ini"
              : "Belum ada approval yang berlaku"}
          </dd>
          <dt>Target pin</dt>
          <dd>
            <Link
              to={
                saved.configuration.target.kind === "agent"
                  ? `/runs/new?penugasan=${saved.configuration.target.id}`
                  : `/workflows/${saved.configuration.target.id}`
              }
            >
              {saved.configuration.target.version_id}
            </Link>
          </dd>
          <dt>Last scheduler tick</dt>
          <dd>
            {saved.scheduler?.last_tick_at
              ? date(saved.scheduler.last_tick_at)
              : "Belum diamati"}
          </dd>
        </dl>
        <Notice>
          {saved.scheduler?.local_device_off} Tidak ada jaminan 24/7 atau hosted
          SLA. Scheduler native Hermes tidak digunakan.
        </Notice>
        {saved.scheduler?.error_code && (
          <Notice tone="error">{saved.scheduler.error_code}</Notice>
        )}
        <ol aria-label="Jadwal efektif">
          {saved.preview?.map((value) => (
            <li key={value.utc}>
              {value.local} · UTC {value.utc}
            </li>
          ))}
        </ol>
      </Panel>
      {canManage && (
        <Panel title="Human approval & execution policy">
          <label>
            Alasan review jadwal
            <textarea
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label className="intelligence-check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Saya meninjau exact target/hash, input, timezone, overlap, budget
            dan batas retry.
          </label>
          <div className="intelligence-actions">
            <Button
              disabled={
                !confirmed || reason.trim().length < 5 || action.isPending
              }
              onClick={() =>
                void act("/approve", {
                  expected_revision: saved.revision,
                  payload_hash: saved.payload_hash,
                  reason,
                })
              }
            >
              Setujui exact jadwal
            </Button>
            <Button
              disabled={
                action.isPending ||
                (saved.status === "paused" && !saved.approval_verified)
              }
              onClick={() =>
                void act("/state", {
                  expected_revision: saved.revision,
                  enabled: saved.status !== "enabled",
                })
              }
            >
              {saved.status === "enabled" ? "Pause jadwal" : "Resume jadwal"}
            </Button>
            <Button
              variant="secondary"
              disabled={action.isPending}
              onClick={() => setEditing(!editing)}
            >
              {editing ? "Tutup editor" : "Edit jadwal"}
            </Button>
          </div>
          <label>
            Idempotency key override
            <input
              value={manualKey}
              maxLength={100}
              onChange={(e) => setManualKey(e.target.value)}
            />
          </label>
          <div className="intelligence-actions">
            <Button
              disabled={
                !confirmed ||
                saved.status !== "enabled" ||
                !saved.approval_verified ||
                action.isPending ||
                !manualKey
              }
              onClick={() =>
                void act("/run", {
                  expected_revision: saved.revision,
                  idempotency_key: manualKey,
                })
              }
            >
              Jalankan occurrence manual
            </Button>
            <Button
              variant="secondary"
              onClick={() => setManualKey(crypto.randomUUID())}
            >
              Intent manual baru
            </Button>
          </div>
          <p>
            Key yang sama membaca occurrence yang sama. Unknown harus
            direkonsiliasi; tidak ada blind retry.
          </p>
        </Panel>
      )}
      {action.error && <Notice tone="error">{action.error.message}</Notice>}
      <div role="status" aria-live="polite">
        {action.isPending
          ? "Core memvalidasi perubahan…"
          : action.isSuccess
            ? "Perubahan tercatat; data proyek diperbarui."
            : ""}
      </div>
      {editing && canManage && (
        <ScheduleForm
          key={`${saved.id}:${saved.revision}`}
          shared={shared}
          saved={saved}
          done={(next) => {
            setEditing(false);
            setConfirmed(false);
            navigate(`/automations/${next}`);
          }}
        />
      )}
      <Panel title="Occurrence history">
        {occurrences.data?.items.length ? (
          occurrences.data.items.map((item) => (
            <article className="evidence-card" key={item.id} id={item.id}>
              <h3 className="mono intelligence-wrap">{item.id}</h3>
              <Status value={item.status} />
              <p>
                {date(item.scheduled_at)} · {item.occurrence_key} · attempts{" "}
                {item.attempts}
              </p>
              {item.error_code && (
                <Notice
                  tone={item.status === "outcome_unknown" ? "warning" : "error"}
                >
                  {item.error_code}
                </Notice>
              )}
              {item.retry_at && (
                <p>Readiness backoff sampai {date(item.retry_at)}</p>
              )}
              {item.run_id && (
                <Link
                  to={
                    item.run_kind === "agent"
                      ? `/runs/${item.run_id}`
                      : `/workflows/${item.target_id}?run=${item.run_id}`
                  }
                >
                  Buka captured{" "}
                  {item.run_kind === "agent" ? "Core Run" : "WorkflowRun"}
                </Link>
              )}
              {canManage && item.status === "outcome_unknown" && (
                <Button
                  disabled={
                    !confirmed || reason.trim().length < 5 || action.isPending
                  }
                  onClick={() =>
                    void act(`/occurrences/${item.id}/reconcile`, {
                      reason,
                      acknowledge_no_retry: true,
                    })
                  }
                >
                  Akui unknown tanpa retry
                </Button>
              )}
            </article>
          ))
        ) : (
          <Empty
            title="Belum ada occurrence"
            description="History muncul setelah tick Core atau override manual yang terotorisasi."
          />
        )}
        <Pager
          after={occAfter}
          next={occurrences.data?.next}
          set={setOccAfter}
        />
      </Panel>
      <Panel title="Immutable scheduling timeline">
        <ol className="incident-timeline">
          {events.data?.items.map((item) => (
            <li key={item.id}>
              <strong>{item.event}</strong>
              <p>
                {date(item.created_at)} · {item.actor_id}
              </p>
              <pre className="intelligence-json">
                {JSON.stringify(item.details, null, 2)}
              </pre>
            </li>
          ))}
        </ol>
        <Pager
          after={eventAfter}
          next={events.data?.next}
          set={setEventAfter}
        />
      </Panel>
    </div>
  );
}

export function Automations({ shared }: { shared: Shared }) {
  const location = useLocation(),
    navigate = useNavigate();
  const id = routeIdentifier(location.pathname.split("/")[2]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [after, setAfter] = useState("");
  const query = useRead<
    Page<Automation> & {
      scheduler: import("../lib/automation-types").SchedulerStatus;
    }
  >(
    shared,
    "automations",
    `/automations?q=${encodeURIComponent(q)}&status=${status}&after=${encodeURIComponent(after)}`,
    !id,
  );
  if (id && id !== "new") return <AutomationDetail shared={shared} id={id} />;
  if (id === "new")
    return (
      <div className="intelligence-workspace">
        <PageHeading
          title="Automation baru"
          description="Simpan paused, review exact payload, lalu aktifkan melalui Core."
        >
          <Link to="/automations">Semua jadwal</Link>
        </PageHeading>
        {shared.data.permissions["version:approve"] ? (
          <ScheduleForm
            shared={shared}
            done={(next) => navigate(`/automations/${next}`)}
          />
        ) : (
          <Notice tone="error">
            Core memerlukan human organization admin untuk mengelola jadwal.
          </Notice>
        )}
      </div>
    );
  return (
    <div className="intelligence-workspace">
      <PageHeading
        title="Automations"
        description="Jadwal server Core dengan occurrence durable dan target yang dipin."
      >
        {shared.data.permissions["version:approve"] && (
          <Link className="button button-primary" to="/automations/new">
            Buat jadwal
          </Link>
        )}
      </PageHeading>
      {query.error ? (
        <ReadError error={query.error} retry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Busy />
      ) : (
        <Panel title="Jadwal proyek">
          <Notice>
            {query.data.scheduler.local_device_off} Authority: Core single
            owner. Tidak ada native cron atau jaminan 24/7.
          </Notice>
          <div className="intelligence-filters">
            <label>
              Cari jadwal
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setAfter("");
                }}
              />
            </label>
            <label>
              Status jadwal
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setAfter("");
                }}
              >
                <option value="">Semua</option>
                <option value="enabled">Enabled</option>
                <option value="paused">Paused</option>
              </select>
            </label>
          </div>
          {query.data.items.length ? (
            query.data.items.map((item) => (
              <article className="evidence-card" key={item.id}>
                <h3>
                  <Link to={`/automations/${item.id}`}>{item.title}</Link>
                </h3>
                <Status value={item.status} />
                <p>
                  {item.configuration.schedule.timezone} ·{" "}
                  {item.configuration.schedule.kind} · next UTC{" "}
                  {item.next_run_at}
                </p>
                <p>
                  Owner {item.owner_actor_id} · last{" "}
                  {item.last_occurrence_id || "belum ada"}
                </p>
              </article>
            ))
          ) : (
            <Empty
              title="Belum ada jadwal yang cocok"
              description="Jadwal hanya menggunakan target agent/workflow terverifikasi dari proyek aktif."
            />
          )}
          <Pager after={after} next={query.data.next} set={setAfter} />
        </Panel>
      )}
    </div>
  );
}

export function Capabilities({ shared }: { shared: Shared }) {
  const query = useRead<CapabilityRegistry>(
    shared,
    "capabilities",
    "/capabilities",
  );
  return (
    <div className="intelligence-workspace">
      <PageHeading
        title="Capabilities"
        description="Read model policy Core; registry ini tidak memberikan tool grants."
      >
        <Button variant="secondary" onClick={() => void query.refetch()}>
          Periksa kembali
        </Button>
      </PageHeading>
      {query.error ? (
        <ReadError error={query.error} retry={() => void query.refetch()} />
      ) : !query.data ? (
        <Busy />
      ) : (
        <>
          <Panel title="Mode, entitlement & batas biaya">
            <dl className="definition-grid">
              <dt>Mode efektif</dt>
              <dd>{query.data.mode}</dd>
              <dt>Entitlement</dt>
              <dd>
                {query.data.entitlement} · {query.data.entitlement_reason}
              </dd>
              <dt>Usage billing</dt>
              <dd>
                {query.data.billing_category} · BYOK/Local bukan Managed AI
              </dd>
              <dt>Provider hard cost cap</dt>
              <dd>Belum terverifikasi</dd>
              <dt>Policy diperiksa</dt>
              <dd>{date(query.data.checked_at)}</dd>
            </dl>
            <Notice>
              Installer Windows, Ollama, pembayaran/subscription dan hosted VPS
              adalah workstream terpisah. Tidak ada premium unlock atau OS
              sandbox yang diklaim.
            </Notice>
          </Panel>
          <Panel title="Effective capability registry">
            {query.data.capabilities.map((item) => (
              <article key={item.namespace} className="evidence-card">
                <h3 className="mono intelligence-wrap">{item.namespace}</h3>
                <p>
                  Adapter {item.adapter} · version {item.version} · {item.risk}{" "}
                  · {item.modes.join(" / ")}
                </p>
                <p>
                  {item.available ? "Adapter tersedia" : "Unavailable"} ·{" "}
                  {item.effective_permission
                    ? "Core permission diizinkan"
                    : "Core permission ditolak"}{" "}
                  · grants{" "}
                  {item.grants.length ? item.grants.join(", ") : "kosong"}
                </p>
                {item.disabled_reason && (
                  <Notice tone="warning">{item.disabled_reason}</Notice>
                )}
                <ul>
                  {item.requirements.map((value) => (
                    <li key={value}>{value}</li>
                  ))}
                </ul>
              </article>
            ))}
          </Panel>
        </>
      )}
    </div>
  );
}
