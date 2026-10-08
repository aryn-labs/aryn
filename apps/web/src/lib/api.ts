import type { BenchCompletion, StreamEvent, StreamPayload, RunResponse } from "./types";

let csrf = "";
let pendingSession: Promise<void> | undefined;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public errorCode?: string,
    public correlationId?: string,
    public runId?: string,
  ) {
    super(message);
  }
}
async function session() {
  if (!pendingSession)
    pendingSession = fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      credentials: "same-origin",
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok)
          throw new ApiError(
            data.message || "Sesi lokal tidak dapat dibuat.",
            response.status,
          );
        if (typeof data.csrf !== "string")
          throw new ApiError(
            "Sesi development belum dapat diterbitkan oleh API Studio.",
            503,
          );
        csrf = data.csrf;
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError) throw error;
        throw new ApiError(
          "Koneksi ke API terputus. Pastikan layanan Studio masih berjalan.",
          0,
        );
      })
      .finally(() => {
        pendingSession = undefined;
      });
  return pendingSession;
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  if (!csrf) await session();
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError(
      "Koneksi ke API terputus. Pastikan layanan Studio masih berjalan.",
      0,
    );
  }
  if (response.status === 401) {
    csrf = "";
    throw new ApiError("Sesi development berakhir. Muat ulang halaman.", 401);
  }
  const data = await response.json().catch(() => ({
    message: "API belum memberikan respons yang dapat dibaca.",
  }));
  if (!response.ok)
    throw new ApiError(
      data.message || "Permintaan belum dapat diselesaikan. Coba kembali.",
      response.status,
      data.error_code, data.correlation_id, data.run_id,
    );
  return data;
}

export type { StreamEvent } from "./types";

export function readBenchCompletion(input: unknown): BenchCompletion {
  if (!input || typeof input !== "object") throw new ApiError("Kontrak hasil Bench tidak valid.", 502);
  const value = input as Partial<BenchCompletion>;
  if (
    typeof value?.evaluation_id !== "string" ||
    !value.evaluation_id ||
    typeof value?.version_id !== "string" ||
    !value.version_id ||
    value.evaluation?.id !== value.evaluation_id ||
    value.evaluation?.version_id !== value.version_id ||
    typeof value.evaluation?.verified !== "boolean"
  ) {
    throw new ApiError("Kontrak hasil Bench tidak valid.", 502);
  }
  return value as BenchCompletion;
}

export function readRunCompletion(input: unknown): RunResponse {
  if (!input || typeof input !== "object") throw new ApiError("Kontrak hasil Core tidak valid.", 502);
  const value = input as Partial<RunResponse>;
  if (!value.run_id || value.id !== value.run_id || value.requested_model !== value.model ||
      !["queued", "started", "running", "stopping", "completed", "failed", "cancelled", "outcome_unknown"].includes(value.status || "") ||
      !["measured", "unavailable"].includes(value.usage?.availability || "") ||
      (value.status === "completed" && (!value.execution_claim_verified || value.actual_model !== value.requested_model || !value.output_reference)) ||
      (value.assignment_id && (!value.assignment_provenance_verified || !value.agent_version_id || !value.agent_payload_hash || !value.assignment_transition_id)) ||
      (value.usage?.availability === "measured" && (value.usage.input_tokens < 0 || value.usage.output_tokens < 0 ||
        value.usage.total_tokens !== value.usage.input_tokens + value.usage.output_tokens))) {
    throw new ApiError("Kontrak hasil Core tidak valid.", 502);
  }
  return value as RunResponse;
}

export async function apiStream<T = Record<string, unknown>>(
  path: string,
  body: unknown,
  onEvent?: (event: StreamEvent) => void,
): Promise<T> {
  if (!csrf) await session();
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "Koneksi ke API terputus. Pastikan layanan Studio masih berjalan.",
      0,
    );
  }
  if (response.status === 401) {
    csrf = "";
    throw new ApiError("Sesi development berakhir. Muat ulang halaman.", 401);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({
      message: "Permintaan belum dapat diselesaikan. Coba kembali.",
    }));
    throw new ApiError(
      data.message || "Permintaan belum dapat diselesaikan. Coba kembali.",
      response.status,
      data.error_code, data.correlation_id, data.run_id,
    );
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const result = await response.json();
    return (
      path.endsWith("/bench") ? readBenchCompletion(result) : path.endsWith("/runs") ? readRunCompletion(result) : result
    ) as T;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new ApiError("Stream reader tidak tersedia", 500);
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: T | undefined;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";

    for (const chunk of chunks) {
      if (!chunk.trim()) continue;
      const eventMatch = chunk.match(/^event:\s*(.+)$/m);
      const dataMatch = chunk.match(/^data:\s*(.+)$/m);
      if (eventMatch && dataMatch) {
        const evType = eventMatch[1].trim();
        try {
          const parsedData = JSON.parse(dataMatch[1].trim());
          if (evType === "bench.completed" || evType === "run.completed") {
            if (evType === "bench.completed") readBenchCompletion(parsedData);
            else readRunCompletion(parsedData);
            finalResult = parsedData as T;
          }
          if (evType === "bench.error" || evType === "run.failed") {
            throw new ApiError(parsedData.message || "Operasi gagal.", 500, parsedData.error_code, parsedData.correlation_id, parsedData.run_id);
          }
          if (onEvent) {
            onEvent({ type: evType, data: parsedData as StreamPayload });
          }
        } catch (e) {
          if (e instanceof ApiError) throw e;
        }
      }
    }
  }

  if (!finalResult)
    throw new ApiError("Stream berakhir tanpa hasil operasi.", 502);
  return finalResult;
}
