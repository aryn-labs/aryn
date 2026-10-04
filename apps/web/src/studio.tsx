import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Beaker,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Fingerprint,
  Layers3,
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
import { api, ApiError } from "./lib/api";
import type { Snapshot, Workspace } from "./lib/types";
import { Button } from "./components/ui/button";
import { Modal } from "./components/ui/dialog";
import { BlueprintForm } from "./components/blueprint-form";
import { Busy, Empty, Notice } from "./components/shared";
import { Overview } from "./features/overview";
import { Factory, AgentDetail } from "./features/factory";
import { BenchPage } from "./features/bench";
import { Approvals } from "./features/approvals";
import { Runs } from "./features/runs";
import { Governance } from "./features/governance";
import { SettingsPage, Unavailable } from "./features/settings";
import arynMark from "./assets/aryn-mark.png";
import arynMarkDark from "./assets/aryn-mark-dark.png";
const navigation = [
  { path: "/", label: "Ringkasan", icon: LayoutDashboard },
  { path: "/factory", label: "Agent Factory", icon: Bot },
  { path: "/runs", label: "Eksekusi", icon: Workflow },
  { path: "/bench", label: "Bench", icon: Beaker },
  { path: "/approvals", label: "Persetujuan", icon: ShieldCheck },
  { path: "/brief", label: "Brief", icon: FileText, future: true },
  { path: "/relay", label: "Relay", icon: Radio, future: true },
  { path: "/governance", label: "Tata Kelola", icon: Fingerprint },
  { path: "/settings", label: "Pengaturan", icon: Settings },
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
  const [project, setProject] = useState(
    () => localStorage.getItem("aryn-project") || "proj_studio_research",
  );
  const [newBlueprint, setNewBlueprint] = useState(false);
  const [toast, setToast] = useState("");
  const workspace = useQuery({
    queryKey: ["workspace"],
    queryFn: () => api<Workspace>("/workspace"),
    refetchInterval: 20000,
  });
  const snapshot = useQuery({
    queryKey: ["snapshot", project],
    queryFn: () => api<Snapshot>(`/projects/${project}/snapshot`),
    enabled: !!workspace.data,
    refetchInterval: 10000,
  });
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) =>
      api<Record<string, unknown>>(`/projects/${project}${path}`, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["snapshot", project] });
    },
  });
  const act = async (path: string, body: unknown, success: string) => {
    const result = await mutation.mutateAsync({ path, body });
    setToast(success);
    return result;
  };
  useEffect(() => {
    setMobile(false);
    mutation.reset();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 6000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    if (
      workspace.data &&
      !workspace.data.projects.some((p) => p.id === project)
    ) {
      setProject(workspace.data.projects[0]?.id || "proj_studio_research");
    }
  }, [workspace.data, project]);
  const w = workspace.data;
  const data = snapshot.data;
  const readError = workspace.error || snapshot.error;
  const accessDenied =
    readError instanceof ApiError && readError.status === 403;
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
  const selectedBlueprint = data?.blueprints.find(
    (b) => location.pathname === `/factory/${b.id}`,
  );
  const shared = {
    data: data!,
    workspace: w!,
    project,
    pending: mutation.isPending,
    error: mutation.error?.message,
    resetError: () => mutation.reset(),
    act,
    openBlueprint: () => {
      mutation.reset();
      setNewBlueprint(true);
    },
  };
  return (
    <div
      className={`app ${collapsed ? "sidebar-collapsed" : ""} ${mobile ? "mobile-open" : ""}`}
    >
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
      <aside className="sidebar">
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
        <div className="workspace-switcher">
          <div className="workspace-avatar">
            <Layers3 size={17} />
          </div>
          <div className="workspace-label">
            <strong>{w?.organization.name || "ARYN Lokal"}</strong>
            <select
              aria-label="Pilih proyek"
              value={project}
              onChange={(e) => {
                setProject(e.target.value);
                localStorage.setItem("aryn-project", e.target.value);
                navigate("/");
              }}
            >
              {w?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              )) || <option>Memuat proyek…</option>}
            </select>
          </div>
          <ChevronDown size={14} className="workspace-chevron" />
        </div>
        <div className="nav-caption">RUANG KERJA</div>
        <nav aria-label="Navigasi utama">
          {navigation.map((n, i) => (
            <NavLink
              key={n.path}
              to={n.path}
              end={n.path === "/"}
              title={n.label}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""} ${i === 7 ? "nav-separated" : ""}`
              }
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.future && (
                <span className="future-dot" title="Belum tersedia" />
              )}
              {n.path === "/approvals" &&
                data &&
                data.versions.filter(
                  (v) =>
                    v.status === "draft" &&
                    data.evaluations.find((e) => e.version_id === v.id)?.passed,
                ).length > 0 && (
                  <small className="nav-count">
                    {
                      data.versions.filter(
                        (v) =>
                          v.status === "draft" &&
                          data.evaluations.find((e) => e.version_id === v.id)
                            ?.passed,
                      ).length
                    }
                  </small>
                )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-mode">
            <span className="connection-dot" />
            <span>
              {w?.mode === "isolated-test"
                ? "Pengujian terisolasi"
                : "Lingkungan lokal"}
              <small>Sesi development · loopback</small>
            </span>
          </div>
          <div className="user-area">
            <div className="user-avatar">PL</div>
            <div>
              <strong>{w?.user.name || "Sesi development"}</strong>
              <small>
                {w?.user.role === "admin" ? "Admin lokal" : "Akses terbatas"}
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
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              size="icon"
              variant="ghost"
              className="mobile-menu"
              aria-label="Buka navigasi"
              onClick={() => setMobile(true)}
            >
              <Menu size={19} />
            </Button>
            <span className="breadcrumb-workspace">Ruang kerja</span>
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
            <span
              className={`connection ${apiConnected ? "online" : "offline"}`}
              title={workspace.error?.message || "ARYN API lokal"}
            >
              <span className="connection-dot" />
              API {apiConnected ? "terhubung" : "terputus"}
            </span>
            <span
              className={`connection ${apiConnected && w?.runtime.ready ? "online" : "offline"}`}
              title={w?.runtime.message || "Memeriksa Hermes"}
            >
              <span className="connection-dot" />
              Hermes {apiConnected && w?.runtime.ready ? "siap" : "belum siap"}
            </span>
            <div className="topbar-divider" />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Perbarui koneksi dan data"
              onClick={refresh}
            >
              <RefreshCw
                size={16}
                className={
                  workspace.isFetching || snapshot.isFetching ? "spin" : ""
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
          {workspace.isPending ||
          (!snapshot.error && !data && snapshot.isFetching) ? (
            <Busy />
          ) : workspace.error || snapshot.error ? (
            <div className="connection-error">
              <Terminal size={30} />
              <h1>
                {accessDenied
                  ? "Akses proyek dibatasi"
                  : "Ruang kerja belum terhubung"}
              </h1>
              <Notice tone="error">
                {workspace.error?.message || snapshot.error?.message}
              </Notice>
              <p>
                {accessDenied
                  ? "Core belum mengizinkan sesi ini membaca proyek. Periksa keanggotaan dan peran development di server."
                  : "Data dan aksi Studio membutuhkan API lokal yang aktif."}
              </p>
              <Button onClick={refresh}>
                <RefreshCw size={15} />
                Coba sambungkan kembali
              </Button>
            </div>
          ) : data && w ? (
            <>
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
                <Overview {...shared} />
              ) : location.pathname === "/factory" ? (
                <Factory {...shared} />
              ) : selectedBlueprint ? (
                <AgentDetail {...shared} blueprint={selectedBlueprint} />
              ) : location.pathname === "/runs" ? (
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
                  data={data}
                  theme={theme.theme}
                  setTheme={theme.setTheme}
                  refresh={refresh}
                />
              ) : location.pathname === "/brief" ||
                location.pathname === "/relay" ? (
                <Unavailable
                  module={location.pathname === "/brief" ? "Brief" : "Relay"}
                />
              ) : (
                <Empty
                  title="Halaman tidak ditemukan"
                  description="Halaman atau blueprint ini tidak tersedia di proyek yang dipilih."
                  action="Kembali ke Ringkasan"
                  onAction={() => navigate("/")}
                />
              )}
            </>
          ) : null}
        </main>
        <footer className="app-footer">
          <span>
            ARYN Studio <span className="footer-dot">·</span> development
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
