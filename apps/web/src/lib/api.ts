let csrf = "";
let pendingSession: Promise<void> | undefined;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
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
    );
  return data;
}

export type StreamEvent = {
  type: string;
  data: any;
};

export async function apiStream<T = any>(
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
    );
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
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
            finalResult = parsedData as T;
          }
          if (evType === "bench.error" || evType === "run.failed") {
            throw new ApiError(parsedData.message || "Operasi gagal.", 500);
          }
          if (onEvent) {
            onEvent({ type: evType, data: parsedData });
          }
        } catch (e) {
          if (e instanceof ApiError) throw e;
        }
      }
    }
  }

  return finalResult as T;
}
