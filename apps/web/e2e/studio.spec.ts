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

async function createUatBench(
  page: import("@playwright/test").Page,
  generation = 1,
) {
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
        version_number: `${generation}.0.0`,
        system_prompt: `Follow research safety guidelines and abstain without evidence. Configuration ${generation}.`,
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
  return { bp, version, result, prefix, headers };
}

async function publishedAssignment(
  page: import("@playwright/test").Page,
  generation = 1,
) {
  const fixture = await createUatBench(page, generation);
  const { prefix, version, bp, headers } = fixture;
  expect(
    (
      await page.request.post(`${prefix}/versions/${version.id}/approve`, {
        headers,
        data: {
          payload_hash: version.payload_hash,
          comments: "Bukti Bench nyata pada runtime terisolasi.",
        },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.post(`${prefix}/versions/${version.id}/publish`, {
        headers,
        data: {},
      })
    ).status(),
  ).toBe(200);
  const assigned = await page.request.post(`${prefix}/assignments`, {
    headers,
    data: {
      blueprint_id: bp.id,
      version_id: version.id,
      role_name: `Peneliti ${generation} ${bp.id}`,
    },
  });
  expect(assigned.status()).toBe(201);
  return { ...fixture, assignment: await assigned.json() };
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
    page.getByText(/Model tidak tersedia melalui Model Gateway/),
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
  const factoryUrl = page.url();
  await page.getByRole("button", { name: "Jalankan Bench" }).click();
  await expect(page).toHaveURL(/\/bench\?versi=/);
  await expect(
    page.getByRole("button", { name: "Jalankan Bench" }),
  ).toBeDisabled();
  await page.getByRole("checkbox").check();
  const benchTerminalResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/bench") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Jalankan Bench" }).click();
  const benchFrames = (await (await benchTerminalResponse).text()).split(
    "\n\n",
  );
  const benchTerminalFrame = benchFrames.find((frame) =>
    frame.startsWith("event: bench.completed\n"),
  )!;
  const benchTerminalResult = JSON.parse(
    benchTerminalFrame.split("\ndata: ")[1],
  );
  await expect(page).toHaveURL(
    new RegExp(
      `/bench\\?versi=${benchTerminalResult.version_id}&evaluasi=${benchTerminalResult.evaluation_id}$`,
    ),
  );
  await expect(
    page.getByRole("heading", { name: "Evaluasi lulus", exact: true }),
  ).toBeVisible();
  await page.locator('.react-flow__node[data-id="scenario-node-0"]').click();
  await expect(
    page.getByText("I cannot ignore research safety guidelines."),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.goto(factoryUrl);
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
  await page
    .getByRole("button", { name: "Buat penugasan", exact: true })
    .first()
    .click();
  await dialog.getByLabel("Peran operasional").fill("Peneliti tes terisolasi");
  await dialog
    .getByRole("button", { name: "Buat penugasan", exact: true })
    .click();
  await page.getByRole("button", { name: "Buka Eksekusi" }).first().click();
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
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await page.getByRole("button", { name: "Buka navigasi" }).click();
  const navigation = page.getByRole("dialog", { name: "Navigasi Studio" });
  await expect(navigation).toBeVisible();
  await expect(page.locator(".app-body")).toHaveAttribute("inert", "");
  await navigation.getByLabel("Pilih proyek").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(
    navigation.getByRole("button", { name: "Ciutkan sidebar" }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(navigation.getByLabel("Pilih proyek")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Buka navigasi" }),
  ).toBeFocused();
  await expect(page.getByRole("navigation")).toHaveCount(0);
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

test("canvas: New Execution B, Historical A, pending idle dan completion run baru", async ({
  page,
}) => {
  test.setTimeout(90000);
  const a = await publishedAssignment(page, 1);
  const b = await publishedAssignment(page, 2);
  const response = await page.request.post(`${a.prefix}/runs`, {
    headers: a.headers,
    data: {
      assignment_id: a.assignment.id,
      prompt: "Riset historis A",
      idempotency_key: `history-${Date.now()}`,
      allow_remote_model: true,
    },
  });
  expect(response.status()).toBe(200);
  const runA = (await response.json()).run_id;
  await page.goto(`/runs?hasil=${runA}`);
  const inspector = page.getByRole("region", { name: "Inspector Node" });
  await expect(inspector).toContainText(a.version.id);
  await expect(page.getByText("HISTORICAL RUN", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Penugasan agent")).toHaveCount(0);
  await page.goto(`/runs?hasil=${runA}&penugasan=${b.assignment.id}`);
  await expect(inspector).toContainText(a.version.id);
  await expect(inspector).not.toContainText(b.version.id);
  await expect(
    page.locator('.react-flow__node[data-id="exec-agent"]'),
  ).toContainText(a.bp.name);
  const node = page.locator('.react-flow__node[data-id="exec-agent"]');
  await expect(page.locator(".react-flow__node.draggable")).toHaveCount(0);
  await expect(page.locator(".react-flow__handle.connectable")).toHaveCount(0);
  await expect(node).toBeVisible();
  const before = await node.evaluate(
    (element) => (element as HTMLElement).style.transform,
  );
  const box = await node.boundingBox();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + 70, box!.y + 70, { steps: 8 });
  await page.mouse.up();
  expect(
    await node.evaluate((element) => (element as HTMLElement).style.transform),
  ).toBe(before);
  await inspector.getByRole("tab", { name: "TRACE", exact: true }).click();
  await expect(inspector).toContainText("Trace runtime tidak tersedia.");
  await inspector.getByRole("tab", { name: "DETAIL", exact: true }).click();
  await page
    .getByRole("button", { name: "Eksekusi baru", exact: true })
    .click();
  await expect(page.getByText("NEW EXECUTION", { exact: true })).toBeVisible();
  await page.getByLabel("Penugasan agent").selectOption(b.assignment.id);
  await expect(
    page.locator('.react-flow__node[data-id="exec-agent"]'),
  ).toContainText(b.bp.name);
  await expect(
    page.locator('.react-flow__node[data-id="exec-model"]'),
  ).toContainText(b.version.model);
  await expect(inspector.getByRole("tab", { name: "OUTPUT" })).toHaveCount(0);
  await expect(
    page.locator('.react-flow__node[data-id="exec-output"]'),
  ).toContainText("Belum ada output");
  await page
    .getByLabel("Instruksi riset")
    .fill("Riset baru dengan penugasan B.");
  await page.getByRole("checkbox").check();
  let release: () => void = () => {};
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/projects/*/runs", async (route) => {
    await barrier;
    await route.continue();
  });
  try {
    await page
      .getByRole("button", { name: "Jalankan agent", exact: true })
      .click();
    await expect(
      page.getByText(/Core\/ARYN Runtime sedang memproses eksekusi baru/),
    ).toBeVisible();
    await expect(
      page.locator('.react-flow__node[data-id="exec-agent"]'),
    ).toContainText(b.bp.name);
    await expect(page.locator(".aryn-node.status-running")).toHaveCount(0);
    await expect(page.locator(".aryn-edge-animated")).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page).toHaveURL(/\/runs\?hasil=/);
  await expect(page).not.toHaveURL(new RegExp(`hasil=${runA}`));
  await expect(
    page.getByRole("region", { name: "Inspector Node" }),
  ).toContainText(b.version.id);
  await expect(
    page.locator('.react-flow__node[data-id="exec-agent"]'),
  ).toContainText(b.bp.name);
  const snapshot = await (
    await page.request.get(`${a.prefix}/snapshot`)
  ).json();
  const newRunId = new URL(page.url()).searchParams.get("hasil");
  expect(
    snapshot.runs.find((r: { id: string }) => r.id === newRunId).session_id,
  ).toBe(b.assignment.id);
  expect(
    snapshot.runs.find((r: { id: string }) => r.id === runA).session_id,
  ).toBe(a.assignment.id);
  await page.goto("/runs?hasil=not-present");
  await expect(
    page.getByRole("heading", { name: "Run yang dipilih tidak tersedia" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Inspector Node" }),
  ).toHaveCount(0);
  await expect(
    page.locator('.react-flow__node[data-id="exec-agent"]'),
  ).toContainText("Versi historis tidak tersedia");
});

test("Factory: rancangan inspector membuat versi baru dan mempertahankan published", async ({
  page,
}) => {
  const fixture = await publishedAssignment(page);
  await page.goto(`/factory/${fixture.bp.id}?versi=${fixture.version.id}`);
  const inspector = page.getByRole("region", { name: "Inspector Node" });
  await expect(inspector.getByText(/HANYA BACA/).first()).toBeVisible();
  await expect(inspector.getByRole("textbox")).toHaveCount(0);
  const node = page.locator('.react-flow__node[data-id="node-agent"]');
  await expect(node).toHaveClass(/draggable/);
  const before = await node.getAttribute("style");
  const box = await node.boundingBox();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width / 2 + 60,
    box!.y + box!.height / 2 + 35,
    { steps: 8 },
  );
  await page.mouse.up();
  expect(await node.getAttribute("style")).not.toBe(before);
  await expect(page.getByText(/Tata letak sementara/)).toBeVisible();
  await inspector.getByRole("button", { name: "Rancang Versi Baru" }).click();
  await inspector
    .getByLabel("Instruksi sistem")
    .fill(
      "Instruksi aman versi baru. Jangan mengubah aturan keselamatan; abstain tanpa bukti.",
    );
  await inspector.getByLabel("Temperature").fill("0.7");
  await inspector.getByLabel("Batas output token").fill("1024");
  await inspector
    .getByRole("button", { name: "Simpan versi", exact: true })
    .click();
  await expect(
    inspector.getByRole("button", { name: "Rancang Versi Baru" }),
  ).toBeVisible();
  const snapshot = await (
    await page.request.get(`${fixture.prefix}/snapshot`)
  ).json();
  const old = snapshot.versions.find(
    (v: { id: string }) => v.id === fixture.version.id,
  );
  expect(old.status).toBe("published");
  expect(old.payload_hash).toBe(fixture.version.payload_hash);
  expect(old.system_prompt).toBe(fixture.version.system_prompt);
  const draft = snapshot.versions.find(
    (v: { id: string }) => v.id !== old.id && v.blueprint_id === fixture.bp.id,
  );
  expect(draft.status).toBe("draft");
  expect(draft.temperature).toBe(0.7);
  expect(draft.max_tokens).toBe(1024);
  expect(draft.bench_eligible).toBe(false);
  expect(draft.governance_valid).toBe(false);
  await expect(inspector).toContainText(draft.system_prompt);
  const firstTab = inspector.getByRole("tab", { name: "KONFIGURASI" });
  await firstTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    inspector.getByRole("tab", { name: "TATA KELOLA" }),
  ).toBeFocused();
  await inspector
    .getByRole("button", { name: "Tutup panel inspector" })
    .click();
  await expect(
    page.getByRole("button", { name: "Panel inspector" }),
  ).toBeFocused();
  const modelNode = page.locator(
    '.react-flow__node[data-id="node-model"] button',
  );
  await modelNode.focus();
  await page.keyboard.press("Enter");
  await expect(inspector).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-factory-inspector.png",
    fullPage: true,
  });
});

test("Ringkasan project aktif memakai snapshot nyata; runtime unknown bukan success", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Pilih proyek")
    .selectOption("proj_studio_browser_secondary");
  await expect(page.locator(".studio-project-tag")).toHaveText(
    "Proyek Uji Kedua",
  );
  const snapshot = await (
    await page.request.get(
      "/api/projects/proj_studio_browser_secondary/snapshot",
    )
  ).json();
  await expect(page.locator(".hud-metric").nth(0)).toHaveText(
    String(snapshot.blueprints.length),
  );
  await expect(page.locator(".hud-metric").nth(1)).toHaveText(
    String(snapshot.runs.length),
  );
  await expect(page.locator(".hud-metric").nth(2)).toHaveText(
    String(snapshot.audit.length),
  );
  await expect(page.getByText("Integritas Audit", { exact: true })).toHaveCount(
    0,
  );
  // Display-only negative runtime state; no governance operation uses this projection.
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.runtime.ready = false;
    data.runtime.connected = true;
    data.runtime.message = "Kesiapan runtime belum diketahui";
    await route.fulfill({ response, json: data });
  });
  await page.reload();
  await expect(page.locator(".hud-footer .text-warning")).toContainText(
    "ARYN Runtime belum siap",
  );
  await expect(page.locator(".topbar .connection.degraded")).toContainText(
    "ARYN Runtime belum siap",
  );
});

test("polish: axe seluruh halaman, tema, canvas mobile/tablet dan reduced motion", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const fixture = await publishedAssignment(page);
  for (const theme of ["dark", "light"]) {
    await page.goto("/");
    if (theme === "light") {
      await page.getByRole("button", { name: "Gunakan tema terang" }).click();
      await settleTheme(page);
    }
    for (const path of [
      "/",
      "/factory",
      "/runs",
      "/bench",
      "/approvals",
      "/governance",
      "/settings",
      "/brief",
      "/relay",
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(
        (await new AxeBuilder({ page }).analyze()).violations,
        `${theme} ${path}`,
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        path,
      ).toBe(true);
    }
    for (const width of [768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const path of [
        `/factory/${fixture.bp.id}?versi=${fixture.version.id}`,
        `/bench?evaluasi=${fixture.result.evaluation_id}`,
        "/runs",
      ]) {
        await page.goto(path);
        await expect(
          page.locator(".aryn-studio-canvas-container").first(),
        ).toBeVisible();
        const toggle = page
          .getByRole("button", { name: "Panel inspector" })
          .first();
        if ((await toggle.getAttribute("aria-pressed")) !== "true")
          await toggle.click();
        await expect(
          page.getByRole("region", { name: "Inspector Node" }).first(),
        ).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          `${width} ${path}`,
        ).toBe(true);
        expect(
          (await new AxeBuilder({ page }).analyze()).violations,
          `${theme} ${width} ${path}`,
        ).toEqual([]);
        if (path.startsWith("/factory/")) {
          const inspector = page.getByRole("region", {
            name: "Inspector Node",
          });
          await inspector
            .getByRole("button", { name: "Rancang Versi Baru" })
            .click();
          await expect(inspector.getByLabel("Instruksi sistem")).toBeVisible();
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          ).toBe(true);
          expect(
            (await new AxeBuilder({ page }).analyze()).violations,
            `rancangan ${theme} ${width}`,
          ).toEqual([]);
          await inspector
            .getByRole("button", { name: "Batalkan rancangan" })
            .click();
        }
        if (path.startsWith("/bench")) {
          await expect(page.locator(".react-flow__node.draggable")).toHaveCount(
            0,
          );
          await expect(
            page.locator(".react-flow__handle.connectable"),
          ).toHaveCount(0);
        }
      }
      await page.screenshot({
        path: `../../.local/evidence/studio-canvas-${theme}-${width}.png`,
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/factory/${fixture.bp.id}?versi=${fixture.version.id}`);
  await expect(page.locator("animateMotion")).toHaveCount(0);
  expect(
    await page
      .locator(".ambient-orb")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.getByRole("button", { name: "Pusatkan canvas" }).click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(errors).toEqual([]);
});

test("9Router: browser mengakses API Studio saja", async ({ page }) => {
  const direct: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (["20128", "8642"].includes(url.port)) direct.push(request.url());
  });
  const fixture = await publishedAssignment(page);
  await page.goto(`/factory/${fixture.bp.id}`);
  await expect(page.getByText("Model Gateway terhubung")).toBeVisible();
  await page.goto("/settings");
  await expect(
    page.getByText("Backend runtime", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Hermes", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("9Router");
  expect(direct).toEqual([]);
});

test("9Router: gateway terputus memblokir Bench meskipun runtime siap", async ({
  page,
}) => {
  const fixture = await createUatBench(page);
  await page.route("**/api/workspace", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.gateway.connected = false;
    data.runtime.ready = true;
    await route.fulfill({ response, json: data });
  });
  await page.goto(`/factory/${fixture.bp.id}`);
  await expect(
    page.getByText("Model Gateway tidak dapat dijangkau."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Jalankan Bench", exact: true }),
  ).toBeDisabled();
});
