import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Overview } from "../features/overview";
import { Runs } from "../features/runs";
import { Approvals } from "../features/approvals";
import { studioFixture, versionA } from "./studio-fixtures";

vi.mock("../components/canvas/aryn-canvas", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../components/canvas/aryn-canvas")>();
  return {
    ...actual,
    ArynCanvas: (props: any) => (
      <div>
        <div data-testid="bound-canvas">
          {JSON.stringify({
            version: props.version?.id,
            nodes: props.initialNodes,
            edges: props.initialEdges,
            run: props.run?.id,
          })}
        </div>
        <actual.ArynCanvas {...props} />
      </div>
    ),
  };
});

function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="url">
        {location.pathname}
        {location.search}
      </output>
      <button
        onClick={() => navigate("/runs?hasil=run-a&penugasan=assignment-b")}
      >
        Pilih B melalui URL
      </button>
    </>
  );
}

describe("konteks Studio", () => {
  it("Ringkasan menampilkan project aktif, bukan proyek pertama/organization", () => {
    render(
      <MemoryRouter>
        <Overview {...studioFixture()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Proyek Aktif")).toBeInTheDocument();
    expect(screen.queryByText("Integritas Audit")).not.toBeInTheDocument();
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
    expect(screen.getByText(/ARYN Runtime.*tidak tersedia/i)).not.toHaveClass(
      "text-success",
    );
  });
  it("/runs tanpa hasil adalah New Execution; selector B mengikat canvas B tanpa output historis", () => {
    render(
      <MemoryRouter initialEntries={["/runs"]}>
        <Runs {...studioFixture()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("NEW EXECUTION")).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "OUTPUT" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      "Hasil historis A",
    );
    fireEvent.change(screen.getByLabelText("Penugasan agent"), {
      target: { value: "assignment-b" },
    });
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-b"',
    );
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      "Hasil historis A",
    );
    const graph = JSON.parse(screen.getByTestId("bound-canvas").textContent!);
    expect(graph.nodes.every((n: any) => n.data.status === "idle")).toBe(true);
    expect(graph.edges.every((e: any) => !e.animated)).toBe(true);
    expect(graph.nodes.find((n: any) => n.id === "exec-agent").data.label).toBe(
      "Agent B",
    );
    expect(graph.nodes.find((n: any) => n.id === "exec-model").data.label).toBe(
      "model-b",
    );
  });
  it("Historical A tetap A setelah memilih B pada mode baru atau lewat URL", () => {
    render(
      <MemoryRouter initialEntries={["/runs"]}>
        <Runs {...studioFixture()} />
        <LocationProbe />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Penugasan agent"), {
      target: { value: "assignment-b" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Lihat hasil eksekusi run-a" }),
    );
    expect(screen.getByText("HISTORICAL RUN")).toBeInTheDocument();
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-a"',
    );
    expect(screen.queryByLabelText("Penugasan agent")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Instruksi riset")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "DETAIL" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "OUTPUT" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "TRACE" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Pilih B melalui URL"));
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-a"',
    );
    fireEvent.click(screen.getByRole("button", { name: "Eksekusi baru" }));
    expect(screen.getByLabelText("Penugasan agent")).toHaveValue(
      "assignment-b",
    );
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-b"',
    );
  });
  it("run selesai berpindah ke hasil run baru; pending sebelum actual event tetap idle", async () => {
    const fixture = studioFixture();
    fixture.workspace.runtime.ready = true;
    let complete!: () => void;
    const barrier = new Promise<void>((resolve) => {
      complete = resolve;
    });
    function Harness() {
      const [data, setData] = useState(fixture.data);
      return (
        <>
          <Runs
            {...fixture}
            data={data}
            actStream={async () => {
              await barrier;
              setData({
                ...data,
                runs: [
                  {
                    ...data.runs[0],
                    id: "new-run-b",
                    session_id: "assignment-b",
                    assignment_id: "assignment-b",
                    agent_version_id: "version-b",
                    output: "Output baru B",
                    model: "model-b",
                  },
                  ...data.runs,
                ],
              });
              return { run_id: "new-run-b" };
            }}
          />
          <LocationProbe />
        </>
      );
    }
    render(
      <MemoryRouter initialEntries={["/runs"]}>
        <Harness />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Penugasan agent"), {
      target: { value: "assignment-b" },
    });
    fireEvent.change(screen.getByLabelText("Instruksi riset"), {
      target: { value: "Riset baru B." },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Jalankan agent" }));
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      '"status":"running"',
    );
    await act(async () => {
      complete();
      await barrier;
    });
    await waitFor(() =>
      expect(screen.getByTestId("url")).toHaveTextContent(
        "/runs?hasil=new-run-b",
      ),
    );
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-b"',
    );
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      "Output baru B",
    );
    expect(screen.getByText("HISTORICAL RUN")).toBeInTheDocument();
  });
  it("pending permintaan baru tidak memberi status running pada node historis", () => {
    render(
      <MemoryRouter initialEntries={["/runs?hasil=run-a"]}>
        <Runs {...studioFixture()} pending />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      '"status":"running"',
    );
  });
  it("historis tetap memakai assignment nonaktif, sementara form memilih assignment aktif", () => {
    const props = studioFixture();
    props.data.assignments[0].status = "inactive";
    render(
      <MemoryRouter initialEntries={["/runs?hasil=run-a"]}>
        <Runs {...props} />
      </MemoryRouter>,
    );
    expect(screen.queryByLabelText("Penugasan agent")).not.toBeInTheDocument();
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-a"',
    );
  });
  it("run yang tidak ditemukan tidak diganti dengan hasil run lain", () => {
    render(
      <MemoryRouter initialEntries={["/runs?hasil=missing"]}>
        <Runs {...studioFixture()} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      "Instruksi historis khusus Agent A.",
    );
    expect(
      screen.getByText("Run yang dipilih tidak tersedia"),
    ).toBeInTheDocument();
  });
  it("konfigurasi historis dengan integritas tidak valid ditandai secara jujur", () => {
    const props = studioFixture();
    props.data.versions = props.data.versions.map((v) =>
      v.id === versionA.id ? { ...v, integrity_valid: false } : v,
    );
    render(
      <MemoryRouter initialEntries={["/runs?hasil=run-a"]}>
        <Runs {...props} />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/Integritas versi historis tidak valid/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Penugasan agent")).not.toBeInTheDocument();
  });
  it("versi approved tidak termasuk Perlu ditinjau", () => {
    const props = studioFixture();
    props.data.versions = [{ ...versionA, status: "approved" }];
    render(
      <MemoryRouter>
        <Approvals {...props} />
      </MemoryRouter>,
    );
    expect(
      within(screen.getByRole("button", { name: /Perlu ditinjau/ })).getByText(
        "0",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Tinjau versi/ }),
    ).not.toBeInTheDocument();
  });
});
