import { executionReady } from "../lib/studio-state";
import { useMemo, useState, type ReactNode } from "react";
import {
  Link,
  useSearchParams,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { Shared } from "../lib/types";
import { routeIdentifier } from "../lib/workspace-types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Busy, Empty, Notice, PageHeading, Status } from "../components/shared";
import { Panel } from "../components/workspace";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildExecutionNodesAndEdges } from "../components/canvas/canvas-builders";
import { historicalRunContext } from "../lib/studio-state";
import { useReducedMotion } from "../lib/motion";
import type { PublishedAgentItem } from "../components/canvas/canvas-inspector";

export function Runs({
  data,
  workspace,
  pending,
  act,
  actStream,
  history,
}: Shared & { history?: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const routeRun = useLocation().pathname.split("/")[2];
  const navigate = useNavigate();
  const reducedMotion = useReducedMotion();

  // Published agents available for execution (assigned or unassigned)
  const publishedAgents = useMemo<PublishedAgentItem[]>(() => {
    const list: PublishedAgentItem[] = [];
    const publishedVersions = data.versions.filter(
      (v) =>
        v.status === "published" && v.integrity_valid && v.governance_valid,
    );

    for (const v of publishedVersions) {
      const bp = data.blueprints.find((b) => b.id === v.blueprint_id);
      const activeAssignment = data.assignments.find(
        (a) =>
          a.status === "active" &&
          a.version_id === v.id &&
          a.blueprint_id === v.blueprint_id,
      );

      list.push({
        versionId: v.id,
        blueprintId: v.blueprint_id,
        blueprintName: bp?.name || v.blueprint_id,
        versionNumber: v.version_number,
        model: v.model,
        assignmentId: activeAssignment?.id,
        roleName: activeAssignment?.role_name,
        isAssigned: Boolean(activeAssignment),
        integrityValid: v.integrity_valid,
        governanceValid: v.governance_valid,
      });
    }

    return list;
  }, [data.versions, data.blueprints, data.assignments]);

  // Selected agent version
  const [selectedVersionId, setSelectedVersionId] = useState<string>(() => {
    const paramPenugasan = params.get("penugasan");
    if (paramPenugasan) {
      const match = data.assignments.find((a) => a.id === paramPenugasan);
      if (match) return match.version_id;
    }
    const firstValidAssigned = publishedAgents.find(
      (a) =>
        a.isAssigned &&
        a.integrityValid !== false &&
        a.governanceValid !== false,
    );
    if (firstValidAssigned) return firstValidAssigned.versionId;
    const firstAssigned = publishedAgents.find((a) => a.isAssigned);
    if (firstAssigned) return firstAssigned.versionId;
    return publishedAgents[0]?.versionId || "";
  });

  const activeVersionId = publishedAgents.some(
    (a) => a.versionId === selectedVersionId,
  )
    ? selectedVersionId
    : publishedAgents.find(
        (a) =>
          a.isAssigned &&
          a.integrityValid !== false &&
          a.governanceValid !== false,
      )?.versionId ||
      publishedAgents.find((a) => a.isAssigned)?.versionId ||
      publishedAgents[0]?.versionId ||
      "";

  const selectedAgent = publishedAgents.find(
    (a) => a.versionId === activeVersionId,
  );

  // Form states
  const [prompt, setPrompt] = useState("");
  const [consent, setConsent] = useState(false);
  const [runKey, setRunKey] = useState(() => crypto.randomUUID());
  const [validation, setValidation] = useState("");
  const [executing, setExecuting] = useState(false);
  const [stopMessage, setStopMessage] = useState("");
  const [liveEvent, setLiveEvent] = useState<{
    step: string;
    message?: string;
  } | null>(null);

  // Inline assignment creation states
  const [roleInput, setRoleInput] = useState("Peneliti riset");
  const [creatingAssignment, setCreatingAssignment] = useState(false);

  const runIdentifier =
    params.get("hasil") ||
    (routeRun && routeRun !== "new" ? routeIdentifier(routeRun) : null);
  const isHistorical = !!runIdentifier;
  const selectedRun = isHistorical
    ? data.runs.find((r) => r.id === runIdentifier)
    : undefined;
  const historical = historicalRunContext(data, selectedRun?.id);

  const assigned = selectedAgent?.assignmentId
    ? data.assignments.find((a) => a.id === selectedAgent.assignmentId)
    : undefined;
  const version = data.versions.find((v) => v.id === selectedAgent?.versionId);
  const modelAvailability =
    workspace.models.find((m) => m.model_id === version?.model)?.availability ||
    "unknown";

  const viewResult = (runId: string) => {
    if (history) navigate(`/runs/${runId}`);
    else setParams({ hasil: runId });
    const target = document.getElementById("canvas-inspector");
    if (target) {
      target.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    }
  };

  const createAssignment = async () => {
    if (!selectedAgent || roleInput.trim().length < 2 || !act) return;
    setCreatingAssignment(true);
    setValidation("");
    try {
      const res = await act(
        "/assignments",
        {
          blueprint_id: selectedAgent.blueprintId,
          version_id: selectedAgent.versionId,
          role_name: roleInput.trim(),
        },
        "Penugasan operasional berhasil dibuat. Agent siap dijalankan.",
      );
      if (res && typeof res.id === "string") {
        setParams({ penugasan: res.id });
      }
    } catch (err: unknown) {
      setValidation(
        (err instanceof Error ? err.message : "") || "Gagal membuat penugasan",
      );
    } finally {
      setCreatingAssignment(false);
    }
  };

  const submit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!assigned || prompt.trim().length < 5 || !consent) {
      setValidation(
        "Pilih agent dengan penugasan aktif, isi instruksi minimal lima karakter, dan konfirmasikan penggunaan model.",
      );
      return;
    }
    setValidation("");
    setExecuting(true);
    setLiveEvent(null);

    try {
      const runner = actStream || act;
      const r = await runner(
        "/runs",
        {
          assignment_id: assigned.id,
          prompt: prompt.trim(),
          idempotency_key: runKey,
          allow_remote_model: consent,
        },
        "Eksekusi selesai. Hasil dan audit tersimpan.",
        (evt: import("../lib/types").StreamEvent) => {
          if (!evt) return;
          setLiveEvent({ step: evt.type, message: evt.data?.message });
        },
      );
      // Fresh runs return run_id; idempotency replay returns the persisted row id.
      const newRunId = r?.run_id || r?.id;
      if (typeof newRunId !== "string" || !newRunId) {
        throw new Error("Respons eksekusi belum menyertakan ID run.");
      }
      setRunKey(crypto.randomUUID());
      viewResult(newRunId);
    } catch (err: unknown) {
      setValidation(
        (err instanceof Error ? err.message : "") ||
          "Eksekusi belum dapat diselesaikan.",
      );
      /* Retry preserves idempotency key; edits create a new key. */
    } finally {
      setExecuting(false);
      setLiveEvent(null);
    }
  };

  const canvasVersion = isHistorical ? historical.version : version;
  const canvasAgentName = isHistorical
    ? historical.blueprint?.name
    : selectedAgent?.blueprintName;
  const { nodes: execNodes, edges: execEdges } = useMemo(() => {
    return buildExecutionNodesAndEdges(
      selectedRun,
      canvasVersion,
      canvasAgentName,
      isHistorical ? null : liveEvent,
      isHistorical ? "historical" : "new",
    );
  }, [selectedRun, canvasVersion, canvasAgentName, isHistorical, liveEvent]);

  const executionFormConfig = useMemo(
    () => ({
      publishedAgents,
      selectedVersionId: activeVersionId,
      onSelectVersion: (id: string) => {
        setSelectedVersionId(id);
        if (history) setParams({ versi: id });
        setRunKey(crypto.randomUUID());
        setValidation("");
      },
      roleInput,
      onRoleInputChange: setRoleInput,
      onCreateAssignment: createAssignment,
      creatingAssignment,
      selectedAssignmentId: selectedAgent?.assignmentId,
      prompt,
      onPromptChange: (p: string) => {
        setPrompt(p);
        setRunKey(crypto.randomUUID());
      },
      consent,
      onConsentChange: setConsent,
      onSubmit: submit,
      executing,
      validationError: validation,
      canSubmit:
        !pending &&
        executionReady(workspace) &&
        modelAvailability === "available" &&
        Boolean(data.permissions["run:create"]) &&
        consent &&
        prompt.trim().length >= 5,
      workspace,
      permissionCanRun: Boolean(data.permissions["run:create"]),
      permissionCanAssign: Boolean(data.permissions["agent:assign"]),
      modelAvailability,
    }),
    [
      publishedAgents,
      activeVersionId,
      roleInput,
      creatingAssignment,
      selectedAgent?.assignmentId,
      prompt,
      consent,
      executing,
      validation,
      pending,
      workspace,
      modelAvailability,
      data.permissions,
    ],
  );

  return (
    <>
      <PageHeading
        eyebrow="OPERASIKAN"
        title="Eksekusi"
        description="Jalankan Research Agent melalui ARYN Core, lalu telusuri hasilnya."
      />

      <div className="detail-toolbar mb-4">
        <span className="mono">
          {isHistorical ? "HISTORICAL RUN" : "NEW EXECUTION"}
        </span>
        {isHistorical && (
          <Button
            variant="secondary"
            onClick={() => navigate(history ? "/runs/new" : "/runs")}
          >
            Eksekusi baru
          </Button>
        )}
      </div>

      {executing && (
        <Busy label="Core/ARYN Runtime sedang memproses eksekusi baru. Canvas mengikuti event run; trace per-node belum tersedia." />
      )}
      {selectedRun && !historical.version && (
        <Notice tone="warning">
          Konfigurasi historis run tidak tersedia. Pilihan form baru tidak
          digunakan sebagai penggantinya.
        </Notice>
      )}
      {selectedRun && (
        <Panel title="Captured Core execution">
          <Link to={`/brief?source_kind=run&source_id=${selectedRun.id}`}>
            Kumpulkan Core Run ke Brief
          </Link>
          {selectedRun.execution_claim_verified &&
            selectedRun.assignment_provenance_verified &&
            selectedRun.execution_provenance?.workflow && (
              <Link
                to={`/workflows/${selectedRun.execution_provenance.workflow.workflow_id}?run=${selectedRun.execution_provenance.workflow.run_id}`}
              >
                Workflow · {selectedRun.execution_provenance.workflow.node_id}
              </Link>
            )}
          {selectedRun?.execution_claim_verified &&
            selectedRun.execution_provenance?.automation && (
              <Link
                to={`/automations/${selectedRun.execution_provenance.automation.automation_id}#${selectedRun.execution_provenance.automation.occurrence_id}`}
              >
                Core Automation occurrence
              </Link>
            )}
          <p>
            Claim{" "}
            {selectedRun.execution_claim_verified
              ? "terverifikasi"
              : "belum terverifikasi"}{" "}
            · Version {selectedRun.agent_version_id || "Tidak tersedia"} ·
            Assignment {selectedRun.assignment_id || "Tidak tersedia"}
          </p>
          {selectedRun.status === "outcome_unknown" && (
            <Notice tone="warning">
              Outcome tidak pasti. Reservation tetap ditahan sampai Core
              memiliki evidence settlement; jangan menganggap run gagal atau
              dibatalkan.
            </Notice>
          )}
          {selectedRun.status === "stopping" && (
            <Notice tone="warning">
              Stop diminta; ACK belum membuktikan cancellation. Status terminal
              dan usage harus dikonfirmasi Core.
            </Notice>
          )}
          <p>
            Reservation{" "}
            {selectedRun.reserved_tokens == null
              ? "Tidak tersedia"
              : number(selectedRun.reserved_tokens)}{" "}
            token · Settlement{" "}
            {selectedRun.usage_settled == null
              ? "Tidak tersedia"
              : selectedRun.usage_settled
                ? "tercatat"
                : "belum selesai"}
          </p>
          {selectedRun.execution_claim_verified &&
            ["queued", "started", "running", "stopping"].includes(
              selectedRun.status,
            ) &&
            data.permissions["run:cancel"] && (
              <Button
                disabled={pending}
                variant="secondary"
                onClick={async () => {
                  try {
                    const receipt = await act(
                      `/runs/${selectedRun.id}/stop`,
                      {},
                      "Permintaan stop telah ditinjau Core.",
                    );
                    setStopMessage(
                      receipt.cancellation_confirmed === true
                        ? "Cancellation dikonfirmasi oleh status terminal Core."
                        : "Cancellation belum dikonfirmasi. ACK tidak membuktikan penghentian.",
                    );
                  } catch (failure) {
                    setStopMessage((failure as Error).message);
                  }
                }}
              >
                Minta stop melalui Core
              </Button>
            )}
          {stopMessage && <Notice>{stopMessage}</Notice>}
          <p>
            Trace per-node tidak tersedia untuk direct turn. Audit Core dan
            provenance tersimpan dapat ditelusuri.
          </p>
        </Panel>
      )}
      {historical.version && !historical.version.integrity_valid && (
        <Notice tone="warning">
          Integritas versi historis tidak valid. Konfigurasi tersimpan tidak
          dapat dianggap sebagai bukti konfigurasi saat eksekusi.
        </Notice>
      )}

      {/* Primary Interaction Surface: Execution Canvas & Inspector */}
      <div className="execution-canvas-workspace mb-6">
        <ArynCanvas
          key={
            isHistorical
              ? `historical:${runIdentifier}`
              : `new:${activeVersionId}`
          }
          mode="execution"
          initialNodes={execNodes}
          initialEdges={execEdges}
          run={selectedRun}
          version={canvasVersion}
          assignment={isHistorical ? historical.assignment : assigned}
          auditEvents={data.audit.filter(
            (e) => e.resource_id === selectedRun?.id,
          )}
          showInspectorByDefault={!isHistorical || Boolean(selectedRun)}
          executionForm={isHistorical ? undefined : executionFormConfig}
        />
      </div>

      {isHistorical && !selectedRun && (
        <Panel title="Hasil eksekusi" className="mb-6">
          <Empty
            title="Run yang dipilih tidak tersedia"
            description="Run tidak ditemukan pada proyek aktif. Pilih run yang tersedia dari riwayat."
          />
        </Panel>
      )}

      {/* Secondary Information Surface: Execution History Table */}
      <Panel
        className="mt-6"
        title="Riwayat eksekusi"
        subtitle="Tetap tersedia setelah halaman dimuat ulang."
      >
        {history ||
          (data.runs.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Instruksi</th>
                    <th>Status</th>
                    <th>Model</th>
                    <th>Token</th>
                    <th>Waktu</th>
                    <th>
                      <span className="sr-only">Aksi</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.runs.map((r) => {
                    const isCurrent = selectedRun?.id === r.id;
                    return (
                      <tr
                        key={r.id}
                        className={isCurrent ? "table-row-selected" : ""}
                      >
                        <td className="run-prompt-cell">{r.prompt}</td>
                        <td>
                          <Status value={r.status} />
                        </td>
                        <td className="mono">{r.model}</td>
                        <td className="mono">{number(r.total_tokens)}</td>
                        <td className="subtle">{date(r.created_at)}</td>
                        <td>
                          <Button
                            size="sm"
                            variant={isCurrent ? "secondary" : "ghost"}
                            onClick={() => viewResult(r.id)}
                            disabled={executing}
                            aria-label={`Lihat hasil eksekusi ${r.id}`}
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
              title="Riwayat masih kosong"
              description="Setiap eksekusi yang dimulai Core akan dicatat beserta status dan hasilnya."
            />
          ))}
      </Panel>
    </>
  );
}
