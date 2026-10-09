import { useEffect, useRef, useState, type ComponentProps } from "react";
import { Link, useBlocker, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, ApiError } from "../lib/api";
import { workspaceKey } from "../lib/workspace-types";
import type { Shared } from "../lib/types";
import {
  documentGraph,
  emptyDefinition,
  node,
  type Definition,
  type Version,
  type WorkflowRun,
  type WorkflowNode,
  type Page,
  type Artifact,
  type Deliverable,
} from "../lib/workflow-types";
import { PageHeading, Busy, Notice, Status } from "../components/shared";
import { Panel as WorkspacePanel } from "../components/workspace";
import { Button } from "../components/ui/button";
import "./workflow.css";
import { EvidenceLinks } from "./intelligence";

function Panel({ children, ...props }: ComponentProps<typeof WorkspacePanel>) {
  return (
    <WorkspacePanel {...props}>
      <div className="workflow-panel-body">{children}</div>
    </WorkspacePanel>
  );
}

function GraphNode({ data }: NodeProps) {
  const value = data.value as WorkflowNode;
  return (
    <div
      className={`workflow-node ${data.invalid ? "workflow-node-invalid" : ""}`}
    >
      <strong>{value.label}</strong>
      <small>
        {value.kind} · {value.input_schema} → {value.output_schema}
      </small>
      {value.kind !== "start" && (
        <Handle type="target" id="value" position={Position.Left} />
      )}
      {value.kind !== "end" &&
        (value.kind === "condition" ? (
          <>
            <Handle
              type="source"
              id="yes"
              position={Position.Right}
              style={{ top: "30%" }}
            />
            <Handle
              type="source"
              id="no"
              position={Position.Right}
              style={{ top: "70%" }}
            />
          </>
        ) : (
          <Handle type="source" id="value" position={Position.Right} />
        ))}
    </div>
  );
}
const nodeTypes = { typed: GraphNode };
type Assignment = {
  id: string;
  name: string;
  verified: boolean;
  references: { version_id: string };
};

