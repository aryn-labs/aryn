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
