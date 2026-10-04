import { useState } from "react";
import { Fingerprint, Folder, Search, ShieldCheck } from "lucide-react";
import { number } from "../lib/utils";
import { PageHeading } from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, AuditList, eventNames } from "../components/workspace";
export function Governance({ data }: Shared) {
  const [search, setSearch] = useState("");
  const events = data.audit.filter((e) =>
    `${eventNames[e.event_type] || ""} ${e.event_type} ${e.resource_id}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
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
          <h3>Identitas server</h3>
          <p>
            Browser memakai sesi lokal. Identitas bertanda tangan hanya
            diterbitkan di server.
          </p>
        </div>
        <div>
          <ShieldCheck size={21} />
          <h3>Persetujuan yang tepat</h3>
          <p>
            Keputusan manusia terikat pada hash konfigurasi dan evaluasi Bench
            terakhir.
          </p>
        </div>
        <div>
          <Folder size={21} />
          <h3>Lingkup proyek</h3>
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
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span>{number(events.length)} peristiwa</span>
      </div>
      <Panel
        title="Jejak audit"
        subtitle="Payload disamarkan oleh Core; referensi integritas tersedia pada setiap peristiwa."
      >
        <AuditList events={events} />
      </Panel>
    </>
  );
}
