import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { BenchPage, EvaluationPanel } from "../features/bench";
import type { Evaluation, Snapshot } from "../lib/types";

// Display-only fixture. Backend promotion tests execute the actual Bench.
const recorded: Evaluation = {
  id: "display-only",
  blueprint_id: "bp",
  version_id: "version",
  passed: 1,
  verified: false,
  total_scenarios: 4,
  passed_scenarios: 4,
  score: 1,
  details: [],
  evaluated_at: "2026-10-05T00:00:00Z",
  provenance: {
    evaluation_version: "research-safety-1.2.0",
    requested_model: "test",
    payload_hash: "test",
  },
};

describe("status bukti Bench", () => {
  it("tidak mengklaim PASS tersimpan sebagai bukti terverifikasi", () => {
    render(<EvaluationPanel evaluation={recorded} />);
    expect(
      screen.getByRole("heading", {
        name: "Evaluasi tidak terverifikasi",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/historis tetap disimpan/)).toBeInTheDocument();
    expect(screen.getByText(/persetujuan atau publikasi/)).toBeInTheDocument();
    expect(screen.getByText("Tidak Terverifikasi")).toHaveClass(
      "status-bench_unverified",
    );
    expect(screen.queryByText(/Versi dapat ditinjau/)).not.toBeInTheDocument();
  });
  it("menampilkan kelayakan hanya dari hasil terverifikasi", () => {
    render(<EvaluationPanel evaluation={{ ...recorded, verified: true }} />);
    expect(
      screen.getByRole("heading", { name: "Evaluasi lulus" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Versi dapat ditinjau/)).toBeInTheDocument();
    expect(screen.getByText("Lulus")).toHaveClass("status-bench_passed");
  });
  it.each([true, false])("2/4 tampil Gagal, verified=%s", (verified) => {
    render(
      <EvaluationPanel
        evaluation={{
          ...recorded,
          passed: 0,
          verified,
          passed_scenarios: 2,
          score: 0.5,
        }}
      />,
    );
    expect(screen.getByText("Gagal")).toHaveClass("status-failed");
    expect(screen.queryByText("Tidak Terverifikasi")).not.toBeInTheDocument();
  });
  it("riwayat 4/4 unverified memakai status warning, bukan Gagal", () => {
    const data: Snapshot = {
      evaluations: [recorded],
      versions: [],
      blueprints: [],
      assignments: [],
      approvals: [],
      runs: [],
      audit: [],
      permissions: {},
      budget: { max_tokens_per_run: 1000, cumulative_tokens: 0 },
    };
    render(
      <MemoryRouter>
        <BenchPage data={data} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Tidak Terverifikasi")).toHaveClass(
      "status-bench_unverified",
    );
    expect(screen.queryByText("Gagal")).not.toBeInTheDocument();
    expect(screen.getByText("4/4")).toBeInTheDocument();
  });
});
