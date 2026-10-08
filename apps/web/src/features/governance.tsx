import { useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Fingerprint,
  Folder,
  Search,
  ShieldCheck,
} from "lucide-react";
import { number } from "../lib/utils";
import { Empty, PageHeading } from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, AuditList, eventNames } from "../components/workspace";

const PAGE_SIZE = 8;

function getPageNumbers(
  currentPage: number,
  totalPages: number,
): (number | string)[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages: (number | string)[] = [1];
  if (currentPage > 3) {
    pages.push("ellipsis-1");
  }
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);
  for (let i = start; i <= end; i++) {
    pages.push(i);
  }
  if (currentPage < totalPages - 2) {
    pages.push("ellipsis-2");
  }
  pages.push(totalPages);
  return pages;
}

export function Governance({ data }: Shared) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const events = useMemo(() => {
    return data.audit.filter((e) =>
      `${eventNames[e.event_type] || ""} ${e.event_type} ${e.resource_id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    );
  }, [data.audit, search]);

  const totalEvents = events.length;
  const totalPages = Math.max(1, Math.ceil(totalEvents / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, totalEvents);
  const paginatedEvents = events.slice(startIndex, endIndex);
  const pageNumbers = getPageNumbers(currentPage, totalPages);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  return (
    <>
      <PageHeading
        eyebrow="OTORITAS CORE"
        title="Tata Kelola"
        description="Izin, lingkup proyek, dan bukti setiap keputusan operasional."
      />
      <div className="governance-principles">
        <div>
          <Fingerprint size={21} />
          <h2>Identitas server</h2>
          <p>
            Browser memakai sesi lokal. Identitas bertanda tangan hanya
            diterbitkan di server.
          </p>
        </div>
        <div>
          <ShieldCheck size={21} />
          <h2>Persetujuan yang tepat</h2>
          <p>
            Keputusan manusia terikat pada hash konfigurasi dan evaluasi Bench
            terakhir.
          </p>
        </div>
        <div>
          <Folder size={21} />
          <h2>Lingkup proyek</h2>
          <p>
            Keanggotaan dan izin diperiksa Core untuk setiap aksi baca dan
            mutasi.
          </p>
        </div>
      </div>
      <div className="list-toolbar">
        <div className="search-field">
          <Search size={16} />
          <input
            aria-label="Cari audit"
            placeholder="Cari aktivitas atau ID sumber daya…"
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
        <span>
          {totalEvents > 0
            ? `Menampilkan ${startIndex + 1}–${endIndex} dari ${number(totalEvents)} peristiwa`
            : "0 peristiwa"}
        </span>
      </div>
      <Panel
        title="Jejak audit"
        subtitle="Payload disamarkan oleh Core; referensi integritas tersedia pada setiap peristiwa."
        action={
          totalPages > 1 ? (
            <span className="subtle-label">
              HALAMAN {currentPage} / {totalPages}
            </span>
          ) : undefined
        }
      >
        {events.length ? (
          <>
            <AuditList events={paginatedEvents} />
            {totalPages > 1 && (
              <div
                className="pagination-bar"
                aria-label="Navigasi halaman jejak audit"
              >
                <div className="pagination-info">
                  Halaman <strong>{currentPage}</strong> dari{" "}
                  <strong>{totalPages}</strong>
                  <span className="pagination-count-note">
                    ({number(totalEvents)} total peristiwa)
                  </span>
                </div>
                <div className="pagination-controls">
                  <button
                    className="pagination-btn"
                    disabled={currentPage === 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    aria-label="Halaman sebelumnya"
                  >
                    <ChevronLeft size={15} />
                    <span>Sebelumnya</span>
                  </button>

                  <div className="pagination-pages">
                    {pageNumbers.map((p, idx) =>
                      typeof p === "number" ? (
                        <button
                          key={p}
                          className={`pagination-pill ${p === currentPage ? "active" : ""}`}
                          onClick={() => setPage(p)}
                          aria-label={`Buka halaman ${p}`}
                          aria-current={p === currentPage ? "page" : undefined}
                        >
                          {p}
                        </button>
                      ) : (
                        <span
                          key={`ellipsis-${idx}`}
                          className="pagination-ellipsis"
                        >
                          …
                        </span>
                      ),
                    )}
                  </div>

                  <button
                    className="pagination-btn"
                    disabled={currentPage === totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    aria-label="Halaman berikutnya"
                  >
                    <span>Berikutnya</span>
                    <ChevronRight size={15} />
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <Empty
            title="Tidak ada peristiwa ditemukan"
            description={
              search
                ? `Tidak ada catatan audit yang cocok dengan "${search}".`
                : "Belum ada jejak aktivitas Core yang tercatat."
            }
            action={search ? "Bersihkan pencarian" : undefined}
            onAction={
              search
                ? () => {
                    setSearch("");
                    setPage(1);
                  }
                : undefined
            }
          />
        )}
      </Panel>
    </>
  );
}
