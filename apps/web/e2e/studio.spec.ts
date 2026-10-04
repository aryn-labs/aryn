import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

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
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-dark.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Gunakan tema terang" }).click();
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
  await page.getByRole("button", { name: "Buka navigasi" }).click();
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

test("vertical slice HTTP nyata ke Core dengan runtime pengujian terisolasi", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/factory");
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
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../.local/evidence/studio-isolated-run.png",
    fullPage: true,
  });
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
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("Nama agent")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Ciutkan sidebar" }).click();
  await expect(page.locator(".app")).toHaveClass(/sidebar-collapsed/);
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
