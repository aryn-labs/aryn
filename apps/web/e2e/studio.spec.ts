import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function settleTheme(page: import("@playwright/test").Page) {
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.evaluate(async () => {
    // Measure settled colors, without disabling animations or accessibility rules.
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.effect?.getComputedTiming().iterations !== Infinity,
        )
        .map((animation) => animation.finished.catch(() => {})),
    );
  });
}

async function createUatBench(page: import("@playwright/test").Page) {
  await page.goto("/bench");
  const origin = "http://127.0.0.1:8711";
  const bootstrap = await page.request.post("/api/session", {
    data: {},
    headers: { Origin: origin },
  });
  const headers = {
    Origin: origin,
    "X-CSRF-Token": (await bootstrap.json()).csrf,
  };
  const prefix = "/api/projects/proj_studio_research";
  const slug = `uat-bench-${Date.now()}`;
  const bpResponse = await page.request.post(`${prefix}/blueprints`, {
    data: { name: slug, slug },
    headers,
  });
  expect(bpResponse.status()).toBe(201);
  const bp = await bpResponse.json();
  const workspace = await (await page.request.get("/api/workspace")).json();
  const model = workspace.models.find(
    (m: { availability: string }) => m.availability === "available",
  ).model_id;
  const versionResponse = await page.request.post(
    `${prefix}/blueprints/${bp.id}/versions`,
    {
      data: {
        version_number: "1.0.0",
        system_prompt:
          "Follow research safety guidelines and abstain without evidence.",
        model,
        temperature: 0.3,
        max_tokens: 512,
        tool_grants: [],
      },
      headers,
    },
  );
  expect(versionResponse.status()).toBe(201);
  const version = await versionResponse.json();
  const response = await page.request.post(
    `${prefix}/versions/${version.id}/bench`,
    { data: { allow_remote_model: true }, headers },
  );
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.passed_scenarios).toBe(4);
  return { bp, version, result, prefix };
}

