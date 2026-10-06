import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Overview } from "../features/overview";
import { Runs } from "../features/runs";
import { Approvals } from "../features/approvals";
import { studioFixture, versionA } from "./studio-fixtures";

vi.mock("../components/canvas/aryn-canvas", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../components/canvas/aryn-canvas")>();
  return {
    ...actual,
    ArynCanvas: (props: any) => (
      <div>
        <div data-testid="bound-canvas">
          {JSON.stringify({
            version: props.version?.id,
            nodes: props.initialNodes,
          })}
        </div>
        <actual.ArynCanvas {...props} />
      </div>
    ),
  };
});

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
  it("Run A tetap memakai versi A setelah form memilih penugasan B", () => {
    render(
      <MemoryRouter initialEntries={["/runs?hasil=run-a"]}>
        <Runs {...studioFixture()} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Penugasan agent"), {
      target: { value: "assignment-b" },
    });
    expect(screen.getByTestId("bound-canvas")).toHaveTextContent(
      '"version":"version-a"',
    );
    expect(screen.getByTestId("bound-canvas")).not.toHaveTextContent(
      "Instruksi baru Agent B",
    );
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
    expect(screen.getByLabelText("Penugasan agent")).toHaveValue(
      "assignment-b",
    );
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
    expect(screen.getByLabelText("Penugasan agent")).toHaveValue(
      "assignment-b",
    );
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
