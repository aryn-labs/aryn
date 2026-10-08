import { afterEach, beforeEach, expect, it, vi } from "vitest";

beforeEach(() => vi.resetModules());
afterEach(() => vi.unstubAllGlobals());

it("anonymous hosted session exposes only the fixed OIDC login route", async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        error_code: "authentication_required",
        login_url: "/auth/login",
      }),
      { status: 401 },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const { api } = await import("../lib/api");
  await expect(api("/workspace")).rejects.toMatchObject({
    status: 401,
    loginUrl: "/auth/login",
  });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("an arbitrary login redirect from an error is not accepted", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error_code: "authentication_required",
          login_url: "https://evil.example",
        }),
        { status: 401 },
      ),
    ),
  );
  const { api } = await import("../lib/api");
  await expect(api("/workspace")).rejects.toMatchObject({
    status: 401,
    loginUrl: undefined,
  });
});

it("logout uses the existing same-origin session CSRF contract", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ csrf: "server-csrf", mode: "oidc" })),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ logged_out: true })));
  vi.stubGlobal("fetch", fetch);
  const { logout } = await import("../lib/api");
  await logout();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/logout",
    expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      headers: expect.objectContaining({ "X-CSRF-Token": "server-csrf" }),
    }),
  );
});
