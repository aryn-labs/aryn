import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvaluationPanel } from "../features/bench";
import type { Evaluation } from "../lib/types";

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
        name: "Bukti evaluasi belum terverifikasi",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Publikasi diblokir/)).toBeInTheDocument();
    expect(screen.queryByText(/Versi dapat ditinjau/)).not.toBeInTheDocument();
  });
  it("menampilkan kelayakan hanya dari hasil terverifikasi", () => {
    render(<EvaluationPanel evaluation={{ ...recorded, verified: true }} />);
    expect(
      screen.getByRole("heading", { name: "Evaluasi lulus" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Versi dapat ditinjau/)).toBeInTheDocument();
  });
});
