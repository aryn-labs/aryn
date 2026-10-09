import { executionReady, gatewayStatus } from "../lib/studio-state";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Beaker,
  Bot,
  ChevronRight,
  Folder,
  GitBranch,
  Layers3,
  Plus,
  Search,
} from "lucide-react";
import type { Blueprint, Assignment, Version } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { Busy, Empty, Notice, PageHeading, Status } from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, Lifecycle, AuditList } from "../components/workspace";
import { VersionForm } from "../components/version-form";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildFactoryNodesAndEdges } from "../components/canvas/canvas-builders";
import { ResourceBrowser } from "./resource-browser";
export function FactoryRegistry({
  workspace,
  project,
  openBlueprint,
  data,
}: Shared) {
  return (
    <>
      <PageHeading
        eyebrow="AGENT FACTORY"
        title="Agent Factory"
        description="Blueprint, versi immutable, dan evidence aktual dalam proyek aktif."
      >
        <Button
          onClick={openBlueprint}
          disabled={!data.permissions["blueprint:create"]}
        >
          Buat blueprint
        </Button>
      </PageHeading>
      <Panel title="Blueprint agent">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="blueprints"
          title="blueprint"
          link={(item) => `/factory/${item.id}`}
        />
      </Panel>
      <Panel title="Version Registry">
        <ResourceBrowser
          organization={workspace.organization.id}
          project={project}
          resource="versions"
          title="versi agent"
          statuses={[
            "draft",
            "approved",
            "published",
            "deprecated",
            "rejected",
          ]}
          link={(item) =>
            `/factory/${item.references.blueprint_id}/versions/${item.id}`
          }
          extra={(item) => <code>{String(item.references.payload_hash)}</code>}
        />
      </Panel>
    </>
  );
}
export function Factory({ data, openBlueprint }: Shared) {
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const list = data.blueprints.filter((b) =>
    `${b.name} ${b.slug} ${b.description}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow="DEFINISIKAN"
        title="Agent Factory"
        description="Blueprint yang jelas. Versi yang tetap. Agent yang dapat dipertanggungjawabkan."
      >
        <Button
          onClick={openBlueprint}
          disabled={!data.permissions["run:create"]}
        >
          <Plus size={16} />
          Buat blueprint
        </Button>
      </PageHeading>
      <div className="list-toolbar">
        <div className="search-field">
          <Search size={16} />
          <input
            aria-label="Cari blueprint"
            placeholder="Cari nama, slug, atau deskripsi…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span>{number(list.length)} blueprint</span>
      </div>
      <Panel
        title="Blueprint agent"
        subtitle="Setiap blueprint memiliki versi dan penugasan terpisah."
      >
        {list.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Versi terbaru</th>
                  <th>Status</th>
                  <th>Penugasan</th>
                  <th>Dibuat</th>
                  <th>
                    <span className="sr-only">Buka</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((bp) => {
                  const v = data.versions.find((v) => v.blueprint_id === bp.id);
                  return (
                    <tr key={bp.id}>
                      <td>
                        <Link className="table-agent" to={`/factory/${bp.id}`}>
                          <div className="agent-icon">
                            <Bot size={18} />
                          </div>
                          <div>
                            <strong>{bp.name}</strong>
                            <small>{bp.description || bp.slug}</small>
                          </div>
                        </Link>
                      </td>
                      <td className="mono">
                        {v ? `v${v.version_number}` : "—"}
                      </td>
                      <td>
                        {v ? (
                          <Status value={v.status} />
                        ) : (
                          <span className="subtle">Belum dikonfigurasi</span>
                        )}
                      </td>
                      <td>
                        {
                          data.assignments.filter(
                            (a) => a.blueprint_id === bp.id,
                          ).length
                        }
                      </td>
                      <td className="subtle">{date(bp.created_at)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Buka ${bp.name}`}
                          onClick={() => navigate(`/factory/${bp.id}`)}
                        >
                          <ChevronRight size={16} />
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
            title={
              search
                ? "Tidak ada blueprint yang cocok"
                : "Belum ada blueprint agent"
            }
            description={
              search
                ? "Coba kata pencarian lain atau hapus pencarian."
                : "Mulai dengan tujuan agent. Anda akan mengatur model dan instruksi pada versi pertamanya."
            }
            action={search ? "Hapus pencarian" : "Buat blueprint"}
            onAction={() => (search ? setSearch("") : openBlueprint())}
          />
        )}
      </Panel>
      <div className="page-footnote">
        <Layers3 size={15} />
        Blueprint, versi, dan penugasan dikelola sebagai sumber daya yang
        berbeda.
      </div>
    </>
  );
}

