import { useEffect, useRef, useState } from "react";
import {
  Link,
  useBlocker,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useNodesState,
  type NodeProps,
  type Node,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../lib/api";
import { workspaceKey } from "../lib/workspace-types";
import type { Blueprint, Shared } from "../lib/types";
import {
  draftDefinition,
  sections,
  validateDraft,
  serializeDefinition,
  type AgentDraft,
  type WorkingCopy,
  type EditorLayout,
  type Section,
} from "../lib/agent-editor-types";
import { Button } from "../components/ui/button";
import { Busy, Notice, PageHeading } from "../components/shared";
import { Modal } from "../components/ui/dialog";
import "./agent-editor.css";

function DefinitionNode({
  data,
}: NodeProps<Node<{ label: string; summary: string; selected: boolean }>>) {
  return (
    <div className={`definition-node ${data.selected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <strong>{data.label}</strong>
      <small>{data.summary}</small>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}
const nodeTypes = { definition: DefinitionNode };
const edges = sections.slice(1).map(([id]) => ({
  id: `identity-${id}`,
  source: "identity",
  target: id,
  selectable: false,
  focusable: false,
  style: { stroke: "var(--primary)", opacity: 0.45 },
}));
const policyKeys = {
  output: "output_contract",
  constraints: "constraints",
  tools: "tool_policy",
  budget: "budget_policy",
  evaluation: "evaluation_reference",
  model: "model_policy",
} as const;

function JsonField({
  label,
  value,
  onChange,
  disabled,
  draft,
  setDraft,
}: {
  label: string;
  value: unknown;
  onChange: (value: Record<string, unknown> | null) => void;
  disabled: boolean;
  draft?: string;
  setDraft: (text?: string) => void;
}) {
  const text = draft ?? JSON.stringify(value, null, 2);
  const error =
    draft === undefined ? "" : "JSON belum valid; input lokal belum disimpan.";
  return (
    <label>
      {label}
      <textarea
        aria-label={label}
        disabled={disabled}
        rows={8}
        value={text}
        onChange={(e) => {
          try {
            const parsed: unknown = JSON.parse(e.target.value);
            if (
              parsed !== null &&
              (typeof parsed !== "object" || Array.isArray(parsed))
            )
              throw Error("Gunakan object JSON atau null.");
            setDraft(undefined);
            onChange(parsed as Record<string, unknown> | null);
          } catch {
            setDraft(e.target.value);
          }
        }}
        aria-invalid={!!error}
      />
      {error && <span role="alert">{error}</span>}
    </label>
  );
}

function SectionFields({
  section,
  value,
  update,
  disabled,
  models,
  jsonDrafts,
  setJsonDraft,
}: {
  section: Section;
  value: AgentDraft;
  update: (value: AgentDraft) => void;
  disabled: boolean;
  models: Shared["workspace"]["models"];
  jsonDrafts: Record<string, string>;
  setJsonDraft: (field: string, text?: string) => void;
}) {
  const scalar = (
    key: "version_number" | "role" | "objective" | "owner" | "system_prompt",
    label: string,
    multiline = false,
  ) => (
    <label key={key}>
      {label}
      {multiline ? (
        <textarea
          aria-label={label}
          rows={key === "system_prompt" ? 10 : 3}
          disabled={disabled}
          value={value[key] || ""}
          onChange={(e) => update({ ...value, [key]: e.target.value })}
        />
      ) : (
        <input
          aria-label={label}
          disabled={disabled}
          value={value[key] || ""}
          onChange={(e) =>
            update({
              ...value,
              [key]: e.target.value || (key === "owner" ? null : ""),
            })
          }
        />
      )}
    </label>
  );
  if (section === "identity")
    return (
      <>
        {scalar("version_number", "Nomor versi")}
        {scalar("role", "Role")}
        {scalar("objective", "Objective", true)}
        {scalar("owner", "Owner")}
        <JsonField
          label="Metadata"
          draft={jsonDrafts.metadata}
          setDraft={(text) => setJsonDraft("metadata", text)}
          value={value.metadata}
          onChange={(metadata) =>
            update({ ...value, metadata: metadata || {} })
          }
          disabled={disabled}
        />
        <p>
          Schema version <code>{value.schema_version}</code>
        </p>
      </>
    );
  if (section === "instructions")
    return scalar("system_prompt", "Instruksi sistem", true);
  const key = policyKeys[section];
  const policy = value[key];
  return (
    <>
      {section === "model" && (
        <label>
          Model
          <select
            aria-label="Model"
            disabled={disabled}
            value={value.model}
            onChange={(e) =>
              update({
                ...value,
                model: e.target.value,
                model_policy: {
                  ...value.model_policy,
                  primary_model: e.target.value,
                },
              })
            }
          >
            <option value="">Pilih model</option>
            {models.map((model) => (
              <option
                key={model.model_id}
                value={model.model_id}
                disabled={model.availability !== "available"}
              >
                {model.display_name} · {model.availability}
              </option>
            ))}
          </select>
        </label>
      )}
      {Object.entries(policy).map(([field, fieldValue]) => {
        const locked =
          disabled ||
          (section === "tools" && field !== "forbidden_tools") ||
          (section === "model" &&
            ["primary_model", "provider", "allow_fallback"].includes(field));
        const label = field.replaceAll("_", " ");
        const change = (next: unknown) => {
          const updated = { ...value, [key]: { ...policy, [field]: next } };
          if (section === "model" && field === "temperature")
            updated.temperature = Number(next);
          if (section === "model" && field === "max_tokens")
            updated.max_tokens = Number(next);
          update(updated);
        };
        if (section === "output" && field === "format")
          return (
            <label key={field}>
              {label}
              <select
                aria-label={label}
                disabled={locked}
                value={String(fieldValue)}
                onChange={(event) => change(event.target.value)}
              >
                {["text", "markdown", "json"].map((format) => (
                  <option key={format}>{format}</option>
                ))}
              </select>
            </label>
          );
        if (field === "schema_definition")
          return (
            <JsonField
              key={field}
              label={label}
              value={fieldValue}
              onChange={change}
              disabled={locked}
              draft={jsonDrafts[`${key}.${field}`]}
              setDraft={(text) => setJsonDraft(`${key}.${field}`, text)}
            />
          );
        if (Array.isArray(fieldValue))
          return (
            <label key={field}>
              {label}
              <textarea
                aria-label={label}
                disabled={locked}
                rows={3}
                value={fieldValue.join("\n")}
                onChange={(e) =>
                  change(e.target.value.split("\n").filter(Boolean))
                }
              />
              <small>Satu nilai per baris.</small>
            </label>
          );
        if (typeof fieldValue === "boolean")
          return (
            <label className="checkbox-row" key={field}>
              <input
                type="checkbox"
                aria-label={label}
                disabled={locked}
                checked={fieldValue}
                onChange={(e) => change(e.target.checked)}
              />
              {label}
            </label>
          );
        if (typeof fieldValue === "number")
          return (
            <label key={field}>
              {label}
              <input
                type="number"
                aria-label={label}
                step="any"
                disabled={locked}
                value={fieldValue}
                onChange={(e) => change(Number(e.target.value))}
              />
            </label>
          );
        return (
          <label key={field}>
            {label}
            <input
              aria-label={label}
              disabled={locked}
              value={String(fieldValue ?? "")}
              onChange={(e) => change(e.target.value || null)}
            />
          </label>
        );
      })}
      {section === "tools" && (
        <Notice>
          Core mempertahankan tool grants kosong dan menolak akses jaringan,
          host, file, serta eksekusi kode.
        </Notice>
      )}
    </>
  );
}

export function AgentBuilder({
  blueprint,
  data,
  workspace,
  project,
  pending,
  act,
  theme = "dark",
}: Shared & { blueprint: Blueprint; theme?: string }) {
  const [params] = useSearchParams();
  const source =
    data.versions.find((version) => version.id === params.get("source")) ||
    data.versions.find(
      (version) =>
        version.configuration_loaded !== false &&
        version.blueprint_id === blueprint.id,
    );
  const path = `/blueprints/${blueprint.id}`;
  const organization = workspace.organization.id;
  const navigate = useNavigate();
  const working = useQuery({
    queryKey: workspaceKey(organization, project, "working-copy", blueprint.id),
    queryFn: ({ signal }) =>
      api<WorkingCopy>(
        `/projects/${project}${path}/working-copy`,
        undefined,
        signal,
      ),
    retry: false,
  });
  const layout = useQuery({
    queryKey: workspaceKey(
      organization,
      project,
      "editor-layout",
      blueprint.id,
    ),
    queryFn: ({ signal }) =>
      api<EditorLayout>(
        `/projects/${project}${path}/editor-layout`,
        undefined,
        signal,
      ),
    retry: false,
  });
  const [value, setValue] = useState<AgentDraft>(() =>
    draftDefinition(
      blueprint,
      source,
      workspace.models.find((m) => m.availability === "available")?.model_id,
    ),
  );
  const [saved, setSaved] = useState("");
  const [generation, setGeneration] = useState(0);
  const [layoutGeneration, setLayoutGeneration] = useState(0);
  const [section, setSection] = useState<Section>("identity");
  const [formView, setFormView] = useState(false);
  const [inspector, setInspector] = useState(true);
  const [history, setHistory] = useState<AgentDraft[]>([]);
  const [error, setError] = useState("");
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({});
  const [recovery, setRecovery] = useState<{
    definition: AgentDraft;
    jsonDrafts: Record<string, string>;
  } | null>(null);
  const setJsonDraft = (field: string, text?: string) =>
    setJsonDrafts((current) => {
      const next = { ...current };
      if (text === undefined) delete next[field];
      else next[field] = text;
      return next;
    });
  const [layoutDirty, setLayoutDirty] = useState(false);
  const viewport = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const initialized = useRef(false);
  const [nodes, setNodes, onNodesChange] = useNodesState(
    sections.map(([id, label], index) => ({
      id,
      type: "definition",
      position: {
        x: index === 0 ? 40 : 400 + ((index - 1) % 2) * 310,
        y: index === 0 ? 180 : Math.floor((index - 1) / 2) * 150 + 40,
      },
      data: {
        label,
        summary: "Konfigurasi agent",
        selected: id === "identity",
      },
    })),
  );
  const dirty =
    serializeDefinition(value) !== saved || Object.keys(jsonDrafts).length > 0;
  const editable = !!data.permissions["version:create"];
  const writable = editable && !pending;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      editable &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );
  useEffect(() => {
    if (!working.data || initialized.current) return;
    const definition = working.data.definition || value;
    setValue(definition);
    setSaved(working.data.definition ? serializeDefinition(definition) : "");
    setGeneration(working.data.generation);
    initialized.current = true;
  }, [working.data, value]);
  useEffect(() => {
    if (!layout.data || layoutDirty) return;
    setLayoutGeneration(layout.data.generation);
    viewport.current = layout.data.viewport;
    setNodes((current) =>
      current.map((node) => ({
        ...node,
        position:
          layout.data.positions.find((position) => position.id === node.id) ||
          node.position,
      })),
    );
  }, [layout.data, layoutDirty, setNodes]);
  useEffect(() => {
    setNodes((current) =>
      current.map((node) => ({
        ...node,
        data: {
          ...node.data,
          selected: node.id === section,
          summary:
            node.id === "model"
              ? value.model || "Pilih model"
              : node.id === "identity"
                ? value.role
                : node.id === "instructions"
                  ? `${value.system_prompt.length} karakter`
                  : node.id === "output"
                    ? `${value.output_contract.format} · ${value.output_contract.strict ? "strict" : "flexible"}`
                    : node.id === "constraints"
                      ? `${value.constraints.operational_rules.length} aturan · ${value.constraints.require_evidence_citation ? "evidence wajib" : "evidence opsional"}`
                      : node.id === "tools"
                        ? "Tool grants dinonaktifkan"
                        : node.id === "budget"
                          ? `${value.budget_policy.max_tokens_per_run} token · ${value.budget_policy.timeout_seconds}s`
                          : value.evaluation_reference.suite_id,
        },
      })),
    );
  }, [section, value, setNodes]);
  useEffect(() => {
    const unload = (event: BeforeUnloadEvent) => {
      if (dirty && editable) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    const scopeChange = (event: Event) => {
      if (dirty && editable) {
        event.preventDefault();
        setError("Simpan atau buang perubahan sebelum mengganti proyek.");
      }
    };
    window.addEventListener("beforeunload", unload);
    window.addEventListener("aryn:scope-change", scopeChange);
    return () => {
      window.removeEventListener("beforeunload", unload);
      window.removeEventListener("aryn:scope-change", scopeChange);
    };
  }, [dirty, editable]);
  const update = (next: AgentDraft) => {
    setHistory((current) => [...current.slice(-49), value]);
    setValue(next);
    setError("");
  };
  const save = async () => {
    const errors = validateDraft(value);
    if (Object.keys(jsonDrafts).length)
      errors.push(
        `Perbaiki JSON sebelum menyimpan: ${Object.keys(jsonDrafts).join(", ")}.`,
      );
    if (
      data.versions.some(
        (version) => version.version_number === value.version_number,
      )
    )
      errors.push("Gunakan nomor versi baru.");
    if (errors.length) {
      setError(errors.join(" "));
      return false;
    }
    try {
      const result = (await act(
        path + "/working-copy",
        {
          expected_generation: generation,
          definition: value,
          source_version_id: source?.id || null,
        },
        "Working copy tersimpan.",
      )) as unknown as WorkingCopy;
      setGeneration(result.generation);
      setSaved(serializeDefinition(result.definition));
      setHistory([]);
      setError("");
      return true;
    } catch (failure) {
      setRecovery({ definition: value, jsonDrafts });
      setError((failure as Error).message);
      return false;
    }
  };
  const reload = async () => {
    setRecovery({ definition: value, jsonDrafts });
    const response = await working.refetch();
    if (response.data) {
      setGeneration(response.data.generation);
      if (response.data.definition) {
        setValue(response.data.definition);
        setSaved(serializeDefinition(response.data.definition));
      } else {
        setValue(draftDefinition(blueprint, source));
        setSaved("");
      }
      setHistory([]);
      setJsonDrafts({});
    }
  };
  if (working.error || layout.error)
    return (
      <Notice tone="error">{(working.error || layout.error)?.message}</Notice>
    );
  if (working.isPending || layout.isPending) return <Busy />;
  return (
    <>
      <PageHeading
        eyebrow="AGENT FACTORY"
        title={`${blueprint.name} · AgentBuilder`}
        description="Delapan bagian membentuk satu definisi agent. Hubungan canvas tidak menjalankan workflow."
      >
        <Link to={`/factory/${blueprint.id}`}>Agent Detail</Link>
      </PageHeading>
      <div className="editor-toolbar">
        <span role="status">
          {dirty
            ? "Perubahan belum disimpan"
            : `Tersimpan · generation ${generation}`}
        </span>
        <Button variant="secondary" onClick={() => setFormView(!formView)}>
          {formView ? "Canvas" : "Form lengkap"}
        </Button>
        <Button variant="secondary" onClick={() => setInspector(!inspector)}>
          Inspector
        </Button>
        <Button
          variant="secondary"
          disabled={
            !writable || (!history.length && !Object.keys(jsonDrafts).length)
          }
          onClick={() => {
            if (Object.keys(jsonDrafts).length) {
              setJsonDrafts({});
              return;
            }
            setValue(history.at(-1)!);
            setHistory(history.slice(0, -1));
          }}
        >
          Undo
        </Button>
        <Button disabled={!writable || !dirty} onClick={() => void save()}>
          Simpan working copy
        </Button>
        <Button
          disabled={
            !writable || dirty || !generation || !working.data?.definition
          }
          onClick={async () => {
            try {
              const candidate = await act(
                path + "/working-copy/versions",
                { expected_generation: generation },
                "Candidate versi dibuat; lanjutkan Bench.",
              );
              navigate(`/factory/${blueprint.id}/versions/${candidate.id}`);
            } catch (failure) {
              setError((failure as Error).message);
            }
          }}
        >
          Buat candidate versi
        </Button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {!writable && (
        <Notice>
          Definisi hanya dapat dibaca untuk peran ini. Versi published tetap
          immutable.
        </Notice>
      )}
      <div className="editor-toolbar">
        <Button
          variant="ghost"
          disabled={pending}
          onClick={() => void reload()}
        >
          Muat ulang working copy
        </Button>
        {recovery && (
          <Button
            variant="secondary"
            disabled={!writable}
            onClick={() => {
              setValue(recovery.definition);
              setJsonDrafts(recovery.jsonDrafts);
              setRecovery(null);
            }}
          >
            Pulihkan input lokal
          </Button>
        )}
        <Button
          variant="ghost"
          disabled={!writable || !generation}
          onClick={async () => {
            try {
              const result = (await act(
                path + "/working-copy/discard",
                { expected_generation: generation },
                "Working copy dibuang.",
              )) as unknown as WorkingCopy;
              setGeneration(result.generation);
              setValue(draftDefinition(blueprint, source));
              setSaved("");
              setHistory([]);
              setJsonDrafts({});
            } catch (failure) {
              setError((failure as Error).message);
            }
          }}
        >
          Buang working copy
        </Button>
      </div>
      {formView ? (
        <div className="editor-full-form">
          {sections.map(([id, label]) => (
            <fieldset key={id} className="editor-section">
              <legend>{label}</legend>
              <SectionFields
                section={id}
                value={value}
                update={update}
                disabled={!writable}
                models={workspace.models}
                jsonDrafts={jsonDrafts}
                setJsonDraft={setJsonDraft}
              />
            </fieldset>
          ))}
        </div>
      ) : (
        <>
          <div className="editor-section-tabs" aria-label="Bagian definisi">
            {sections.map(([id, label]) => (
              <button
                key={id}
                aria-pressed={section === id}
                onClick={() => {
                  setSection(id);
                  setInspector(true);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className={`agent-editor ${inspector ? "with-inspector" : ""}`}>
            <div
              className="definition-canvas"
              aria-label="Canvas definisi agent"
            >
              <ReactFlow
                colorMode={theme === "light" ? "light" : "dark"}
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onNodeClick={(_, node) => {
                  setSection(node.id as Section);
                  setInspector(true);
                }}
                nodesDraggable={writable}
                nodesConnectable={false}
                edgesReconnectable={false}
                onNodeDragStop={() => setLayoutDirty(true)}
                onMoveEnd={(_, position) => {
                  viewport.current = position;
                  setLayoutDirty(true);
                }}
                defaultViewport={layout.data?.viewport}
                fitView={layout.data?.generation === 0}
                minZoom={0.1}
                maxZoom={4}
              >
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
            {inspector && (
              <aside
                className="editor-inspector"
                aria-label="Inspector definisi"
              >
                <div className="editor-toolbar">
                  <h2>{sections.find(([id]) => id === section)?.[1]}</h2>
                  <Button variant="ghost" onClick={() => setInspector(false)}>
                    Tutup inspector
                  </Button>
                </div>
                <SectionFields
                  section={section}
                  value={value}
                  update={update}
                  disabled={!writable}
                  models={workspace.models}
                  jsonDrafts={jsonDrafts}
                  setJsonDraft={setJsonDraft}
                />
              </aside>
            )}
          </div>
          <div className="editor-toolbar">
            <Button
              variant="secondary"
              disabled={!writable || !layoutDirty}
              onClick={async () => {
                try {
                  const result = (await act(
                    path + "/editor-layout",
                    {
                      expected_generation: layoutGeneration,
                      positions: nodes.map((node) => ({
                        id: node.id,
                        ...node.position,
                      })),
                      viewport: viewport.current,
                    },
                    "Layout tersimpan terpisah dari hash versi.",
                  )) as unknown as EditorLayout;
                  setLayoutGeneration(result.generation);
                  setLayoutDirty(false);
                } catch (failure) {
                  setError((failure as Error).message);
                }
              }}
            >
              Simpan layout
            </Button>
            <small>Layout pribadi · tidak membuat AgentVersion.</small>
          </div>
        </>
      )}
      <Modal
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open) blocker.reset?.();
        }}
        title="Perubahan belum disimpan"
        description="Pilih tindakan sebelum meninggalkan editor."
      >
        <div className="editor-toolbar">
          <Button
            onClick={async () => {
              if (await save()) blocker.proceed?.();
            }}
          >
            Simpan dan lanjutkan
          </Button>
          <Button variant="secondary" onClick={() => blocker.proceed?.()}>
            Tinggalkan input lokal
          </Button>
          <Button variant="ghost" onClick={() => blocker.reset?.()}>
            Tetap di editor
          </Button>
        </div>
      </Modal>
    </>
  );
}
