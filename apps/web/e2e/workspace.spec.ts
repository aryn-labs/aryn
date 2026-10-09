import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";

for (const width of [390, 768, 1440]) {
  test(`workspace responsive, keyboard and axe at ${width}px in both themes`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const theme of ["dark", "light"]) {
      await page.goto("/");
      await expect(
        page.getByRole("heading", { name: "Ruang kerja agent Anda." }),
      ).toBeVisible();
      if (theme === "light")
        await page.getByRole("button", { name: "Gunakan tema terang" }).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(
        page.getByText("Biaya provider", { exact: true }),
      ).toBeVisible();
      if (width === 390) {
        const menu = page.getByRole("button", { name: "Buka navigasi" });
        await menu.click();
        const navigation = page.getByRole("dialog", {
          name: "Navigasi Studio",
        });
        await expect(navigation).toBeVisible();
        await page.keyboard.press("Shift+Tab");
        expect(
          await navigation.evaluate((element) =>
            element.contains(document.activeElement),
          ),
        ).toBe(true);
        await page.keyboard.press("Escape");
        await expect(menu).toBeFocused();
      }
      for (const path of ["/", "/projects", "/projects/proj_studio_research"]) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(
          page.getByText("Diperbarui", { exact: false }).first(),
        ).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        expect(
          (
            await new AxeBuilder({ page })
              .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
              .analyze()
          ).violations,
          `${width} ${theme} ${path}`,
        ).toEqual([]);
        const name =
          path === "/"
            ? "overview"
            : path === "/projects"
              ? "projects"
              : "divisions";
        await page.screenshot({
          path: info.outputPath(`${name}-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Lewati ke konten" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
  });
}

test("real division persistence, conflict, filter and project isolation", async ({
  page,
}) => {
  await page.goto("/projects/proj_studio_research");
  await page.getByRole("button", { name: "Buat division" }).click();
  await page.getByLabel("Nama division").fill("Tim Evidence");
  await page.getByLabel("Slug division").fill("tim-evidence");
  await page.getByLabel("Deskripsi division").fill("Struktur proyek nyata");
  await page.getByRole("button", { name: "Simpan division" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("row", { name: /Tim Evidence/ })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Edit Tim Evidence" }).click();
  const origin = "http://127.0.0.1:8711";
  const csrf = (
    await (
      await page.request.post("/api/session", {
        data: {},
        headers: { Origin: origin },
      })
    ).json()
  ).csrf;
  const prefix = "/api/projects/proj_studio_research";
  const division = (
    await (await page.request.get(prefix + "/resources/divisions")).json()
  ).items[0];
  const changed = await page.request.post(
    `${prefix}/divisions/${division.id}`,
    {
      headers: { Origin: origin, "X-CSRF-Token": csrf },
      data: {
        name: "Perubahan server",
        slug: division.slug,
        description: "",
        expected_generation: division.generation,
      },
    },
  );
  expect(changed.status()).toBe(200);
  await page.getByRole("button", { name: "Simpan division" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Tahap ini belum diizinkan",
  );
  await expect(page.getByLabel("Nama division")).toHaveValue("Tim Evidence");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Perbarui daftar" }).click();
  await expect(
    page.getByRole("row", { name: /Perubahan server/ }),
  ).toBeVisible();
  await page.getByLabel("Cari division").fill("missing");
  await expect(
    page.getByRole("heading", { name: "Tidak ada hasil filter" }),
  ).toBeVisible();
  await page
    .getByLabel("Pilih proyek")
    .selectOption("proj_studio_browser_secondary");
  await page.goto("/projects/proj_studio_browser_secondary");
  await expect(
    page.getByRole("heading", { name: "Belum ada division" }),
  ).toBeVisible();
  await expect(page.getByText("Perubahan server")).toHaveCount(0);
});

test("late project response cannot replace current project; summary avoids snapshot", async ({
  page,
}) => {
  let release!: () => void;
  let intercepted!: () => void;
  const ready = new Promise<void>((resolve) => {
    intercepted = resolve;
  });
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  const snapshots: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/snapshot")) snapshots.push(request.url());
  });
  await page.route(
    "**/api/projects/proj_studio_research/summary",
    async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.metrics.blueprints.value = 931;
      intercepted();
      await barrier;
      await route.fulfill({ response, json: body }).catch(() => {});
    },
  );
  await page.goto("/");
  await ready;
  await page
    .getByLabel("Pilih proyek")
    .selectOption("proj_studio_browser_secondary");
  await expect(page.locator(".studio-project-tag")).toHaveText(
    "Proyek Uji Kedua",
  );
  release();
  await expect(page.locator(".hud-metric").first()).toHaveText("0");
  await expect(page.getByText("931", { exact: true })).toHaveCount(0);
  expect(snapshots).toEqual([]);
});

test("stale, offline, session-expired and permission-changed states", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ruang kerja agent Anda." }),
  ).toBeVisible();
  await page.route("**/api/projects/*/summary", (route) =>
    route.fulfill({
      status: 503,
      json: { message: "API temporarily unavailable" },
    }),
  );
  await page.getByRole("button", { name: "Perbarui koneksi dan data" }).click();
  await expect(
    page.getByText(/Data terakhir · belum diperbarui/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja agent Anda." }),
  ).toBeVisible();
  await page.unroute("**/api/projects/*/summary");
  await page.route("**/api/projects/*/summary", (route) =>
    route.fulfill({ status: 403, json: { message: "Membership revoked" } }),
  );
  await page.getByRole("button", { name: "Perbarui koneksi dan data" }).click();
  await expect(
    page.getByRole("heading", { name: "Akses proyek dibatasi" }),
  ).toBeVisible();
  await expect(page.locator(".hud-metric")).toHaveCount(0);
  await page.unroute("**/api/projects/*/summary");
  await page.route("**/api/workspace/context", (route) => route.abort());
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja belum terhubung" }),
  ).toBeVisible();
  await page.unroute("**/api/workspace/context");
  await page.route("**/api/workspace/context", (route) =>
    route.fulfill({
      status: 401,
      json: { message: "Session expired", login_url: "/auth/login" },
    }),
  );
  await page.getByRole("button", { name: "Coba sambungkan kembali" }).click();
  await expect(
    page.getByRole("link", { name: "Masuk melalui penyedia identitas" }),
  ).toHaveAttribute("href", "/auth/login");
});

test("future detail routes are truthful and have no enabled feature actions", async ({
  page,
}) => {
  for (const path of [
    "/workflows/demo/builder",
    "/outputs/demo",
    "/brief/demo",
    "/relay/demo",
    "/automations",
    "/capabilities",
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: "Belum tersedia", exact: true }),
    ).toBeVisible();
    await expect(page.locator("main button")).toHaveCount(0);
  }
  await page.goto("/operations");
  await expect(
    page.getByRole("heading", { name: "Agent Operations", exact: true }),
  ).toBeVisible();
  for (const path of ["/factory/demo/builder", "/bench/evaluations/demo"]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", {
        name: "Sumber daya tidak tersedia",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".definition-canvas, .bench-canvas")).toHaveCount(
      0,
    );
  }
  await page.goto("/runs/missing");
  await expect(page.getByText("Run yang dipilih tidak tersedia")).toBeVisible();
  await page.goto("/runs?hasil=missing");
  await expect(page.getByText("Run yang dipilih tidak tersedia")).toBeVisible();
});

test.describe("large deterministic workspace", () => {
  test.use({ workspaceDataset: "large" });
  test("summary and interactive navigation meet development thresholds", async ({
    page,
  }, info) => {
    const durations: number[] = [];
    for (let index = 0; index < 10; index++) {
      const start = performance.now();
      await page.goto(index % 2 ? "/projects" : "/");
      await expect(
        page.getByText("Diperbarui", { exact: false }).first(),
      ).toBeVisible();
      durations.push(performance.now() - start);
    }
    durations.sort((a, b) => a - b);
    const summary = [];
    for (let index = 0; index < 20; index++) {
      const start = performance.now();
      const response = await page.request.get(
        "/api/projects/proj_studio_research/summary",
      );
      expect(response.ok()).toBe(true);
      const value = await response.json();
      expect(value.metrics.blueprints.value).toBe(200);
      expect(value.metrics.runs.value).toBe(1000);
      expect(value.latest_runs).toHaveLength(5);
      expect(
        value.latest_audits.every(
          (item: { verified: boolean }) => item.verified,
        ),
      ).toBe(true);
      summary.push(performance.now() - start);
    }
    summary.sort((a, b) => a - b);
    const evidence = {
      fixture: { blueprints: 200, runs: 1000, audits: 5000, divisions: 200 },
      navigation: { p50_ms: durations[4], p95_ms: durations[9] },
      summary: { p50_ms: summary[9], p95_ms: summary[19] },
      environment: process.platform,
    };
    await info.attach("workspace-performance", {
      body: JSON.stringify(evidence, null, 2),
      contentType: "application/json",
    });
    expect(evidence.navigation.p95_ms).toBeLessThanOrEqual(3000);
    expect(evidence.summary.p95_ms).toBeLessThanOrEqual(2000);
    await page.goto("/projects/proj_studio_research");
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(10);
    await page.getByRole("button", { name: "Berikutnya" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Halaman 2" }),
    ).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(10);
    const lifecycleReads: string[] = [];
    page.on("request", (request) => {
      if (/\/(snapshot|lifecycle)(\?|$)/.test(request.url()))
        lifecycleReads.push(request.url());
    });
    const resourceNavigation: { path: string; milliseconds: number }[] = [];
    for (const path of [
      "/factory",
      "/governance",
      "/runs",
      "/approvals",
      "/operations",
    ]) {
      const start = performance.now();
      await page.goto(path);
      await expect(
        page.getByText("Diperbarui", { exact: false }).last(),
      ).toBeVisible();
      resourceNavigation.push({
        path,
        milliseconds: performance.now() - start,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    expect(lifecycleReads.filter((path) => path.includes("/snapshot"))).toEqual(
      [],
    );
    expect(
      lifecycleReads.filter(
        (path) => !path.includes("lifecycle?") && path.includes("lifecycle"),
      ),
    ).toEqual([]);
    expect(resourceNavigation.every((item) => item.milliseconds <= 3000)).toBe(
      true,
    );
    await info.attach("agent-resource-navigation", {
      body: JSON.stringify(resourceNavigation, null, 2),
      contentType: "application/json",
    });
  });
});