test("navigasi, tema, empty state, aksesibilitas dan responsivitas", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ruang kerja agent Anda." }),
  ).toBeVisible();
  await expect(
    page.getByText("Agent pertama Anda dimulai di sini"),
  ).toBeVisible();
  const logo = page.getByRole("img", { name: "Logo ARYN" });
  await expect(logo).toBeVisible();
  await expect(logo).toHaveAttribute("draggable", "false");
  await expect(logo).toHaveJSProperty("complete", true);
  expect(
    await logo.evaluate((image: HTMLImageElement) => image.naturalWidth),
  ).toBeGreaterThan(0);
  expect(
    await logo.evaluate((image) =>
      image.closest("a, button, [role='button'], [tabindex]"),
    ),
  ).toBeNull();
  const darkLogo = await logo.getAttribute("src");
  const flowName = "Alur agent dari blueprint hingga eksekusi";
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      !request.url().endsWith("/api/session")
    ) {
      mutations.push(request.url());
    }
  });
  const flow = page.getByRole("list", { name: flowName });
  await expect(flow.getByRole("link")).toHaveCount(7);
  const stageDestinations = [
    ["Blueprint", "/factory", "Agent Factory"],
    ["Versi", "/factory", "Agent Factory"],
    ["Bench", "/bench", "Bench"],
    ["Persetujuan", "/approvals", "Persetujuan"],
    ["Publikasi", "/factory", "Agent Factory"],
    ["Penugasan", "/factory", "Agent Factory"],
    ["Eksekusi", "/runs", "Eksekusi"],
  ];
  for (const [index, [stage, path, heading]] of stageDestinations.entries()) {
    const link = page.getByRole("list", { name: flowName }).getByRole("link", {
      name: `Tahap ${index + 1}: ${stage} — buka ${heading}`,
    });
    await expect(link).toHaveAttribute("href", path);
    await link.click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true, level: 1 }),
    ).toBeVisible();
    await page.goto("/");
  }
  await flow.getByRole("link").first().focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Agent Factory", exact: true, level: 1 }),
  ).toBeVisible();
  await page.goto("/");
  expect(mutations).toEqual([]); // Opening a stage must never create or promote an agent.
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-dark.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Gunakan tema terang" }).click();
  await settleTheme(page);
  await expect(logo).not.toHaveAttribute("src", darkLogo!);
  await expect(logo).toHaveJSProperty("complete", true);
  expect(
    await logo.evaluate((image: HTMLImageElement) => image.naturalWidth),
  ).toBeGreaterThan(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Gunakan tema gelap" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../.local/evidence/studio-light.png",
    fullPage: true,
  });
  for (const name of [
    "Agent Factory",
    "Bench",
    "Persetujuan",
    "Eksekusi",
    "Brief",
    "Relay",
    "Tata Kelola",
    "Pengaturan",
  ]) {
    await page
      .getByRole("navigation")
      .getByRole("link", { name: new RegExp(`^${name}( Belum tersedia)?$`) })
      .click();
    await expect(
      page.getByRole("heading", { name, exact: true, level: 1 }),
    ).toBeVisible();
  }
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/");
  await expect(
    page.getByRole("list", { name: flowName }).getByRole("link"),
  ).toHaveCount(7);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../../.local/evidence/studio-tablet.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("list", { name: flowName }).getByRole("link"),
  ).toHaveCount(7);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../../.local/evidence/studio-flow-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Buka navigasi" }).click();
  await expect(logo).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Agent Factory", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Agent Factory", exact: true, level: 1 }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("UAT Bench membedakan Lulus, Tidak Terverifikasi, dan Gagal", async ({
  page,
}) => {
  const { bp, result, prefix } = await createUatBench(page);
  await page.goto("/bench");
  let row = page.getByRole("row").filter({ hasText: bp.name });
  await expect(row.getByText("Lulus", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: /Lihat hasil/ }).click();
  await expect(
    page.getByRole("heading", { name: "Evaluasi lulus", exact: true }),
  ).toBeVisible();

  // UI-only negative projection of a real Bench result. No PASS row is inserted,
  // and no backend approval/publish is executed against the projected snapshot.
  let historicalFailure = false;
  await page.route("**/api/projects/*/snapshot", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const evaluation = data.evaluations.find(
      (e: { id: string }) => e.id === result.evaluation_id,
    );
    evaluation.verified = false;
    if (historicalFailure) {
      evaluation.passed = 0;
      evaluation.passed_scenarios = 2;
      evaluation.score = 0.5;
    }
    const version = data.versions.find(
      (v: { id: string }) => v.id === evaluation.version_id,
    );
    version.bench_eligible = false;
    version.governance_valid = false;
    await route.fulfill({ response, json: data });
  });
  await page.reload();
  row = page.getByRole("row").filter({ hasText: bp.name });
  const warning = row.getByText("Tidak Terverifikasi", { exact: true });
  await expect(warning).toBeVisible();
  await expect(row.getByText("Gagal", { exact: true })).toHaveCount(0);
  await expect(row).toContainText("4/4");
  expect(await warning.evaluate((el) => getComputedStyle(el).color)).toBe(
    "rgb(245, 158, 11)",
  );
  await expect(page.getByText(/Hasil historis tetap disimpan/)).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/uat-bench-unverified.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Gunakan tema terang" }).click();
  await settleTheme(page);
  expect(
    (
      await new AxeBuilder({ page })
        .include(".status-bench_unverified")
        .include(".notice-warning")
        .include(".score.text-warning")
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Gunakan tema gelap" }).click();

  historicalFailure = true;
  await page.reload();
  await expect(row.getByText("Gagal", { exact: true })).toBeVisible();
  await expect(row).toContainText("2/4");
  await expect(
    row.getByText("Tidak Terverifikasi", { exact: true }),
  ).toHaveCount(0);
  const stored = await (await page.request.get(`${prefix}/snapshot`)).json();
  const original = stored.evaluations.find(
    (e: { id: string }) => e.id === result.evaluation_id,
  );
  expect(original.passed_scenarios).toBe(4);
  expect(original.verified).toBe(true); // Display projection never changes the stored evidence.
});

test("UAT model unavailable memblokir tombol Bench dengan pesan Indonesia", async ({
  page,
}) => {
  const { bp, version } = await createUatBench(page);
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.models.find(
      (m: { model_id: string }) => m.model_id === version.model,
    ).availability = "unavailable";
    await route.fulfill({ response, json: data });
  });
  await page.goto(`/factory/${bp.id}?versi=${version.id}`);
  await expect(
    page.getByRole("button", { name: "Jalankan Bench", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Model tidak tersedia di provider\/runtime/),
  ).toBeVisible();
});

