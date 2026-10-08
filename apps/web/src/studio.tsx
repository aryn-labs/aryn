import { Fragment, Suspense, lazy, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Beaker,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderKanban,
  Fingerprint,
  LayoutDashboard,
  Menu,
  Moon,
  PanelLeftClose,
  Radio,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sun,
  Terminal,
  Workflow,
  X,
} from "lucide-react";
import { api, apiStream, ApiError, logout } from "./lib/api";
import type { Snapshot, Workspace } from "./lib/types";
import type { WorkspaceSummary } from "./lib/workspace-types";
import { workspaceKey, routeIdentifier } from "./lib/workspace-types";
import { Button } from "./components/ui/button";
import { Modal } from "./components/ui/dialog";
import { BlueprintForm } from "./components/blueprint-form";
import { Busy, Empty, Notice } from "./components/shared";
import { Overview } from "./features/overview";
import { Projects } from "./features/projects";
import "./workspace.css";
import { AmbientBackground } from "./components/ambient-background";
import arynMark from "./assets/aryn-mark.png";
import arynMarkDark from "./assets/aryn-mark-dark.png";
const Factory = lazy(() =>
  import("./features/factory").then((module) => ({ default: module.Factory })),
);
const AgentDetail = lazy(() =>
  import("./features/factory").then((module) => ({
    default: module.AgentDetail,
  })),
);
const BenchPage = lazy(() =>
  import("./features/bench").then((module) => ({ default: module.BenchPage })),
);
const Approvals = lazy(() =>
  import("./features/approvals").then((module) => ({
    default: module.Approvals,
  })),
);
const Runs = lazy(() =>
  import("./features/runs").then((module) => ({ default: module.Runs })),
);
const Governance = lazy(() =>
  import("./features/governance").then((module) => ({
    default: module.Governance,
  })),
);
const SettingsPage = lazy(() =>
  import("./features/settings").then((module) => ({
    default: module.SettingsPage,
  })),
);
const Unavailable = lazy(() =>
  import("./features/settings").then((module) => ({
    default: module.Unavailable,
  })),
);
const navigation = [
  { path: "/", label: "Ringkasan", icon: LayoutDashboard, group: "WORKSPACE" },
  {
    path: "/projects",
    label: "Projects & Divisions",
    icon: FolderKanban,
    group: "WORKSPACE",
  },
  { path: "/factory", label: "Agent Factory", icon: Bot, group: "BUILD" },
  {
    path: "/workflows",
    label: "Workflow Builder",
    icon: Workflow,
    group: "BUILD",
    future: true,
  },
  {
    path: "/capabilities",
    label: "Capabilities",
    icon: ShieldCheck,
    group: "BUILD",
    future: true,
  },
  {
    path: "/operations",
    label: "Agent Operations",
    icon: Bot,
    group: "OPERATE",
    future: true,
  },
  {
    path: "/automations",
    label: "Automations",
    icon: Workflow,
    group: "OPERATE",
    future: true,
  },
  { path: "/runs", label: "Eksekusi", icon: Terminal, group: "OPERATE" },
  {
    path: "/outputs",
    label: "Outputs",
    icon: FileText,
    group: "OPERATE",
    future: true,
  },
  {
    path: "/brief",
    label: "Brief",
    icon: FileText,
    group: "INTELLIGENCE & RELIABILITY",
    future: true,
  },
  {
    path: "/bench",
    label: "Bench",
    icon: Beaker,
    group: "INTELLIGENCE & RELIABILITY",
  },
  {
    path: "/relay",
    label: "Relay",
    icon: Radio,
    group: "INTELLIGENCE & RELIABILITY",
    future: true,
  },
  {
    path: "/approvals",
    label: "Persetujuan",
    icon: ShieldCheck,
    group: "CONTROL",
  },
  {
    path: "/governance",
    label: "Tata Kelola",
    icon: Fingerprint,
    group: "CONTROL",
  },
  { path: "/settings", label: "Pengaturan", icon: Settings, group: "CONTROL" },
];

function useTheme() {
  const [theme, setTheme] = useState(() =>
    localStorage.getItem("aryn-theme") === "light" ? "light" : "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("aryn-theme", theme);
  }, [theme]);
  return { theme, setTheme };
}