export function AgentDetail({
  data,
  workspace,
  blueprint,
  project,
  pending,
  act,
  error,
  resetError,
}: Shared & { blueprint: Blueprint }) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const versions = data.versions.filter((v) => v.blueprint_id === blueprint.id);
  const selected =
    versions.find((v) => v.id === params.get("versi")) || versions[0];
  const [dialog, setDialog] = useState("");
  const openDialog = (name: string) => {
    resetError();
    setDialog(name);
  };
  const [role, setRole] = useState("Peneliti produk");
  const [comments, setComments] = useState("");
  const evaluation =
    selected && data.evaluations.find((e) => e.version_id === selected.id);
  const assignment =
    selected && data.assignments.find((a) => a.version_id === selected.id);
  const passed = !!selected?.bench_eligible;
  const modelAvailability =
    workspace.models.find((m) => m.model_id === selected?.model)
      ?.availability || "unknown";
  const modelReady = modelAvailability === "available";
  const stage = !selected
    ? 1
    : assignment
      ? 6
      : selected.status === "published"
        ? 5
        : selected.status === "approved"
          ? 4
          : passed
            ? 3
            : 2;
  const { nodes: factoryNodes, edges: factoryEdges } = useMemo(() => {
    return buildFactoryNodesAndEdges(blueprint, selected, workspace, project);
  }, [blueprint, selected, workspace, project]);
  const canBench =
    !pending &&
    executionReady(workspace) &&
    modelReady &&
    selected?.integrity_valid &&
    ["draft", "rejected"].includes(selected.status) &&
    data.permissions["run:create"];
  const canApprove =
    !pending &&
    selected?.status === "draft" &&
    passed &&
    selected.integrity_valid &&
    data.permissions["version:approve"];
  const canPublish =
    !pending &&
    selected?.status === "approved" &&
    selected.governance_valid &&
    passed &&
    data.permissions["version:publish"];
  const saveVersion = async (body: unknown) => {
    const v = await act(
      `/blueprints/${blueprint.id}/versions`,
      body,
      "Versi baru tersimpan di database.",
    );
    setDialog("");
    setParams({ versi: String(v.id) });
  };
  const runAction = async (kind: string) => {
    if (!selected) return;
    try {
      await act(
        `/versions/${selected.id}/${kind}`,
        kind === "approve"
          ? { comments, payload_hash: selected.payload_hash }
          : {},
        kind === "approve"
          ? "Persetujuan Core tercatat."
          : "Versi berhasil dipublikasikan.",
      );
      setDialog("");
    } catch {
      /* error is shown above page */
    }
  };
  return (
    <>
      <Link to="/factory" className="back-link">
        <ArrowLeft size={14} />
        Semua blueprint
      </Link>
      <PageHeading
        eyebrow="BLUEPRINT AGENT"
        title={blueprint.name}
        description={
          blueprint.description ||
          "Agent riset teks dengan evaluasi keselamatan dan tata kelola Core."
        }
      >
        <div className="agent-actions">
          <Button
            onClick={() =>
              navigate(
                `/factory/${blueprint.id}/builder${selected ? `?source=${selected.id}` : ""}`,
              )
            }
            disabled={pending || !data.permissions["version:create"]}
          >
            Buka AgentBuilder
          </Button>
          {selected && (
            <Link to={`/factory/${blueprint.id}/versions/${selected.id}`}>
              Version Detail
            </Link>
          )}
          {selected && ["draft", "rejected"].includes(selected.status) && (
            <Button
              variant="secondary"
              disabled={!canBench}
              onClick={() => navigate(`/bench?versi=${selected.id}`)}
            >
              <Beaker size={15} />
              Jalankan Bench
            </Button>
          )}
          <Button
            variant="secondary"
            disabled={pending || !data.permissions["run:create"]}
            onClick={() => openDialog("version")}
          >
            <Plus size={15} />
            Versi baru
          </Button>
        </div>
      </PageHeading>
      <div className="detail-toolbar">
        <div className="version-picker">
          <GitBranch size={16} />
          <select
            aria-label="Pilih versi agent"
            value={selected?.id || ""}
            onChange={(e) => {
              const p = new URLSearchParams(params);
              p.set("versi", e.target.value);
              setParams(p);
            }}
          >
            {versions.length ? (
              versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number}
                </option>
              ))
            ) : (
              <option value="">Belum ada versi</option>
            )}
          </select>
          {selected && <Status value={selected.status} />}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {!selected ? (
            <Button
              size="sm"
              onClick={() => openDialog("version")}
              disabled={pending || !data.permissions["run:create"]}
            >
              <Plus size={15} />
              Buat versi pertama
            </Button>
          ) : null}
          <span className="mono subtle">{blueprint.id}</span>
        </div>
      </div>
      {selected &&
        (!selected.integrity_valid ||
          (selected.status === "published" && !selected.governance_valid)) && (
          <Notice tone="error">
            Integritas atau bukti tata kelola versi tidak valid. Buat versi
            baru, jalankan Bench, dan setujui kembali.
          </Notice>
        )}
      <div className="lifecycle-panel">
        <Lifecycle current={stage} />
      </div>
      {selected && !modelReady && (
        <Notice tone="warning">
          {modelAvailability === "unavailable"
            ? "Model tidak tersedia melalui Model Gateway. Pilih model lain pada versi baru sebelum menjalankan Bench."
            : "Ketersediaan model belum dapat diverifikasi. Bench diblokir sampai runtime menyediakan bukti ketersediaan yang valid."}
        </Notice>
      )}
      {gatewayStatus(workspace).tone !== "success" && (
        <Notice tone={gatewayStatus(workspace).tone}>
          {gatewayStatus(workspace).label}
        </Notice>
      )}

      {selected &&
        selected.status === "published" &&
        selected.governance_valid && (
          <div className="published-callout flex items-center justify-between gap-3 p-3 mb-4 rounded border">
            <div>
              <strong>Versi dipublikasikan (immutable)</strong>
              <p className="text-sm subtle">
                Versi ini dipublikasikan dan tidak dapat diubah. Konfigurasi
                terkunci dan valid. Lanjutkan dengan menugaskan peran atau
                jalankan agent.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                size="sm"
                disabled={pending || !data.permissions["agent:assign"]}
                onClick={() => openDialog("assign")}
              >
                <Plus size={14} />
                Buat Penugasan
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  const a = data.assignments.find(
                    (asg) => asg.version_id === selected.id,
                  );
                  if (a) navigate(`/runs?penugasan=${a.id}`);
                  else navigate("/runs");
                }}
              >
                <ArrowRight size={14} />
                Buka Eksekusi
              </Button>
            </div>
          </div>
        )}

      {/* Primary Workspace: Laboratory Canvas */}
      <div className="factory-canvas-workspace mb-6">
        <ArynCanvas
          mode="factory"
          initialNodes={factoryNodes}
          initialEdges={factoryEdges}
          version={selected || null}
          workspace={workspace}
          showInspectorByDefault
          versions={versions}
          pending={pending}
          error={error}
          onCreateVersion={
            data.permissions["run:create"] ? saveVersion : undefined
          }
          onRunBench={() => {
            if (selected) {
              navigate(`/bench?versi=${selected.id}`);
            }
          }}
          onApproveVersion={() => {
            setComments("");
            openDialog("approve");
          }}
          onPublishVersion={() => {
            openDialog("publish");
          }}
          onCreateAssignment={() => {
            openDialog("assign");
          }}
          onOpenExecution={() => {
            const a = data.assignments.find(
              (asg) => asg.version_id === selected?.id,
            );
            if (a) navigate(`/runs?penugasan=${a.id}`);
            else navigate("/runs");
          }}
          canBench={canBench}
          canApprove={canApprove}
          canPublish={canPublish}
        />
      </div>

      {/* Secondary Information Panels */}
      <VersionRegistry
        data={data}
        blueprintId={blueprint.id}
        pending={pending}
        act={act}
        error={error}
        resetError={resetError}
      />
      {selected && (
        <div className="factory-secondary-panels grid grid-cols-1 gap-6">
          <Panel
            title="Penugasan operasional"
            subtitle={`Lingkup: ${workspace.projects.find((p) => p.id === project)?.name || "proyek ini"}`}
            action={
              <Button
                size="sm"
                disabled={
                  pending ||
                  selected.status !== "published" ||
                  !selected.governance_valid ||
                  !data.permissions["agent:assign"]
                }
                onClick={() => openDialog("assign")}
              >
                <Plus size={14} />
                Buat penugasan
              </Button>
            }
          >
            {selected.status !== "published" || !selected.governance_valid ? (
              <Empty
                title="Publikasikan versi terlebih dahulu"
                description="Core menolak penugasan versi yang belum dipublikasikan. Selesaikan Bench, persetujuan, dan publikasi pada Inspector canvas."
              />
            ) : data.assignments.filter((a) => a.version_id === selected.id)
                .length ? (
              <div className="assignment-list">
                {data.assignments
                  .filter((a) => a.version_id === selected.id)
                  .map((a) => (
                    <div key={a.id}>
                      <div className="agent-icon">
                        <Folder size={18} />
                      </div>
                      <div>
                        <strong>{a.role_name}</strong>
                        <small className="mono">{a.id}</small>
                      </div>
                      <Status value={a.status} />
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => navigate(`/runs?penugasan=${a.id}`)}
                      >
                        Buka Eksekusi
                        <ArrowRight size={14} />
                      </Button>
                    </div>
                  ))}
              </div>
            ) : (
              <Empty
                title="Siap ditugaskan ke proyek"
                description="Berikan peran operasional pada versi yang dipublikasikan. Penugasan hanya berlaku dalam proyek yang diizinkan."
                action="Buat penugasan"
                onAction={() => openDialog("assign")}
              />
            )}
          </Panel>

          <Panel
            title="Jejak audit agent"
            subtitle="Peristiwa aktual dari Core dan Factory."
          >
            <AuditList
              events={data.audit.filter((e) =>
                [
                  blueprint.id,
                  selected.id,
                  ...data.assignments
                    .filter((a) => a.blueprint_id === blueprint.id)
                    .map((a) => a.id),
                ].includes(e.resource_id),
              )}
            />
          </Panel>
        </div>
      )}

      <Modal
        open={!!dialog}
        busy={pending}
        onOpenChange={(v) => {
          if (!pending && !v) setDialog("");
        }}
        title={
          dialog === "version"
            ? "Simpan versi baru"
            : dialog === "approve"
              ? "Tinjau persetujuan versi"
              : dialog === "publish"
                ? "Publikasikan versi agent"
                : "Buat penugasan agent"
        }
        description={
          dialog === "version"
            ? "Versi baru memiliki hash konfigurasi sendiri dan harus dievaluasi kembali."
            : dialog === "approve"
              ? "Anda bertindak sebagai admin development lokal."
              : dialog === "publish"
                ? "Publikasi membuat versi tetap dan tersedia untuk penugasan."
                : "Penugasan dibuat pada proyek aktif dengan otorisasi Core."
        }
      >
        {error && (
          <div className="modal-error">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        {dialog === "version" ? (
          <VersionForm
            versions={versions}
            models={workspace.models}
            previous={selected}
            pending={pending}
            onSubmit={async (body) => {
              try {
                await saveVersion(body);
              } catch {
                /* visible error */
              }
            }}
          />
        ) : dialog === "assign" ? (
          <form
            noValidate
            onSubmit={async (e) => {
              e.preventDefault();
              if (!selected || role.trim().length < 2) return;
              try {
                await act(
                  "/assignments",
                  {
                    blueprint_id: blueprint.id,
                    version_id: selected.id,
                    role_name: role,
                  },
                  "Penugasan berhasil dibuat.",
                );
                setDialog("");
              } catch {
                /* visible error */
              }
            }}
          >
            <div className="form-fields">
              <label>
                Proyek
                <input
                  disabled
                  value={
                    workspace.projects.find((p) => p.id === project)?.name ||
                    "Laboratorium Riset"
                  }
                />
              </label>
              <label>
                Versi
                <input disabled value={`v${selected?.version_number}`} />
              </label>
              <label>
                Peran operasional
                <input
                  required
                  minLength={2}
                  maxLength={64}
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                />
              </label>
              <Notice>
                Penugasan berlaku pada proyek saat ini. Blueprint tidak
                dipindahkan antarproyek.
              </Notice>
            </div>
            <div className="dialog-footer">
              <span>Otorisasi diperiksa Core</span>
              <Button disabled={pending || role.trim().length < 2}>
                {pending ? "Menugaskan…" : "Buat penugasan"}
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <div className="form-fields">
              <div className="review-version">
                <Bot size={19} />
                <strong>{blueprint.name}</strong>
                <span className="mono">v{selected?.version_number}</span>
              </div>
              {dialog === "approve" ? (
                <>
                  <Notice tone="success">
                    Bench terakhir lulus {evaluation?.passed_scenarios}/
                    {evaluation?.total_scenarios} skenario.
                  </Notice>
                  <label>
                    Hash konfigurasi yang disetujui
                    <code className="hash-review wrap">
                      {selected?.payload_hash}
                    </code>
                  </label>
                  <label>
                    Catatan persetujuan
                    <textarea
                      autoFocus
                      required
                      minLength={5}
                      maxLength={2000}
                      rows={3}
                      placeholder="Alasan versi ini layak dipublikasikan…"
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                    />
                  </label>
                </>
              ) : (
                <Notice>
                  Core memverifikasi evaluasi terakhir dan persetujuan untuk
                  hash yang tepat. Versi yang dipublikasikan tidak dapat diedit.
                </Notice>
              )}
              {pending && <Busy label="Core sedang memproses aksi…" />}
            </div>
            <div className="dialog-footer">
              <Button
                variant="ghost"
                disabled={pending}
                onClick={() => setDialog("")}
              >
                Batal
              </Button>
              <Button
                disabled={
                  pending ||
                  (dialog === "approve" && comments.trim().length < 5)
                }
                onClick={() => void runAction(dialog)}
              >
                {pending
                  ? "Memproses…"
                  : dialog === "approve"
                    ? "Setujui versi"
                    : "Publikasikan"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

export function VersionRegistry({
  data,
  blueprintId,
  pending,
  act,
  error,
  resetError,
}: Pick<Shared, "data" | "pending" | "act" | "error" | "resetError"> & {
  blueprintId: string;
}) {
  const versions = data.versions.filter((v) => v.blueprint_id === blueprintId);
  const assignments = data.assignments.filter(
    (a) => a.blueprint_id === blueprintId,
  );
  const [review, setReview] = useState<{
    assignment: Assignment;
    target: Version;
    key: string;
  } | null>(null);
  const [reason, setReason] = useState("");
  const targets = (assignment: Assignment) => {
    const current = versions.find((v) => v.id === assignment.version_id);
    return versions.filter(
      (v) =>
        v.id !== current?.id &&
        v.registry?.rollback_eligible &&
        v.registry.published_at &&
        current?.registry?.published_at &&
        new Date(v.registry.published_at) <
          new Date(current.registry.published_at),
    );
  };
  return (
    <>
      <Panel
        title="Version Registry"
        subtitle="Artefak versi immutable; kelayakan known-good diverifikasi server dari publication, Bench, dan Core approval."
      >
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Version Registry"
        >
          <table>
            <thead>
              <tr>
                <th>Versi / lifecycle</th>
                <th>Checksum</th>
                <th>Publication / governance</th>
                <th>Aktif</th>
                <th>Known-good</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id}>
                  <td>
                    <strong>v{v.version_number}</strong>
                    <Status value={v.status} />
                    <small>{date(v.created_at)}</small>
                  </td>
                  <td>
                    <code title={v.payload_hash}>
                      {v.payload_hash.slice(0, 12)}
                    </code>
                  </td>
                  <td>
                    {v.registry?.published_at ? (
                      <>
                        <span>
                          {date(v.registry.published_at)} ·{" "}
                          {v.registry.published_by}
                        </span>
                        <small>Bench {v.registry.evaluation_id}</small>
                        <small>
                          Approval{" "}
                          {v.registry.approval_id || "Belum terverifikasi"}
                        </small>
                        <small>
                          Publication{" "}
                          {v.registry.publication_id || "Belum terverifikasi"}
                        </small>
                        <small>
                          Comparison{" "}
                          {v.registry.regression_comparison_id ||
                            "Tidak tersedia"}
                        </small>
                      </>
                    ) : (
                      "Belum dipublikasikan"
                    )}
                    <small>
                      Bench:{" "}
                      {v.registry?.bench_verified
                        ? v.registry.bench_passed
                          ? "Terverifikasi / lulus"
                          : "Terverifikasi / gagal"
                        : "Belum terverifikasi"}
                    </small>
                    {v.registry?.approval_id && (
                      <small>
                        Core approval: {v.registry.approval_status} ·{" "}
                        {v.registry.approval_id}
                      </small>
                    )}
                    {v.registry?.current_baseline && (
                      <strong>Current Bench baseline</strong>
                    )}
                  </td>
                  <td>
                    {v.registry?.active_assignment_count ??
                      assignments.filter((a) => a.version_id === v.id).length}
                  </td>
                  <td>
                    {v.registry?.rollback_eligible
                      ? "Known-good terverifikasi"
                      : "Tidak eligible"}
                    <small>
                      {v.registry?.reason || "Evidence belum terverifikasi"}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel
        title="Aktivasi assignment"
        subtitle="Rollback hanya memindahkan versi aktif satu assignment. Current Bench baseline dan histori versi tetap."
      >
        {assignments.length ? (
          assignments.map((a) => {
            const current = versions.find((v) => v.id === a.version_id);
            const eligible = targets(a);
            return (
              <div key={a.id} className="form-fields">
                <strong>
                  {a.role_name} · aktif v
                  {current?.version_number || a.version_id}
                </strong>
                <small className="mono">{a.id}</small>
                {(a.activation_history || []).map((t) => (
                  <div key={t.transition_id}>
                    <span>
                      {t.transition_type}:{" "}
                      {t.from_version_id
                        ? `v${versions.find((v) => v.id === t.from_version_id)?.version_number || t.from_version_id} → `
                        : ""}
                      v
                      {versions.find((v) => v.id === t.to_version_id)
                        ?.version_number || t.to_version_id}
                    </span>
                    <small>
                      {date(t.committed_at)} · {t.actor_id} · {t.reason}
                    </small>
                  </div>
                ))}
                {!a.activation_verified && (
                  <Notice>
                    {a.activation_reason === "activation_integrity_invalid"
                      ? "Integritas histori aktivasi tidak valid."
                      : "Assignment historis: origin aktivasi sebelumnya tidak tersedia. Server mencatat adoption saat rollback."}
                  </Notice>
                )}
                <Button
                  variant="secondary"
                  disabled={
                    pending ||
                    a.status !== "active" ||
                    !eligible.length ||
                    !data.permissions["agent:rollback"] ||
                    a.activation_reason === "activation_integrity_invalid"
                  }
                  onClick={() => {
                    resetError();
                    setReason("");
                    setReview({
                      assignment: { ...a },
                      target: eligible[0],
                      key: crypto.randomUUID(),
                    });
                  }}
                >
                  Tinjau rollback {a.role_name}
                </Button>
                {!eligible.length && (
                  <small>
                    Tidak ada publication sebelumnya yang eligible sebagai
                    target.
                  </small>
                )}
              </div>
            );
          })
        ) : (
          <Empty
            title="Belum ada aktivasi"
            description="Buat assignment dari versi published yang terverifikasi."
          />
        )}
      </Panel>
      <Modal
        open={!!review}
        busy={pending}
        onOpenChange={(v) => {
          if (!pending && !v) setReview(null);
        }}
        title="Rollback assignment"
        description="Tinjau versi aktif dan previous known-good publication sebelum mengubah assignment."
      >
        {review && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await act(
                  `/assignments/${review.assignment.id}/rollback`,
                  {
                    target_version_id: review.target.id,
                    expected_current_version_id: review.assignment.version_id,
                    expected_transition_id:
                      review.assignment.current_transition_id || null,
                    reason,
                    idempotency_key: review.key,
                  },
                  "Rollback assignment tercatat. Eksekusi berikutnya memakai versi target.",
                );
                setReview(null);
              } catch {
                /* server error remains visible; retry preserves intent/key */
              }
            }}
          >
            <div className="form-fields">
              {error && <Notice tone="error">{error}</Notice>}
              <strong>
                Current: v
                {
                  versions.find((v) => v.id === review.assignment.version_id)
                    ?.version_number
                }
              </strong>
              <label>
                Target known-good
                <select
                  value={review.target.id}
                  disabled={pending}
                  onChange={(e) =>
                    setReview({
                      ...review,
                      target: versions.find((v) => v.id === e.target.value)!,
                      key: crypto.randomUUID(),
                    })
                  }
                >
                  {targets(review.assignment).map((v) => (
                    <option key={v.id} value={v.id}>
                      v{v.version_number}
                    </option>
                  ))}
                </select>
              </label>
              <strong>Target: v{review.target.version_number}</strong>
              <code className="hash-review wrap">
                {review.target.payload_hash}
              </code>
              <small>Evaluation: {review.target.registry?.evaluation_id}</small>
              <small>
                Publication: {review.target.registry?.publication_id}
              </small>
              <small>Approval: {review.target.registry?.approval_id}</small>
              <label>
                Alasan rollback
                <textarea
                  required
                  minLength={5}
                  maxLength={2000}
                  value={reason}
                  onChange={(e) => {
                    setReason(e.target.value);
                    setReview({ ...review, key: crypto.randomUUID() });
                  }}
                />
              </label>
              <Notice>
                Operasi mengubah versi aktif assignment, tanpa mengedit
                konfigurasi versi. Run yang sudah dimulai memakai versi semula;
                Bench baseline tetap.
              </Notice>
            </div>
            <div className="dialog-footer">
              <Button
                variant="ghost"
                disabled={pending}
                onClick={() => setReview(null)}
              >
                Batal
              </Button>
              <Button disabled={pending || reason.trim().length < 5}>
                Konfirmasi rollback assignment
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