test("vertical slice HTTP nyata ke Core dengan runtime pengujian terisolasi", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/factory");
  const logo = page.getByRole("img", { name: "Logo ARYN" });
  const beforeLogoClick = page.url();
  await logo.click();
  await expect(page).toHaveURL(beforeLogoClick);
  await logo.evaluate((image: HTMLImageElement) => image.focus());
  await expect(logo).not.toBeFocused();
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nama agent").fill("Research Agent — Tes Terisolasi");
  await dialog
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Research Agent — Tes Terisolasi" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Buat versi pertama" }).click();
  await dialog.getByRole("button", { name: "Simpan versi" }).click();
  await expect(
    page.getByRole("button", { name: "Jalankan Bench" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Publikasikan versi" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Jalankan Bench" }).click();
  await expect(
    dialog.getByRole("button", { name: "Mulai evaluasi" }),
  ).toBeDisabled();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Mulai evaluasi" }).click();
  await expect(
    page.getByRole("heading", { name: "Evaluasi lulus", exact: true }),
  ).toBeVisible();
  await page.locator(".scenario-result").first().locator("summary").click();
  await expect(
    page.getByText("I cannot ignore research safety guidelines."),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("tab", { name: "Konfigurasi" }).click();
  await page.getByRole("button", { name: "Tinjau dan setujui" }).click();
  await dialog
    .getByLabel("Catatan persetujuan")
    .fill("Lulus empat skenario pada runtime pengujian terisolasi.");
  await dialog.getByRole("button", { name: "Setujui versi" }).click();
  await page.getByRole("button", { name: "Publikasikan versi" }).click();
  await dialog
    .getByRole("button", { name: "Publikasikan", exact: true })
    .click();
  await expect(
    page.getByText("Versi ini dipublikasikan dan tidak dapat diubah.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Penugasan" }).click();
  await page
    .getByRole("button", { name: "Buat penugasan", exact: true })
    .first()
    .click();
  await dialog.getByLabel("Peran operasional").fill("Peneliti tes terisolasi");
  await dialog
    .getByRole("button", { name: "Buat penugasan", exact: true })
    .click();
  await page.getByRole("button", { name: "Buka Eksekusi" }).click();
  await page
    .getByLabel("Instruksi riset")
    .fill("Jelaskan perbedaan likuiditas dan solvabilitas.");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Jalankan agent", exact: true })
    .click();
  await expect(
    page.getByText("[PENGUJIAN TERISOLASI] Likuiditas berkaitan", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.locator(".usage-row")).toContainText("50");
  await page.reload();
  await expect(
    page.getByText("[PENGUJIAN TERISOLASI] Likuiditas berkaitan", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^Audit / }).click();
  await expect(
    page.getByText("Eksekusi selesai", { exact: true }),
  ).toBeVisible();
  const firstAudit = page.locator(".audit-event").first();
  const auditDetails = firstAudit.locator(".audit-details");
  const auditToggle = auditDetails.locator("summary");
  const statusBefore = await firstAudit.locator(".status").boundingBox();
  expect(statusBefore?.height).toBe(24);
  await auditToggle.focus();
  await page.keyboard.press("Enter");
  await expect(auditDetails).toHaveAttribute("open", "");
  await expect(auditToggle).toHaveText("Tutup detail", { useInnerText: true });
  await expect(
    firstAudit.getByText("Peristiwa Core", { exact: true }),
  ).toBeVisible();
  expect((await firstAudit.locator(".status").boundingBox())?.height).toBe(
    statusBefore?.height,
  );
  await auditToggle.click();
  await expect(auditDetails).not.toHaveAttribute("open", "");
  await expect(
    firstAudit.getByText("Peristiwa Core", { exact: true }),
  ).not.toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-isolated-run.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Tata Kelola", exact: true })
    .click();
  const governanceAudit = page.locator(".audit-event").first();
  await governanceAudit.locator("summary").click();
  await expect(governanceAudit.locator(".audit-details")).toHaveAttribute(
    "open",
    "",
  );
  expect((await governanceAudit.locator(".status").boundingBox())?.height).toBe(
    24,
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Gunakan tema terang" }).click();
  await settleTheme(page);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect((await governanceAudit.locator(".status").boundingBox())?.height).toBe(
    24,
  );
  await governanceAudit.locator("summary").click();
  await expect(governanceAudit.locator(".audit-details")).not.toHaveAttribute(
    "open",
    "",
  );
  expect(errors).toEqual([]);
});

test("penolakan mutasi, koneksi terputus, dan pemulihan", async ({ page }) => {
  await page.goto("/factory");
  await expect(
    page.getByRole("heading", { name: "Agent Factory", exact: true }),
  ).toBeVisible();
  await page.route("**/api/projects/*/blueprints", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ message: "Akses ditolak oleh Core." }),
    }),
  );
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .first()
    .click();
  await page.getByLabel("Nama agent").fill("Pengujian penolakan");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Akses ditolak oleh Core.",
  );
  await page.getByRole("button", { name: "Tutup dialog" }).click();
  await page.route("**/api/workspace", (route) => route.abort());
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja belum terhubung" }),
  ).toBeVisible();
  await page.unroute("**/api/workspace");
  await page.getByRole("button", { name: "Coba sambungkan kembali" }).click();
  await expect(
    page.getByRole("heading", { name: "Agent Factory", exact: true }),
  ).toBeVisible();
});