export function Workflows({ workspace, project, data }: Shared) {
  const location = useLocation(),
    navigate = useNavigate(),
    client = useQueryClient();
  const org = workspace.organization.id,
    base = `/projects/${project}`;
  const segments = location.pathname.split("/");
  const id = segments[2] && segments[2] !== "new" ? segments[2] : "";
  const builder = segments[2] === "new" || segments[3] === "builder";
  const selectedRun = new URLSearchParams(location.search).get("run") || "";
  const [after, setAfter] = useState("");
  const [draft, setDraft] = useState<Definition>(emptyDefinition);
  const [saved, setSaved] = useState("");
  const [selected, select] = useState("input");
  const [edgeFrom, setEdgeFrom] = useState(""),
    [edgeTo, setEdgeTo] = useState("");
  const [port, setPort] = useState<"value" | "yes" | "no">("value");
  const [input, setInput] = useState(""),
    [consent, setConsent] = useState(false);
  const [versionId, setVersionId] = useState("");
  const [research, setResearch] = useState(""),
    [content, setContent] = useState("");
  const [notice, setNotice] = useState("");
  const [recovery, setRecovery] = useState<Definition>();
  const [assignmentCursor, setAssignmentCursor] = useState("");
  const [versionAfter, setVersionAfter] = useState(""),
    [runAfter, setRunAfter] = useState("");
  const [nextRoute, setNextRoute] = useState("");
  const startIdentity = useRef<{ fingerprint: string; key: string } | null>(
    null,
  );
  const canEdit = !!data.permissions["version:create"],
    canFreeze = !!data.permissions["version:publish"],
    canRun = !!data.permissions["run:create"];
  const key = (resource: string) =>
    workspaceKey(org, project, "workflow", resource);
  const list = useQuery({
    queryKey: key(`list:${after}`),
    queryFn: ({ signal }) =>
      api<Page<Definition>>(
        `${base}/workflows?after=${encodeURIComponent(after)}`,
        undefined,
        signal,
      ),
    enabled: !id && !builder,
    retry: false,
  });
  const definition = useQuery({
    queryKey: key(`definition:${id}`),
    queryFn: ({ signal }) =>
      api<Definition>(`${base}/workflows/${id}`, undefined, signal),
    enabled: !!id,
    retry: false,
  });
  const assignments = useQuery({
    queryKey: key(`assignments:${assignmentCursor}`),
    queryFn: ({ signal }) =>
      api<{ items: Assignment[]; next_cursor: string | null }>(
        `${base}/resources/assignments?limit=100${assignmentCursor ? `&cursor=${encodeURIComponent(assignmentCursor)}` : ""}`,
        undefined,
        signal,
      ),
    enabled: builder,
    retry: false,
  });
  const versions = useQuery({
    queryKey: key(`versions:${id}:${versionAfter}`),
    queryFn: ({ signal }) =>
      api<Page<Version>>(
        `${base}/workflows/${id}/versions?after=${encodeURIComponent(versionAfter)}`,
        undefined,
        signal,
      ),
    enabled: !!id && !builder,
    retry: false,
  });
  const runs = useQuery({
    queryKey: key(`runs:${id}:${runAfter}`),
    queryFn: ({ signal }) =>
      api<Page<WorkflowRun>>(
        `${base}/workflows/${id}/runs?after=${encodeURIComponent(runAfter)}`,
        undefined,
        signal,
      ),
    enabled: !!id && !builder,
    refetchInterval: 2000,
    retry: false,
  });
  const run = useQuery({
    queryKey: key(`run:${selectedRun}`),
    queryFn: ({ signal }) =>
      api<WorkflowRun>(
        `${base}/workflow-runs/${selectedRun}`,
        undefined,
        signal,
      ),
    enabled: !!selectedRun,
    refetchInterval: 2000,
    retry: false,
  });
  const selectedVersion = useQuery({
    queryKey: key(`version:${versionId}`),
    queryFn: ({ signal }) =>
      api<Version>(`${base}/workflow-versions/${versionId}`, undefined, signal),
    enabled: !!versionId && !builder,
    retry: false,
  });
  useEffect(() => {
    if (definition.data && (!saved || JSON.stringify(draft) === saved)) {
      setDraft(definition.data);
      setSaved(JSON.stringify(definition.data));
    }
  }, [definition.data]);
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) =>
      api<Record<string, unknown>>(base + path, body),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["studio", org, project] });
    },
  });
  const dirty =
    builder &&
    JSON.stringify(draft) !== (saved || JSON.stringify(emptyDefinition()));
  useEffect(() => {
    if (nextRoute && !mutation.isPending && !dirty) {
      if (location.pathname + location.search === nextRoute) setNextRoute("");
      else navigate(nextRoute);
    }
  }, [
    nextRoute,
    mutation.isPending,
    dirty,
    navigate,
    location.pathname,
    location.search,
  ]);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (dirty || mutation.isPending) &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (
        nextRoute &&
        !mutation.isPending &&
        !dirty &&
        blocker.location.pathname + blocker.location.search === nextRoute
      ) {
        blocker.proceed();
        return;
      }
      if (
        !mutation.isPending &&
        window.confirm("Tinggalkan perubahan workflow yang belum disimpan?")
      )
        blocker.proceed();
      else blocker.reset();
    }
  }, [blocker, mutation.isPending, dirty, nextRoute]);
  useEffect(() => {
    const unload = (e: BeforeUnloadEvent) => {
      if (dirty || mutation.isPending) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    const scope = (e: Event) => {
      if (
        mutation.isPending ||
        (dirty &&
          !window.confirm(
            "Tinggalkan perubahan workflow sebelum berganti proyek?",
          ))
      )
        e.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    window.addEventListener("aryn:scope-change", scope);
    return () => {
      window.removeEventListener("beforeunload", unload);
      window.removeEventListener("aryn:scope-change", scope);
    };
  }, [dirty, mutation.isPending]);
  async function save() {
    const response = await mutation.mutateAsync({
      path: `/workflows${id ? `/${id}` : ""}`,
      body: {
        name: draft.name,
        graph: draft.graph,
        positions: draft.positions,
        expected_revision: draft.revision,
      },
    });
    const value = response as unknown as Definition;
    setDraft(value);
    setSaved(JSON.stringify(value));
    setNotice("Draft tersimpan.");
    if (!id) {
      setNextRoute(`/workflows/${value.id}/builder`);
    }
  }
  async function action(path: string, body: unknown, message: string) {
    const result = await mutation.mutateAsync({ path, body });
    setNotice(message);
    return result;
  }
  const update = (value: WorkflowNode) =>
    setDraft({
      ...draft,
      graph: {
        ...draft.graph,
        nodes: draft.graph.nodes.map((n) => (n.id === value.id ? value : n)),
      },
    });
  const current = draft.graph.nodes.find((n) => n.id === selected);
  const error =
    definition.error ||
    list.error ||
    run.error ||
    selectedVersion.error ||
    assignments.error ||
    versions.error ||
    runs.error;
  if (error)
    return (
      <Notice tone="error">
        {error.message}
        <Button
          onClick={() =>
            client.invalidateQueries({ queryKey: ["studio", org, project] })
          }
        >
          Coba lagi
        </Button>
      </Notice>
    );
  if (id && !definition.data) return <Busy />;
  const available = (assignments.data?.items || []).filter((a) => a.verified);
  return (
    <>
      <PageHeading
        eyebrow="CORE WORKFLOW"
        title={
          builder
            ? "Workflow Builder"
            : id
              ? definition.data!.name
              : "Workflows"
        }
        description="Graph bertipe, eksekusi sequential, artifact handoff, dan review manusia."
      />
      {notice && <Notice tone="success">{notice}</Notice>}
      {mutation.error && (
        <Notice tone="error">
          {mutation.error.message} Input lokal tetap tersedia.
          {mutation.error instanceof ApiError && (
            <ul>
              {mutation.error.issues?.map((issue) => (
                <li key={issue.subject + issue.code}>
                  <Button
                    variant="secondary"
                    onClick={() => select(issue.subject)}
                  >
                    {issue.subject}: {issue.code}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Notice>
      )}
      {!id && !builder ? (
        <Panel title="Workflow registry">
          <Link to="/workflows/new">Buat workflow</Link>
          {list.isPending ? (
            <Busy />
          ) : (
            <>
              <ul>
                {list.data?.items.map((w) => (
                  <li key={w.id}>
                    <Link to={`/workflows/${w.id}`}>{w.name}</Link> · revision{" "}
                    {w.revision}
                  </li>
                ))}
              </ul>
              {!list.data?.items.length && <p>Belum ada workflow.</p>}
              <Button disabled={!after} onClick={() => setAfter("")}>
                Halaman pertama
              </Button>
              <Button
                disabled={!list.data?.next}
                onClick={() => setAfter(list.data!.next!)}
              >
                Berikutnya
              </Button>
            </>
          )}
        </Panel>
      ) : builder ? (
        <>
          <div className="workflow-actions">
            <Button
              disabled={!canEdit || mutation.isPending}
              onClick={() => void save().catch(() => {})}
            >
              Simpan draft
            </Button>
            <Button
              disabled={!id || mutation.isPending}
              onClick={async () => {
                setRecovery(draft);
                const response = await definition.refetch();
                if (response.data) {
                  setDraft(response.data);
                  setSaved(JSON.stringify(response.data));
                  setNotice(
                    "Draft server dimuat; input sebelumnya dapat dipulihkan.",
                  );
                }
              }}
            >
              Muat ulang draft
            </Button>
            <Button
              disabled={!recovery || mutation.isPending}
              onClick={() => {
                setDraft({
                  ...recovery!,
                  id: draft.id,
                  revision: draft.revision,
                });
                setRecovery(undefined);
              }}
            >
              Pulihkan input lokal
            </Button>
            <Button
              disabled={!id || dirty || !canEdit || mutation.isPending}
              onClick={() =>
                void action(
                  `/workflows/${id}/validate`,
                  {},
                  "Validator Core menerima graph.",
                ).catch(() => {})
              }
            >
              Validasi server
            </Button>
            <Button
              disabled={!id || dirty || !canFreeze || mutation.isPending}
              onClick={() =>
                void action(
                  `/workflows/${id}/versions`,
                  { expected_revision: draft.revision },
                  "Versi immutable tersimpan.",
                ).catch(() => {})
              }
            >
              Bekukan versi
            </Button>
            {id && <Link to={`/workflows/${id}`}>Detail & eksekusi</Link>}
            <span role="status">
              {dirty ? "Perubahan belum disimpan" : "Tersimpan"} · revision{" "}
              {draft.revision}
            </span>
          </div>
          <label>
            Nama workflow
            <input
              value={draft.name}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <Panel title="Node palette">
            <div className="workflow-actions">
              {(
                [
                  "start",
                  "agent",
                  "condition",
                  "handoff",
                  "review",
                  "end",
                ] as const
              ).map((kind) => (
                <Button
                  key={kind}
                  disabled={!canEdit}
                  onClick={() => {
                    const value = node(
                      kind,
                      `${kind}_${draft.graph.nodes.length + 1}`,
                    );
                    setDraft({
                      ...draft,
                      graph: {
                        ...draft.graph,
                        nodes: [...draft.graph.nodes, value],
                      },
                    });
                    select(value.id);
                  }}
                >
                  Tambah {kind}
                </Button>
              ))}
            </div>
            <label>
              Research assignment
              <select
                value={research}
                onChange={(e) => setResearch(e.target.value)}
              >
                <option value="">Pilih versi published terverifikasi</option>
                {available.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.references.version_id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Content assignment
              <select
                value={content}
                onChange={(e) => setContent(e.target.value)}
              >
                <option value="">Pilih versi published terverifikasi</option>
                {available.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.references.version_id}
                  </option>
                ))}
              </select>
            </label>
            <Button
              disabled={!canEdit || !research || !content}
              onClick={() => {
                const r = available.find((a) => a.id === research)!,
                  c = available.find((a) => a.id === content)!;
                setDraft({
                  ...draft,
                  positions: [],
                  graph: documentGraph(
                    { id: r.id, version_id: r.references.version_id },
                    { id: c.id, version_id: c.references.version_id },
                  ),
                });
                select("research");
              }}
            >
              Gunakan Research → Content → Website
            </Button>
            <p>
              Website memakai renderer static-document-v1. Tidak ada publikasi
              internet.
            </p>
            <Button
              disabled={!assignmentCursor}
              onClick={() => setAssignmentCursor("")}
            >
              Assignment pertama
            </Button>
            <Button
              disabled={!assignments.data?.next_cursor}
              onClick={() =>
                setAssignmentCursor(assignments.data!.next_cursor!)
              }
            >
              Assignment berikutnya
            </Button>
          </Panel>
          <div className="workflow-editor">
            <div className="workflow-canvas" aria-label="Canvas workflow">
              <ReactFlow
                nodeTypes={nodeTypes}
                colorMode={
                  document.documentElement.dataset.theme === "light"
                    ? "light"
                    : "dark"
                }
                nodes={draft.graph.nodes.map((n, i) => ({
                  id: n.id,
                  type: "typed",
                  data: {
                    value: n,
                    invalid:
                      mutation.error instanceof ApiError &&
                      mutation.error.issues?.some(
                        (issue) => issue.subject === n.id,
                      ),
                  },
                  position: draft.positions.find((p) => p.id === n.id) || {
                    x: (i % 3) * 250,
                    y: Math.floor(i / 3) * 140,
                  },
                }))}
                edges={draft.graph.edges.map((e) => ({
                  ...e,
                  sourceHandle: e.source_port,
                  targetHandle: e.target_port,
                  label: e.source_port,
                }))}
                onNodeClick={(_, n) => select(n.id)}
                onNodesChange={(changes) => {
                  if (!canEdit) return;
                  const moved = changes.filter(
                    (c) => c.type === "position" && c.position,
                  );
                  if (moved.length)
                    setDraft((previous) => ({
                      ...previous,
                      positions: moved.reduce(
                        (positions, change) =>
                          change.type === "position" && change.position
                            ? [
                                ...positions.filter((p) => p.id !== change.id),
                                {
                                  id: change.id,
                                  x: change.position.x,
                                  y: change.position.y,
                                },
                              ]
                            : positions,
                        previous.positions,
                      ),
                    }));
                }}
                onNodeDragStop={(_, n) =>
                  setDraft({
                    ...draft,
                    positions: [
                      ...draft.positions.filter((p) => p.id !== n.id),
                      { id: n.id, ...n.position },
                    ],
                  })
                }
                nodesDraggable={canEdit}
                nodesConnectable={canEdit}
                onConnect={(c) => {
                  if (c.source && c.target)
                    setDraft({
                      ...draft,
                      graph: {
                        ...draft.graph,
                        edges: [
                          ...draft.graph.edges,
                          {
                            id: `edge_${Date.now()}`,
                            source: c.source,
                            target: c.target,
                            source_port: (c.sourceHandle || "value") as
                              "value" | "yes" | "no",
                            target_port: "value",
                          },
                        ],
                      },
                    });
                }}
                fitView
              >
                <Background />
                <Controls />
              </ReactFlow>
            </div>
            <Panel title="Typed inspector">
              <label>
                Node terpilih
                <select
                  value={selected}
                  onChange={(e) => select(e.target.value)}
                >
                  {draft.graph.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label} · {n.kind}
                    </option>
                  ))}
                </select>
              </label>
              {current && (
                <fieldset disabled={!canEdit}>
                  <label>
                    Label node
                    <input
                      value={current.label}
                      onChange={(e) =>
                        update({ ...current, label: e.target.value })
                      }
                    />
                  </label>
                  {(["input_schema", "output_schema"] as const).map((field) => (
                    <label key={field}>
                      {field}
                      <select
                        value={current[field]}
                        onChange={(e) =>
                          update({ ...current, [field]: e.target.value })
                        }
                      >
                        {["text", "brief", "content", "website"].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                  {current.kind === "agent" && (
                    <>
                      <label>
                        Target tugas
                        <select
                          value={
                            current.renderer || current.assignment_id || ""
                          }
                          onChange={(e) => {
                            const a = available.find(
                              (a) => a.id === e.target.value,
                            );
                            update({
                              ...current,
                              renderer:
                                e.target.value === "static-document-v1"
                                  ? "static-document-v1"
                                  : null,
                              assignment_id: a?.id || null,
                              agent_version_id:
                                a?.references.version_id || null,
                            });
                          }}
                        >
                          <option value="">Pilih assignment</option>
                          <option value="static-document-v1">
                            Static document renderer v1
                          </option>
                          {available.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.name} · {a.references.version_id}
                            </option>
                          ))}
                        </select>
                      </label>
                      <p>
                        Pin:{" "}
                        {current.agent_version_id ||
                          current.renderer ||
                          "Belum dipilih"}
                      </p>
                    </>
                  )}
                  {current.predicate && (
                    <>
                      <label>
                        Predicate operator
                        <select
                          value={current.predicate.operator}
                          onChange={(e) =>
                            update({
                              ...current,
                              predicate: {
                                ...current.predicate!,
                                operator: e.target.value as
                                  "contains" | "equals" | "nonempty",
                              },
                            })
                          }
                        >
                          {["contains", "equals", "nonempty"].map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Predicate literal
                        <input
                          maxLength={100}
                          value={current.predicate.literal}
                          onChange={(e) =>
                            update({
                              ...current,
                              predicate: {
                                ...current.predicate!,
                                literal: e.target.value,
                              },
                            })
                          }
                        />
                      </label>
                    </>
                  )}
                  <Button
                    onClick={() => {
                      setDraft({
                        ...draft,
                        positions: draft.positions.filter(
                          (p) => p.id !== current.id,
                        ),
                        graph: {
                          nodes: draft.graph.nodes.filter(
                            (n) => n.id !== current.id,
                          ),
                          edges: draft.graph.edges.filter(
                            (e) =>
                              e.source !== current.id &&
                              e.target !== current.id,
                          ),
                        },
                      });
                      select(
                        draft.graph.nodes.find((n) => n.id !== current.id)
                          ?.id || "",
                      );
                    }}
                  >
                    Hapus node
                  </Button>
                </fieldset>
              )}
            </Panel>
          </div>
          <Panel title="Editor graph dengan keyboard">
            <ol>
              {draft.graph.nodes.map((n) => (
                <li key={n.id}>
                  <Button variant="secondary" onClick={() => select(n.id)}>
                    {n.label} · {n.id} · {n.input_schema} → {n.output_schema}
                  </Button>
                </li>
              ))}
            </ol>
            <ul>
              {draft.graph.edges.map((e) => (
                <li key={e.id}>
                  {e.source}.{e.source_port} → {e.target}.{e.target_port}{" "}
                  <Button
                    disabled={!canEdit}
                    onClick={() =>
                      setDraft({
                        ...draft,
                        graph: {
                          ...draft.graph,
                          edges: draft.graph.edges.filter((x) => x.id !== e.id),
                        },
                      })
                    }
                  >
                    Hapus edge {e.id}
                  </Button>
                </li>
              ))}
            </ul>
            <div className="workflow-fields">
              <label>
                Source node
                <select
                  value={edgeFrom}
                  onChange={(e) => setEdgeFrom(e.target.value)}
                >
                  <option value="">Pilih</option>
                  {draft.graph.nodes.map((n) => (
                    <option key={n.id}>{n.id}</option>
                  ))}
                </select>
              </label>
              <label>
                Source port
                <select
                  value={port}
                  onChange={(e) => setPort(e.target.value as typeof port)}
                >
                  {["value", "yes", "no"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Target node
                <select
                  value={edgeTo}
                  onChange={(e) => setEdgeTo(e.target.value)}
                >
                  <option value="">Pilih</option>
                  {draft.graph.nodes.map((n) => (
                    <option key={n.id}>{n.id}</option>
                  ))}
                </select>
              </label>
              <Button
                disabled={!canEdit || !edgeFrom || !edgeTo}
                onClick={() =>
                  setDraft({
                    ...draft,
                    graph: {
                      ...draft.graph,
                      edges: [
                        ...draft.graph.edges,
                        {
                          id: `edge_${Date.now()}`,
                          source: edgeFrom,
                          target: edgeTo,
                          source_port: port,
                          target_port: "value",
                        },
                      ],
                    },
                  })
                }
              >
                Hubungkan node
              </Button>
            </div>
            <p>
              Semua hubungan divalidasi server sebelum pembekuan versi dan
              eksekusi.
            </p>
          </Panel>
        </>
      ) : (
        <>
          <Panel title="Versi immutable">
            <Link to={`/workflows/${id}/builder`}>Edit graph</Link>
            <label>
              Versi workflow
              <select
                value={versionId}
                onChange={(e) => setVersionId(e.target.value)}
              >
                <option value="">Pilih versi</option>
                {versions.data?.items.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.id} · {v.digest}
                  </option>
                ))}
              </select>
            </label>
            {selectedVersion.data && (
              <>
                <Button
                  disabled={!versionAfter}
                  onClick={() => setVersionAfter("")}
                >
                  Versi pertama
                </Button>
                <Button
                  disabled={!versions.data?.next}
                  onClick={() => setVersionAfter(versions.data!.next!)}
                >
                  Versi berikutnya
                </Button>
                <>
                  <p className="workflow-wrap">
                    Hash graph: {selectedVersion.data.digest}
                  </p>
                  <details>
                    <summary>Graph version detail</summary>
                    <pre className="workflow-json">
                      {JSON.stringify(selectedVersion.data.graph, null, 2)}
                    </pre>
                  </details>
                </>
              </>
            )}
            <label>
              Input workflow
              <textarea
                value={input}
                maxLength={8000}
                onChange={(e) => setInput(e.target.value)}
              />
            </label>
            <label className="check-row workflow-consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              Saya menyetujui penggunaan model untuk workflow ini.
            </label>
            <Button
              disabled={
                !canRun ||
                !versionId ||
                !input ||
                !consent ||
                mutation.isPending
              }
              onClick={() => {
                const fingerprint = JSON.stringify({ versionId, input });
                if (startIdentity.current?.fingerprint !== fingerprint)
                  startIdentity.current = {
                    fingerprint,
                    key: crypto.randomUUID(),
                  };
                void action(
                  `/workflows/${id}/runs`,
                  {
                    version_id: versionId,
                    input,
                    idempotency_key: startIdentity.current.key,
                    allow_remote_model: true,
                  },
                  "Eksekusi tersimpan.",
                )
                  .then((r) => {
                    startIdentity.current = null;
                    setNextRoute(`/workflows/${id}?run=${r.id}`);
                  })
                  .catch(() => {});
              }}
            >
              Jalankan workflow
            </Button>
          </Panel>
          <Panel title="Run history">
            <ul>
              {runs.data?.items.map((r) => (
                <li key={r.id}>
                  <Link to={`/workflows/${id}?run=${r.id}`}>{r.id}</Link>{" "}
                  <Status value={r.status} />
                </li>
              ))}
            </ul>
            {!runs.data?.items.length && <p>Belum ada run.</p>}
            <Button disabled={!runAfter} onClick={() => setRunAfter("")}>
              Run pertama
            </Button>
            <Button
              disabled={!runs.data?.next}
              onClick={() => setRunAfter(runs.data!.next!)}
            >
              Run berikutnya
            </Button>
          </Panel>
          {run.data && run.data.workflow_id === id && (
            <EvidenceLinks
              organization={org}
              project={project}
              kind="workflow_run"
              id={run.data.id}
            />
          )}
          {run.data && run.data.workflow_id === id && (
            <Timeline
              run={run.data}
              canCancel={!!data.permissions["run:cancel"]}
              cancel={() =>
                void action(
                  `/workflow-runs/${run.data!.id}/stop`,
                  {},
                  "Permintaan stop tercatat; outcome Core tetap diperiksa.",
                ).catch(() => {})
              }
            />
          )}
        </>
      )}
    </>
  );
}

function Timeline({
  run,
  canCancel,
  cancel,
}: {
  run: WorkflowRun;
  canCancel: boolean;
  cancel: () => void;
}) {
  return (
    <Panel title="Persisted execution timeline">
      <p className="workflow-wrap">
        {run.id} · <Status value={run.status} /> · version {run.version_id}
      </p>
      {run.error_code && (
        <Notice tone="warning">
          {run.error_code} · Eksekusi tidak diulang otomatis.
        </Notice>
      )}
      <ol>
        {run.tasks.map((t) => (
          <li key={t.node_id}>
            <strong>{t.node_id}</strong> <Status value={t.status} />
            {t.core_run_id && (
              <Link to={`/runs/${t.core_run_id}`}>Core Console</Link>
            )}
            {t.input_artifact_id && (
              <Link to={`/outputs/${t.input_artifact_id}`}>Input artifact</Link>
            )}
            {t.output_artifact_id && (
              <Link to={`/outputs/${t.output_artifact_id}`}>
                Output artifact
              </Link>
            )}
          </li>
        ))}
      </ol>
      {run.artifact_id && (
        <Link to={`/outputs/${run.artifact_id}`}>Buka hasil & review</Link>
      )}
      <Button
        disabled={
          !canCancel || !["running", "waiting_review"].includes(run.status)
        }
        onClick={cancel}
      >
        Stop workflow
      </Button>
    </Panel>
  );
}

export function Outputs({ workspace, project, data }: Shared) {
  const org = workspace.organization.id,
    client = useQueryClient(),
    location = useLocation();
  const id = location.pathname.split("/")[2] || "",
    base = `/projects/${project}`;
  const [after, setAfter] = useState(""),
    [reason, setReason] = useState("");
  const [reviewAfter, setReviewAfter] = useState(""),
    [queueAfter, setQueueAfter] = useState("");
  const key = (name: string) => workspaceKey(org, project, "outputs", name);
  const list = useQuery({
    queryKey: key(`list:${after}`),
    queryFn: ({ signal }) =>
      api<Page<Artifact>>(
        `${base}/outputs?after=${encodeURIComponent(after)}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const reviews = useQuery({
    queryKey: key(`reviews:${reviewAfter}`),
    queryFn: ({ signal }) =>
      api<Page<Deliverable>>(
        `${base}/deliverables?after=${encodeURIComponent(reviewAfter)}`,
        undefined,
        signal,
      ),
    retry: false,
  });
  const queue = useQuery({
    queryKey: key(`queue:${queueAfter}`),
    queryFn: ({ signal }) =>
      api<Page<WorkflowRun>>(
        `${base}/review-queue?after=${encodeURIComponent(queueAfter)}`,
        undefined,
        signal,
      ),
    enabled: !id,
    retry: false,
  });
  const receipt = useQuery({
    queryKey: key(`deliverable:${id}`),
    queryFn: ({ signal }) =>
      api<Deliverable>(`${base}/deliverables/${id}`, undefined, signal),
    enabled: id.startsWith("deliverable_"),
    retry: false,
  });
  const artifactId = id.startsWith("deliverable_")
    ? receipt.data?.artifact_id || ""
    : id;
  const artifact = useQuery({
    queryKey: key(artifactId),
    queryFn: ({ signal }) =>
      api<Artifact>(`${base}/outputs/${artifactId}`, undefined, signal),
    enabled: !!artifactId && !receipt.error,
    retry: false,
  });
  const run = useQuery({
    queryKey: key(`run:${artifact.data?.workflow_run_id}`),
    queryFn: ({ signal }) =>
      api<WorkflowRun>(
        `${base}/workflow-runs/${artifact.data!.workflow_run_id}`,
        undefined,
        signal,
      ),
    enabled: !!artifact.data && !artifact.error,
    retry: false,
  });
  const preview = useQuery({
    queryKey: key(`preview:${artifactId}`),
    queryFn: async ({ signal }) => {
      const r = await fetch(`/api${base}/outputs/${artifactId}/preview`, {
        signal,
        credentials: "same-origin",
      });
      if (!r.ok) throw Error(`Preview tidak tersedia (${r.status}).`);
      return r.text();
    },
    enabled: !!artifact.data && !artifact.error && !!run.data && !run.error,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: (decision: string) =>
      api(`${base}/workflow-runs/${artifact.data!.workflow_run_id}/review`, {
        digest: artifact.data!.digest,
        decision,
        reason,
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["studio", org, project] });
    },
  });
  const error =
    list.error ||
    artifact.error ||
    run.error ||
    reviews.error ||
    preview.error ||
    queue.error ||
    receipt.error;
  if (error)
    return (
      <Notice tone="error">
        {error.message}
        <Button
          onClick={() =>
            client.invalidateQueries({ queryKey: ["studio", org, project] })
          }
        >
          Coba lagi
        </Button>
      </Notice>
    );
  const a = artifact.data;
  return (
    <>
      <PageHeading
        eyebrow="ARTIFACTS & DELIVERABLES"
        title="Outputs"
        description="Hasil scoped, integrity verified, dengan lineage dan review exact hash."
      />
      {!id ? (
        <>
          <Panel title="Artifact inventory">
            {list.isPending ? (
              <Busy />
            ) : (
              <>
                <ul>
                  {list.data?.items.map((a) => (
                    <li key={a.id}>
                      <Link to={`/outputs/${a.id}`}>
                        {a.schema_name} · {a.id}
                      </Link>{" "}
                      · {a.length} bytes
                    </li>
                  ))}
                </ul>
                {!list.data?.items.length && <p>Belum ada artifact.</p>}
                <Button disabled={!after} onClick={() => setAfter("")}>
                  Halaman pertama
                </Button>
                <Button
                  disabled={!list.data?.next}
                  onClick={() => setAfter(list.data!.next!)}
                >
                  Berikutnya
                </Button>
              </>
            )}
          </Panel>
          <Panel title="Review decisions">
            <ul>
              {reviews.data?.items.map((r) => (
                <li key={r.id}>
                  <Link to={`/outputs/${r.id}`}>
                    {r.decision} · {r.id}
                  </Link>{" "}
                  · {r.reviewer} · {r.created_at} · {r.reason}
                </li>
              ))}
            </ul>
            <Button disabled={!reviewAfter} onClick={() => setReviewAfter("")}>
              Review pertama
            </Button>
            <Button
              disabled={!reviews.data?.next}
              onClick={() => setReviewAfter(reviews.data!.next!)}
            >
              Review berikutnya
            </Button>
            <p>
              Review pending tersedia pada hasil workflow berstatus
              waiting_review.
            </p>
          </Panel>
          <Panel title="Reviewer queue">
            <ul>
              {queue.data?.items.map((run) => (
                <li key={run.id}>
                  <Link to={`/outputs/${run.artifact_id}`}>
                    {run.id} · waiting_review
                  </Link>
                </li>
              ))}
            </ul>
            {!queue.data?.items.length && <p>Tidak ada review pending.</p>}
            <Button disabled={!queueAfter} onClick={() => setQueueAfter("")}>
              Antrean pertama
            </Button>
            <Button
              disabled={!queue.data?.next}
              onClick={() => setQueueAfter(queue.data!.next!)}
            >
              Antrean berikutnya
            </Button>
          </Panel>
        </>
      ) : !a || !run.data ? (
        <Busy />
      ) : (
        <>
          <Panel title="Artifact provenance">
            <Link
              to={`/brief?source_kind=artifact&source_id=${a.id}&workflow_run=${a.workflow_run_id}`}
            >
              Kumpulkan artifact ke Brief
            </Link>
            <dl>
              {Object.entries(a).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd className="workflow-wrap">
                    {Array.isArray(v) ? v.join(", ") : v || "Tidak berlaku"}
                  </dd>
                </div>
              ))}
            </dl>
            <Link to={`/workflows/${run.data.workflow_id}?run=${run.data.id}`}>
              Workflow & timeline
            </Link>
            {a.core_run_id && (
              <Link to={`/runs/${a.core_run_id}`}>Captured Core Console</Link>
            )}
            {a.source_artifact_id && (
              <Link to={`/outputs/${a.source_artifact_id}`}>
                Source artifact
              </Link>
            )}
            <a href={`/api${base}/outputs/${a.id}/download`} download>
              Download artifact
            </a>
          </Panel>
          <EvidenceLinks
            organization={org}
            project={project}
            kind="artifact"
            id={a.id}
          />
          <Panel title="Inert preview">
            {preview.isPending ? (
              <Busy />
            ) : a.mime === "text/html" ? (
              <iframe
                title="Website artifact preview"
                sandbox=""
                srcDoc={preview.data}
                className="workflow-preview"
              />
            ) : (
              <pre className="workflow-json">{preview.data}</pre>
            )}
            <p>
              Website hanya dokumen staging: opaque sandbox, tanpa script,
              network, form, atau deployment.
            </p>
          </Panel>
          <Panel title="Human review">
            <Status value={run.data.status} />
            <p className="workflow-wrap">Exact hash {a.digest}</p>
            {reviews.data?.items
              .filter((r) => r.artifact_id === a.id)
              .map((r) => (
                <p key={r.id}>
                  {r.decision} · {r.reviewer} · {r.reason}
                </p>
              ))}
            {run.data.artifact_id === a.id &&
              run.data.status === "waiting_review" && (
                <>
                  <label>
                    Alasan review
                    <textarea
                      value={reason}
                      maxLength={1000}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  <div className="workflow-actions">
                    {["accepted", "rejected"].map((decision) => (
                      <Button
                        key={decision}
                        disabled={
                          !data.permissions["version:approve"] ||
                          !reason ||
                          mutation.isPending
                        }
                        onClick={() => mutation.mutate(decision)}
                      >
                        {decision === "accepted"
                          ? "Terima deliverable"
                          : "Tolak deliverable"}
                      </Button>
                    ))}
                  </div>
                </>
              )}
            {mutation.error && (
              <Notice tone="error">{mutation.error.message}</Notice>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
