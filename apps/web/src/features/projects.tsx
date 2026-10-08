import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type {
  ResourceItem,
  ResourcePage,
  WorkspaceSummary,
} from "../lib/workspace-types";
import { workspaceKey, routeIdentifier } from "../lib/workspace-types";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { Busy, Empty, Notice, PageHeading } from "../components/shared";
import { Panel } from "../components/workspace";
import { date } from "../lib/utils";

export function Projects({
  organization,
  project,
  switchProject,
}: {
  organization: string;
  project: string;
  switchProject: (id: string, route?: string) => void;
}) {
  const location = useLocation();
  const detail = location.pathname.split("/")[2];
  const scope = detail ? routeIdentifier(detail) : project;
  const resource = detail ? "divisions" : "projects";
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [editing, setEditing] = useState<ResourceItem | "new" | null>(null);
  const client = useQueryClient();
  const cursor = cursors.at(-1);
  const list = useQuery({
    queryKey: workspaceKey(organization, scope, resource, q, sort, cursor),
    queryFn: ({ signal }) =>
      api<ResourcePage>(
        `/projects/${scope}/resources/${resource}?limit=10&q=${encodeURIComponent(q)}&sort=${sort}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        undefined,
        signal,
      ),
    retry: false,
  });
  const projectDetail = useQuery({
    queryKey: workspaceKey(organization, scope, "project-detail"),
    queryFn: ({ signal }) =>
      api<ResourceItem>(
        `/projects/${scope}/resources/projects/${scope}`,
        undefined,
        signal,
      ),
    enabled: !!detail,
    retry: false,
  });
  const permissions = useQuery({
    queryKey: workspaceKey(organization, scope, "summary"),
    queryFn: ({ signal }) =>
      api<WorkspaceSummary>(`/projects/${scope}/summary`, undefined, signal),
    enabled: !!detail,
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: {
      name: string;
      slug: string;
      description: string;
      expected_generation?: number;
    }) =>
      api(
        `/projects/${scope}/divisions${editing && editing !== "new" ? `/${editing.id}` : ""}`,
        body,
      ),
    onSuccess: async () => {
      setEditing(null);
      setCursors([null]);
      await client.invalidateQueries({
        queryKey: ["studio", organization, scope],
      });
    },
  });
  const error = projectDetail.error || list.error || permissions.error;
  const blocked =
    error instanceof ApiError && [401, 403].includes(error.status);
  const canManage =
    permissions.data?.permissions["division:manage"] && !permissions.error;
  const resetPage = () => setCursors([null]);
  return (
    <div className="projects-page">
      <PageHeading
        title={
          detail
            ? projectDetail.data?.name || "Detail proyek"
            : "Projects & Divisions"
        }
        description={
          detail
            ? "Division adalah struktur proyek; izin tetap dikelola Core."
            : "Proyek yang dapat dibaca melalui keanggotaan Core aktif."
        }
      >
        {detail && canManage && (
          <Button
            onClick={() => {
              save.reset();
              setEditing("new");
            }}
          >
            <Plus size={16} />
            Buat division
          </Button>
        )}
      </PageHeading>
      {error && (
        <Notice tone="error">
          {error.message}{" "}
          {list.data && !blocked
            ? "Data terakhir tersimpan; status kini stale."
            : ""}
        </Notice>
      )}
      {blocked ? (
        <Button
          onClick={() => {
            void list.refetch();
            void projectDetail.refetch();
            void permissions.refetch();
          }}
        >
          Periksa akses kembali
        </Button>
      ) : (
        <Panel
          title={detail ? "Divisions" : "Daftar proyek"}
          subtitle={
            list.data
              ? `Core · ${organization}/${scope} · Diperbarui ${date(list.data.refreshed_at)} · ${Intl.DateTimeFormat().resolvedOptions().timeZone}`
              : "Membaca sumber Core"
          }
        >
          <div className="workspace-toolbar">
            <label>
              Cari {detail ? "division" : "proyek"}
              <input
                value={q}
                maxLength={100}
                onChange={(event) => {
                  setQ(event.target.value);
                  resetPage();
                }}
              />
            </label>
            <label>
              Urutan
              <select
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value);
                  resetPage();
                }}
              >
                <option value="newest">Terbaru</option>
                <option value="oldest">Terlama</option>
              </select>
            </label>
            <Button
              variant="ghost"
              onClick={() => {
                void list.refetch();
              }}
            >
              Perbarui daftar
            </Button>
          </div>
          {list.isPending ? (
            <Busy />
          ) : !list.data ? (
            <Empty
              title="Daftar belum tersedia"
              description="Periksa koneksi atau izin proyek, lalu coba kembali."
            />
          ) : !list.data.items.length ? (
            <Empty
              title={
                q
                  ? "Tidak ada hasil filter"
                  : detail
                    ? "Belum ada division"
                    : "Belum ada proyek"
              }
              description={
                q
                  ? "Ubah kata pencarian untuk melihat sumber yang diizinkan."
                  : "Tidak ada data contoh yang ditambahkan ke proyek."
              }
            />
          ) : (
            <div className="workspace-table-wrap">
              <table className="workspace-table">
                <caption>
                  {detail ? "Division tersimpan" : "Proyek yang diizinkan"}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Nama</th>
                    <th scope="col">Identifier</th>
                    <th scope="col">Dibuat</th>
                    <th scope="col">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        {item.name}
                        {item.description && <small>{item.description}</small>}
                      </th>
                      <td>
                        <code>{item.slug || item.id}</code>
                      </td>
                      <td>{date(item.created_at)}</td>
                      <td>
                        {detail ? (
                          canManage ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => {
                                save.reset();
                                setEditing(item);
                              }}
                            >
                              Edit {item.name}
                            </Button>
                          ) : (
                            "Baca saja"
                          )
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              switchProject(
                                item.id,
                                `/projects/${encodeURIComponent(item.id)}`,
                              )
                            }
                          >
                            Buka {item.name}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="workspace-pagination" aria-label="Pagination daftar">
            <Button
              variant="ghost"
              disabled={cursors.length < 2 || list.isFetching}
              onClick={() => setCursors(cursors.slice(0, -1))}
            >
              Sebelumnya
            </Button>
            <span role="status">
              Halaman {cursors.length}
              {list.isFetching ? " · Memuat" : ""}
            </span>
            <Button
              variant="ghost"
              disabled={!list.data?.next_cursor || list.isFetching}
              onClick={() => setCursors([...cursors, list.data!.next_cursor])}
            >
              Berikutnya
            </Button>
          </div>
        </Panel>
      )}
      <Modal
        open={!!editing}
        busy={save.isPending}
        onOpenChange={(open) => {
          if (!open && !save.isPending) setEditing(null);
        }}
        title={editing === "new" ? "Buat division" : "Edit division"}
        description="Simpan struktur proyek melalui izin efektif Core. Perubahan tidak mengubah role atau history assignment."
      >
        {editing && (
          <DivisionForm
            key={editing === "new" ? "new" : editing.id}
            item={editing === "new" ? undefined : editing}
            pending={save.isPending}
            error={save.error?.message}
            onSubmit={(body) => save.mutate(body)}
          />
        )}
      </Modal>
    </div>
  );
}

function DivisionForm({
  item,
  pending,
  error,
  onSubmit,
}: {
  item?: ResourceItem;
  pending: boolean;
  error?: string;
  onSubmit: (body: {
    name: string;
    slug: string;
    description: string;
    expected_generation?: number;
  }) => void;
}) {
  const [name, setName] = useState(item?.name || "");
  const [slug, setSlug] = useState(item?.slug || "");
  const [description, setDescription] = useState(item?.description || "");
  return (
    <form
      className="workspace-division-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          name,
          slug,
          description,
          ...(item ? { expected_generation: item.generation! } : {}),
        });
      }}
    >
      {error && (
        <Notice tone="error">
          {error} Jika data berubah, tutup form dan perbarui daftar sebelum
          menyimpan kembali.
        </Notice>
      )}
      <label>
        Nama division
        <input
          required
          minLength={2}
          maxLength={100}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        Slug division
        <input
          required
          minLength={2}
          maxLength={80}
          pattern="[a-z0-9]+(-[a-z0-9]+)*"
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
        />
      </label>
      <label>
        Deskripsi division
        <textarea
          maxLength={2000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <Button type="submit" disabled={pending}>
        {pending ? "Menyimpan" : "Simpan division"}
      </Button>
    </form>
  );
}