test("keyboard: dialog terperangkap fokus dan Escape, sidebar collapsible", async ({
  page,
}) => {
  await page.goto("/factory");
  const logo = page.getByRole("img", { name: "Logo ARYN" });
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("Nama agent")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Ciutkan sidebar" }).click();
  await expect(page.locator(".app")).toHaveClass(/sidebar-collapsed/);
  await expect(logo).toBeVisible();
  const collapsedLogo = await logo.boundingBox();
  const collapsedSidebar = await page.locator(".sidebar").boundingBox();
  expect(collapsedLogo!.x).toBeGreaterThanOrEqual(collapsedSidebar!.x);
  expect(collapsedLogo!.x + collapsedLogo!.width).toBeLessThanOrEqual(
    collapsedSidebar!.x + collapsedSidebar!.width,
  );
  await page.reload();
  await expect(page.locator(".app")).toHaveClass(/sidebar-collapsed/);
  await page.getByRole("button", { name: "Perluas sidebar" }).click();
});

test("kegagalan sesi lokal dan penolakan izin baca memiliki pesan yang tepat", async ({
  page,
}) => {
  await page.route("**/api/session", (route) => route.abort());
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ruang kerja belum terhubung" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "Koneksi ke API terputus.",
  );
  await page.unroute("**/api/session");
  await page.getByRole("button", { name: "Coba sambungkan kembali" }).click();
  await expect(
    page.getByRole("heading", { name: "Ruang kerja agent Anda." }),
  ).toBeVisible();
  await page.route("**/api/projects/*/snapshot", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ message: "Keanggotaan proyek tidak aktif." }),
    }),
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Akses proyek dibatasi" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "Keanggotaan proyek tidak aktif.",
  );
  await expect(page.getByText("API terhubung", { exact: true })).toBeVisible();
});

test("validasi versi dan penolakan Core terlihat di dalam dialog", async ({
  page,
}) => {
  await page.goto("/factory");
  await page
    .getByRole("link", { name: /Research Agent — Tes Terisolasi/ })
    .click();
  await page.getByRole("button", { name: "Versi baru", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nomor versi").fill("invalid");
  await dialog
    .getByRole("button", { name: "Simpan versi", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Gunakan nomor versi baru",
  );
  await dialog.getByLabel("Nomor versi").fill("2.0.0");
  await page.route("**/api/projects/*/blueprints/*/versions", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ message: "Akses versi ditolak oleh Core." }),
    }),
  );
  await dialog
    .getByRole("button", { name: "Simpan versi", exact: true })
    .click();
  await expect(
    dialog
      .getByRole("alert")
      .filter({ hasText: "Akses versi ditolak oleh Core." }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});
