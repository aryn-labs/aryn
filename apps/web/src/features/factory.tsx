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
import type { Blueprint } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import {
  Busy,
  Empty,
  Notice,
  PageHeading,
  Status,
} from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, Lifecycle, AuditList } from "../components/workspace";
import { VersionForm } from "../components/version-form";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildFactoryNodesAndEdges } from "../components/canvas/canvas-builders";
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
        <div className="flex items-center gap-2">
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

      {selected && selected.status === "published" && selected.governance_valid && (
        <div className="published-callout flex items-center justify-between gap-3 p-3 mb-4 rounded border">
          <div>
            <strong>Versi dipublikasikan (immutable)</strong>
            <p className="text-sm subtle">
              Versi ini dipublikasikan dan tidak dapat diubah. Konfigurasi terkunci dan valid. Lanjutkan dengan menugaskan peran atau jalankan agent.
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
                const a = data.assignments.find((asg) => asg.version_id === selected.id);
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
            const a = data.assignments.find((asg) => asg.version_id === selected?.id);
            if (a) navigate(`/runs?penugasan=${a.id}`);
            else navigate("/runs");
          }}
          canBench={canBench}
          canApprove={canApprove}
          canPublish={canPublish}
        />
      </div>

      {/* Secondary Information Panels */}
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
            ) : data.assignments.filter((a) => a.version_id === selected.id).length ? (
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
              {pending && (
                <Busy label="Core sedang memproses aksi…" />
              )}
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
