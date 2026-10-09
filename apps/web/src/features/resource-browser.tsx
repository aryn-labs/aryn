import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import {
  workspaceKey,
  type ResourceItem,
  type ResourcePage,
} from "../lib/workspace-types";
import { Busy, Empty, Notice, Status } from "../components/shared";
import { Button } from "../components/ui/button";
import { date } from "../lib/utils";
import "./agent-editor.css";

export function ResourceBrowser({
  organization,
  project,
  resource,
  title,
  statuses = [],
  blueprint = "",
  link,
  extra,
  audit = false,
  initialStatus = "",
}: {
  organization: string;
  project: string;
  resource: string;
  title: string;
  statuses?: string[];
  blueprint?: string;
  link?: (item: ResourceItem) => string;
  extra?: (item: ResourceItem) => ReactNode;
  audit?: boolean;
  initialStatus?: string;
}) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState(initialStatus);
  const [sort, setSort] = useState("newest");
  const [actor, setActor] = useState("");
  const [target, setTarget] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState("");
  const cursor = cursors.at(-1);
  const list = useQuery({
    queryKey: workspaceKey(
      organization,
      project,
      resource,
      blueprint,
      q,
      status,
      sort,
      actor,
      target,
      cursor,
    ),
    queryFn: ({ signal }) =>
      api<ResourcePage>(
        `/projects/${project}/resources/${resource}?limit=10&q=${encodeURIComponent(q)}&status=${status}&sort=${sort}${blueprint ? `&blueprint_id=${encodeURIComponent(blueprint)}` : ""}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}${audit ? `&actor=${encodeURIComponent(actor)}&resource_id=${encodeURIComponent(target)}` : ""}`,
        undefined,
        signal,
      ),
    retry: false,
  });
  const detail = useQuery({
    queryKey: workspaceKey(organization, project, resource, "detail", selected),
    queryFn: ({ signal }) =>
      api<ResourceItem>(
        `/projects/${project}/resources/${resource}/${encodeURIComponent(selected)}`,
        undefined,
        signal,
      ),
    enabled: audit && !!selected,
    retry: false,
  });
  const reset = () => {
    setCursors([null]);
    setSelected("");
  };
  return (
    <section className="resource-browser" aria-label={title}>
      <div className="list-toolbar">
        <label>
          Cari {title}
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              reset();
            }}
            maxLength={100}
          />
        </label>
        {statuses.length > 0 && (
          <label>
            Status
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                reset();
              }}
            >
              <option value="">Semua status</option>
              {statuses.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          Urutan
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              reset();
            }}
          >
            <option value="newest">Terbaru</option>
            <option value="oldest">Terlama</option>
          </select>
        </label>
        {audit && (
          <>
            <label>
              Actor
              <input
                value={actor}
                onChange={(e) => {
                  setActor(e.target.value);
                  reset();
                }}
              />
            </label>
            <label>
              Resource
              <input
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  reset();
                }}
              />
            </label>
          </>
        )}
      </div>
      {list.error ? (
        <Notice tone="error">{list.error.message}</Notice>
      ) : list.isPending ? (
        <Busy />
      ) : list.data?.items.length ? (
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label={`Tabel ${title}`}
        >
          <table>
            <thead>
              <tr>
                <th>Sumber daya</th>
                <th>Status</th>
                <th>Verifikasi</th>
                <th>Waktu</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {link ? (
                      <Link to={link(item)}>{item.name}</Link>
                    ) : (
                      item.name
                    )}
                    <small className="mono">{item.id}</small>
                  </td>
                  <td>
                    <Status value={item.status || "recorded"} />
                  </td>
                  <td>
                    {item.verified === null
                      ? "Inventory tersimpan"
                      : item.verified
                        ? "Terverifikasi"
                        : "Belum terverifikasi"}
                    <small>{item.verification_reason}</small>
                  </td>
                  <td>{date(item.created_at)}</td>
                  <td>
                    {extra?.(item)}
                    {audit && (
                      <Button
                        variant="ghost"
                        onClick={() => setSelected(item.id)}
                      >
                        Buka audit
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="Tidak ada hasil"
          description="Tidak ada sumber daya yang cocok dalam scope dan filter ini."
        />
      )}
      <div className="editor-toolbar">
        <Button
          variant="secondary"
          disabled={cursors.length === 1 || list.isFetching}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          Sebelumnya
        </Button>
        <span>Halaman {cursors.length} · maksimal 10 item</span>
        <Button
          variant="secondary"
          disabled={!list.data?.next_cursor || !!list.error || list.isFetching}
          onClick={() => setCursors([...cursors, list.data!.next_cursor])}
        >
          Berikutnya
        </Button>
        <small>
          {list.data ? `Diperbarui ${date(list.data.refreshed_at)}` : ""}
        </small>
      </div>
      {detail.error && <Notice tone="error">{detail.error.message}</Notice>}
      {detail.data && !detail.error && (
        <div>
          <h3>Audit {detail.data.id}</h3>
          <p>
            {detail.data.verified
              ? "Event terautentikasi"
              : "Evidence belum terverifikasi"}
          </p>
          <pre className="canonical-definition">
            {JSON.stringify(detail.data.references, null, 2)}
          </pre>
          <Button variant="ghost" onClick={() => setSelected("")}>
            Tutup detail
          </Button>
        </div>
      )}
    </section>
  );
}