export function App() {
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("aryn-sidebar") === "collapsed",
  );
  const [mobile, setMobile] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const [selectedProject, setProject] = useState(
    () => localStorage.getItem("aryn-project") || "",
  );
  const project =
    (location.pathname.startsWith("/projects/")
      ? routeIdentifier(location.pathname.split("/")[2])
      : "") || selectedProject;
  const [newBlueprint, setNewBlueprint] = useState(false);
  const [toast, setToast] = useState("");
  const [streamPending, setStreamPending] = useState(false);
  const workspace = useQuery({
    queryKey: ["workspace-context"],
    queryFn: ({ signal }) =>
      api<Workspace>("/workspace/context", undefined, signal),
    refetchInterval: 20000,
    retry: false,
  });
  const organization = workspace.data?.organization.id || "";
  const availability = useQuery({
    queryKey: ["workspace-availability", organization],
    queryFn: ({ signal }) =>
      api<
        Pick<Workspace, "models" | "runtime" | "gateway"> & {
          organization_id: string;
        }
      >("/workspace/status", undefined, signal),
    enabled: !!organization && !workspace.error,
    refetchInterval: 20000,
    retry: false,
  });
  const requiresSnapshot = [
    "/factory",
    "/runs",
    "/bench",
    "/approvals",
    "/governance",
    "/settings",
  ].some(
    (route) =>
      location.pathname === route || location.pathname.startsWith(`${route}/`),
  );
  const summary = useQuery({
    queryKey: workspaceKey(organization, project, "summary"),
    queryFn: ({ signal }) =>
      api<WorkspaceSummary>(`/projects/${project}/summary`, undefined, signal),
    enabled: !!organization && !!project && !workspace.error,
    refetchInterval: 10000,
    retry: false,
  });
  const snapshot = useQuery({
    queryKey: workspaceKey(organization, project, "snapshot"),
    queryFn: ({ signal }) =>
      api<Snapshot>(`/projects/${project}/snapshot`, undefined, signal),
    enabled:
      !!organization && !!project && !workspace.error && requiresSnapshot,
    refetchInterval: 10000,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: ({
      path,
      body,
      scope,
    }: {
      path: string;
      body: unknown;
      scope: string;
      org: string;
    }) => api<Record<string, unknown>>(`/projects/${scope}${path}`, body),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["studio", variables.org, variables.scope],
      });
    },
  });
  const act = async (path: string, body: unknown, success: string) => {
    const result = await mutation.mutateAsync({
      path,
      body,
      scope: project,
      org: organization,
    });
    setToast(success);
    return result;
  };
  const actStream = async (
    path: string,
    body: unknown,
    success: string,
    onEvent?: (event: import("./lib/types").StreamEvent) => void,
  ): Promise<Record<string, unknown>> => {
    setStreamPending(true);
    try {
      const result = await apiStream(
        `/projects/${project}${path}`,
        body,
        onEvent,
      );
      if (success && (!path.endsWith("/runs") || result.status === "completed"))
        setToast(success);
      await queryClient.invalidateQueries({
        queryKey: ["studio", organization, project],
      });
      return result;
    } catch (err: any) {
      throw err;
    } finally {
      setStreamPending(false);
    }
  };
  useEffect(() => {
    setMobile(false);
    mutation.reset();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!mobile) return;
    sidebarRef.current
      ?.querySelector<HTMLAnchorElement>('a[aria-current="page"], a')
      ?.focus();
    return () => menuRef.current?.focus();
  }, [mobile]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 6000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    if (workspace.data && !project) {
      setProject(workspace.data.projects[0]?.id || "");
    }
  }, [workspace.data, project]);
  const w = workspace.data
    ? {
        ...workspace.data,
        ...(availability.data &&
        !availability.error &&
        availability.data.organization_id === organization
          ? {
              models: availability.data.models,
              runtime: availability.data.runtime,
              gateway: availability.data.gateway,
            }
          : {}),
      }
    : undefined;
  const data = snapshot.data;
  const readError =
    workspace.error ||
    summary.error ||
    (requiresSnapshot ? snapshot.error : null);
  const authError =
    availability.error instanceof ApiError &&
    [401, 403].includes(availability.error.status)
      ? availability.error
      : null;
  const accessDenied =
    (readError instanceof ApiError && readError.status === 403) ||
    authError?.status === 403;
  const denied = [readError, authError].some(
    (error) => error instanceof ApiError && [401, 403].includes(error.status),
  );
  const displayError =
    !!authError ||
    (!!readError &&
      (denied || !w || !summary.data || (requiresSnapshot && !data)));
  const apiConnected =
    !!w &&
    !(
      workspace.error instanceof ApiError &&
      (workspace.error.status === 0 || workspace.error.status >= 500)
    );
  const currentNav = navigation.find((n) =>
    n.path === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(n.path),
  );
  const refresh = () => {
    void queryClient.invalidateQueries();
  };
  const switchProject = (next: string, route = "/") => {
    if (mutation.isPending || streamPending) return;
    void queryClient.cancelQueries({ queryKey: ["studio"] });
    queryClient.removeQueries({ queryKey: ["studio"] });
    setNewBlueprint(false);
    setToast("");
    mutation.reset();
    setProject(next);
    localStorage.setItem("aryn-project", next);
    navigate(route);
  };
  const selectedBlueprint = data?.blueprints.find(
    (b) => location.pathname === `/factory/${b.id}`,
  );
  const shared = {
    data: data!,
    workspace: w!,
    project,
    pending: mutation.isPending || streamPending,
    error: mutation.error?.message,
    resetError: () => mutation.reset(),
    act,
    actStream,
    openBlueprint: () => {
      mutation.reset();
      setNewBlueprint(true);
    },
  };
  return (
    <div
      className={`app ${collapsed ? "sidebar-collapsed" : ""} ${mobile ? "mobile-open" : ""}`}
    >
      <AmbientBackground />
      <a className="skip-link" href="#main">
        Lewati ke konten
      </a>
      {mobile && (
        <button
          className="mobile-backdrop"
          aria-label="Tutup navigasi"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        id="studio-sidebar"
        ref={sidebarRef}
        className="sidebar"
        role={mobile ? "dialog" : undefined}
        aria-modal={mobile || undefined}
        aria-label="Navigasi Studio"
        onKeyDown={(event) => {
          if (!mobile) return;
          if (event.key === "Escape") {
            event.preventDefault();
            setMobile(false);
          } else if (event.key === "Tab") {
            const controls = Array.from(
              sidebarRef.current?.querySelectorAll<HTMLElement>(
                "a[href], button:not(:disabled), select:not(:disabled)",
              ) || [],
            ).filter((el) => el.getClientRects().length > 0);
            const target = event.shiftKey ? controls.at(-1) : controls[0];
            const boundary = event.shiftKey ? controls[0] : controls.at(-1);
            if (document.activeElement === boundary) {
              event.preventDefault();
              target?.focus();
            }
          }
        }}
      >
        <div className="brand">
          <img
            className="brand-mark"
            src={theme.theme === "dark" ? arynMarkDark : arynMark}
            alt="Logo ARYN"
            width={38}
            height={28}
            draggable={false}
          />
          <span>
            ARYN <small>Studio</small>
          </span>
        </div>
        <div
          className="workspace-card"
          title={`Proyek aktif: ${w?.projects.find((p) => p.id === project)?.name || project || "Memuat proyek"}`}
        >
          <div className="workspace-card-icon">
            <Radio size={15} />
          </div>
          <div className="workspace-card-info">
            <div className="workspace-card-meta">
              <span className="workspace-pulse" />
              <span className="workspace-card-tag">SESI AKTIF</span>
            </div>
            <strong className="workspace-card-title">
              {w?.projects.find((p) => p.id === project)?.name ||
                project ||
                "Memuat proyek"}
            </strong>
          </div>
          {w && w.projects.length > 1 && (
            <>
              <select
                aria-label="Pilih proyek"
                value={project}
                className="workspace-card-select"
                disabled={mutation.isPending || streamPending}
                onChange={(e) => {
                  switchProject(e.target.value);
                }}
              >
                {w.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="workspace-chevron" />
            </>
          )}
        </div>
        <nav aria-label="Navigasi utama">
          {[...new Set(navigation.map((item) => item.group))].map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-caption">{group}</div>
              {navigation
                .filter((item) => item.group === group)
                .map((n) => (
                  <NavLink
                    key={n.path}
                    to={n.path}
                    end={n.path === "/"}
                    title={n.label}
                    className={({ isActive }) =>
                      `nav-item ${isActive ? "active" : ""}`
                    }
                  >
                    <n.icon size={18} />
                    <span>{n.label}</span>
                    {n.future && (
                      <span className="future-dot" title="Belum tersedia" />
                    )}
                    {n.path === "/approvals" &&
                      summary.data &&
                      !denied &&
                      summary.data.metrics.review_candidates.value! > 0 && (
                        <small className="nav-count">
                          {summary.data.metrics.review_candidates.value}
                        </small>
                      )}
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-mode">
            <span className="connection-dot" />
            <span>
              {w?.mode === "isolated-test"
                ? "Pengujian terisolasi"
                : w?.mode === "hosted"
                  ? "Lingkungan hosted"
                  : "Lingkungan lokal"}
              <small>
                {w?.mode === "hosted"
                  ? "Sesi terautentikasi"
                  : "Sesi development · loopback"}
              </small>
            </span>
          </div>
          <div className="user-area">
            <div className="user-avatar">PL</div>
            <div>
              <strong>{w?.user.name || "Sesi Studio"}</strong>
              <small>
                {w?.user.role === "admin"
                  ? w?.mode === "hosted"
                    ? "Admin organisasi"
                    : "Admin lokal"
                  : "Akses terbatas"}
              </small>
            </div>
            <Button
              size="icon"
              variant="ghost"
              aria-label={collapsed ? "Perluas sidebar" : "Ciutkan sidebar"}
              onClick={() => {
                setCollapsed(!collapsed);
                localStorage.setItem(
                  "aryn-sidebar",
                  !collapsed ? "collapsed" : "expanded",
                );
              }}
            >
              <PanelLeftClose size={16} />
            </Button>
          </div>
        </div>
      </aside>
      <div className="app-body" inert={mobile}>
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              ref={menuRef}
              size="icon"
              variant="ghost"
              className="mobile-menu"
              aria-label="Buka navigasi"
              aria-controls="studio-sidebar"
              aria-expanded={mobile}
              onClick={() => setMobile(true)}
            >
              <Menu size={19} />
            </Button>
            <span className="breadcrumb-workspace">
              {w?.projects.find((item) => item.id === project)?.name ||
                "Ruang kerja"}
            </span>
            <ChevronRight size={14} />
            <span>{currentNav?.label || "Halaman"}</span>
            {selectedBlueprint && (
              <>
                <ChevronRight size={14} />
                <strong>{selectedBlueprint.name}</strong>
              </>
            )}
          </div>
          <div className="topbar-actions">
            {w?.mode === "hosted" && (
              <Button
                variant="ghost"
                onClick={async () => {
                  await logout();
                  queryClient.clear();
                  window.location.assign("/");
                }}
              >
                Keluar
              </Button>
            )}
            <span
              className={`connection ${apiConnected ? "online" : "offline"}`}
              title={workspace.error?.message || "ARYN API"}
            >
              <span className="connection-dot" />
              API {apiConnected ? "terhubung" : "terputus"}
            </span>
            <span
              className={`connection ${apiConnected && w?.runtime.ready ? "online" : apiConnected && w?.runtime.connected ? "degraded" : "offline"}`}
              title={w?.runtime.message || "Memeriksa ARYN Runtime"}
            >
              <span className="connection-dot" />
              ARYN Runtime{" "}
              {apiConnected && w?.runtime.ready ? "siap" : "belum siap"}
            </span>
            <div className="topbar-divider" />
            <span
              className={`connection ${apiConnected && w?.gateway.connected && w?.gateway.discovery_valid && w?.gateway.runtime_binding_verified ? "online" : apiConnected && w?.gateway.connected ? "degraded" : "offline"}`}
            >
              <span className="connection-dot" />
              Model Gateway{" "}
              {apiConnected && w?.gateway.connected ? "terhubung" : "terputus"}
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Perbarui koneksi dan data"
              onClick={refresh}
            >
              <RefreshCw
                size={16}
                className={
                  workspace.isFetching ||
                  snapshot.isFetching ||
                  summary.isFetching
                    ? "spin"
                    : ""
                }
              />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={
                theme.theme === "dark"
                  ? "Gunakan tema terang"
                  : "Gunakan tema gelap"
              }
              onClick={() =>
                theme.setTheme(theme.theme === "dark" ? "light" : "dark")
              }
            >
              {theme.theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
          </div>
        </header>
        <main id="main" className="main-content" tabIndex={-1}>
          <Suspense fallback={<Busy />}>
            {displayError ? (
              <div className="connection-error">
                <Terminal size={30} />
                <h1>
                  {accessDenied
                    ? "Akses proyek dibatasi"
                    : "Ruang kerja belum terhubung"}
                </h1>
                <Notice tone="error">
                  {authError?.message || readError?.message}
                </Notice>
                <p>
                  {accessDenied
                    ? "Core belum mengizinkan sesi ini membaca proyek. Periksa keanggotaan dan peran di server."
                    : "Data dan aksi Studio membutuhkan API yang aktif dan sesi yang valid."}
                </p>
                {[authError, readError].find(
                  (error) => error instanceof ApiError && error.loginUrl,
                ) instanceof ApiError && (
                  <a href="/auth/login">Masuk melalui penyedia identitas</a>
                )}
                <Button onClick={refresh}>
                  <RefreshCw size={15} />
                  Coba sambungkan kembali
                </Button>
              </div>
            ) : workspace.isPending ||
              (!!project && !summary.data && !summary.error) ||
              (requiresSnapshot && !data && !snapshot.error) ? (
              <Busy />
            ) : w && !project ? (
              <Empty
                title="Belum ada proyek yang diizinkan"
                description="Core belum menyediakan proyek untuk sesi ini."
              />
            ) : w && summary.data ? (
              <Fragment
                key={`${organization}:${project}:${location.pathname.startsWith("/projects") ? location.pathname : "workspace"}`}
              >
                {readError && (
                  <div className="workspace-stale">
                    <Notice tone="warning">
                      Data terakhir · belum diperbarui: {readError.message}
                    </Notice>
                  </div>
                )}
                {availability.error && !authError && (
                  <Notice tone="warning">
                    Status runtime/model belum dapat diperbarui.{" "}
                    {availability.error.message}
                  </Notice>
                )}
                {mutation.error && !newBlueprint && (
                  <div className="global-error">
                    <Notice tone="error">{mutation.error.message}</Notice>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Tutup pesan kesalahan"
                      onClick={() => mutation.reset()}
                    >
                      <X size={16} />
                    </Button>
                  </div>
                )}
                {location.pathname === "/" ? (
                  <Overview
                    summary={summary.data}
                    workspace={w}
                    project={project}
                    openBlueprint={shared.openBlueprint}
                  />
                ) : location.pathname === "/projects" ||
                  location.pathname.startsWith("/projects/") ? (
                  <Projects
                    organization={organization}
                    project={project}
                    switchProject={switchProject}
                  />
                ) : location.pathname === "/factory" ? (
                  <Factory {...shared} />
                ) : selectedBlueprint ? (
                  <AgentDetail {...shared} blueprint={selectedBlueprint} />
                ) : location.pathname === "/runs" ||
                  location.pathname.startsWith("/runs/") ? (
                  <Runs {...shared} />
                ) : location.pathname === "/bench" ? (
                  <BenchPage {...shared} />
                ) : location.pathname === "/approvals" ? (
                  <Approvals {...shared} />
                ) : location.pathname === "/governance" ? (
                  <Governance {...shared} />
                ) : location.pathname === "/settings" ? (
                  <SettingsPage
                    workspace={w}
                    data={data!}
                    theme={theme.theme}
                    setTheme={theme.setTheme}
                    refresh={refresh}
                  />
                ) : currentNav &&
                  (currentNav.future ||
                    location.pathname.startsWith(`${currentNav.path}/`)) ? (
                  <Unavailable module={currentNav.label} />
                ) : (
                  <Empty
                    title="Halaman tidak ditemukan"
                    description="Halaman atau blueprint ini tidak tersedia di proyek yang dipilih."
                    action="Kembali ke Ringkasan"
                    onAction={() => navigate("/")}
                  />
                )}
              </Fragment>
            ) : null}
          </Suspense>
        </main>
        <footer className="app-footer">
          <span>
            ARYN Studio <span className="footer-dot">·</span>{" "}
            {w?.mode === "hosted" ? "hosted" : "development"}
          </span>
          <span>
            Core mengatur setiap aksi <ShieldCheck size={12} />
          </span>
        </footer>
      </div>
      <Modal
        open={newBlueprint}
        busy={mutation.isPending}
        onOpenChange={(v) => {
          if (!mutation.isPending) setNewBlueprint(v);
        }}
        title="Buat blueprint agent"
        description="Definisikan tujuan agent. Konfigurasi dan evaluasi dilakukan pada versi terpisah."
      >
        <BlueprintForm
          pending={mutation.isPending}
          error={mutation.error?.message}
          onSubmit={async (form) => {
            try {
              const bp = await act(
                "/blueprints",
                form,
                "Blueprint berhasil dibuat.",
              );
              setNewBlueprint(false);
              navigate(`/factory/${bp.id}`);
            } catch {
              /* visible mutation error */
            }
          }}
        />
      </Modal>
      {toast && (
        <div className="toast" role="status">
          <div>
            <Check size={17} />
            {toast}
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Tutup notifikasi"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </Button>
        </div>
      )}
    </div>
  );
}
