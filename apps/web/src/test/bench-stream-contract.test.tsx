import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BenchPage } from "../features/bench";
import { studioFixture, versionA } from "./studio-fixtures";
import type { BenchCompletion, Evaluation } from "../lib/types";

const evaluation: Evaluation = {
  id: "evaluation-new",
  version_id: versionA.id,
  blueprint_id: versionA.blueprint_id,
  verified: true,
  passed: 1,
  passed_scenarios: 4,
  total_scenarios: 4,
  score: 1,
  details: [],
  evaluated_at: versionA.created_at,
  provenance: {
    requested_model: versionA.model,
    payload_hash: versionA.payload_hash,
    evaluation_version: "test",
  },
};
const completion: BenchCompletion = {
  evaluation_id: evaluation.id,
  version_id: evaluation.version_id,
  evaluation,
};
function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="url">
      {location.pathname}
      {location.search}
    </output>
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("kontrak completion Bench", () => {
  it("bench.completed memilih evaluation_id dan sinkronisasi URL sebelum snapshot refresh", async () => {
    const props = studioFixture();
    props.workspace.runtime.ready = true;
    props.data.evaluations = [{ ...evaluation, id: "older-evaluation" }];
    let release!: () => void;
    const refresh = new Promise<void>((resolve) => {
      release = resolve;
    });
    props.actStream = vi.fn(async (_path, _body, _success, onEvent) => {
      onEvent?.({ type: "bench.completed", data: completion });
      await refresh;
      return completion;
    });
    render(
      <MemoryRouter
        initialEntries={["/bench?versi=version-a&evaluasi=older-evaluation"]}
      >
        <BenchPage {...props} />
        <LocationProbe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getAllByRole("button", { name: "Jalankan Bench" })[0],
    );
    expect(screen.getByTestId("url")).toHaveTextContent(
      "/bench?versi=version-a&evaluasi=evaluation-new",
    );
    expect(
      screen.getByRole("heading", { name: "Evaluasi lulus" }),
    ).toBeInTheDocument();
    await act(async () => {
      release();
      await refresh;
    });
    expect(
      screen.getByRole("heading", { name: "Evaluasi lulus" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Pilih versi untuk dievaluasi"), {
      target: { value: "version-b" },
    });
    expect(screen.getByTestId("url")).toHaveTextContent(
      "/bench?versi=version-b",
    );
    expect(
      screen.queryByRole("heading", { name: "Evaluasi lulus" }),
    ).not.toBeInTheDocument();
  });

  it("URL evaluasi yang tidak ditemukan tidak diganti evaluasi lama", () => {
    const props = studioFixture();
    props.data.evaluations = [evaluation];
    render(
      <MemoryRouter
        initialEntries={["/bench?versi=version-a&evaluasi=missing"]}
      >
        <BenchPage {...props} />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("heading", { name: "Evaluasi lulus" }),
    ).not.toBeInTheDocument();
  });

  it("apiStream mengembalikan completion terfragmentasi dengan evaluation_id", async () => {
    vi.resetModules();
    const { apiStream } = await import("../lib/api");
    const frame = `event: bench.completed\ndata: ${JSON.stringify(completion)}\n\n`;
    const stream = new ReadableStream({
      start(controller) {
        for (const chunk of [frame.slice(0, 51), frame.slice(51)])
          controller.enqueue(new TextEncoder().encode(chunk));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ csrf: "test" })))
        .mockResolvedValueOnce(
          new Response(stream, {
            headers: { "Content-Type": "text/event-stream" },
          }),
        ),
    );
    const events = vi.fn();
    await expect(
      apiStream("/versions/version-a/bench", {}, events),
    ).resolves.toEqual(completion);
    expect(events).toHaveBeenCalledWith({
      type: "bench.completed",
      data: completion,
    });
  });

  it.each([
    { id: "legacy-id", version_id: versionA.id },
    { ...completion, evaluation_id: "mismatched" },
  ])("completion ambigu ditolak", async (payload) => {
    vi.resetModules();
    const { apiStream } = await import("../lib/api");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ csrf: "test" })))
        .mockResolvedValueOnce(
          new Response(
            `event: bench.completed\ndata: ${JSON.stringify(payload)}\n\n`,
            { headers: { "Content-Type": "text/event-stream" } },
          ),
        ),
    );
    await expect(apiStream("/versions/version-a/bench", {})).rejects.toThrow(
      "Kontrak hasil Bench tidak valid",
    );
  });

  it("stream terputus tanpa completion tidak dinyatakan selesai", async () => {
    vi.resetModules();
    const { apiStream } = await import("../lib/api");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ csrf: "test" })))
        .mockResolvedValueOnce(
          new Response("event: bench.started\ndata: {}\n\n", {
            headers: { "Content-Type": "text/event-stream" },
          }),
        ),
    );
    await expect(apiStream("/versions/version-a/bench", {})).rejects.toThrow(
      "Stream berakhir tanpa hasil",
    );
  });
});
