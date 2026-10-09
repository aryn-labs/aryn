import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

async function setup(page: Page) {
  await page.goto("/relay");
  await expect(
    page.getByRole("heading", { name: "Relay", exact: true }),
  ).toBeVisible();
  const csrf = (
    await (
      await page.request.post("/api/session", {
        data: {},
        headers: { Origin: "http://127.0.0.1:8711" },
      })
    ).json()
  ).csrf;
  const headers = { Origin: "http://127.0.0.1:8711", "X-CSRF-Token": csrf },
    prefix = "/api/projects/proj_studio_research";
  async function post(path: string, data: unknown = {}) {
    const response = await page.request.post(prefix + path, { data, headers });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  async function get(path: string) {
    const response = await page.request.get(prefix + path);
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  return { prefix, post, get, headers };
}
async function demo(page: Page, blocking = false) {
  const api = await setup(page);
  const created = await api.post("/relay/demo-fixtures", {
    name: "Isolated browser worker",
  });
  await api.post(`/relay/demo-fixtures/${created.fixture.id}`, {
    expected_revision: 1,
    running: false,
    blocking_fault: blocking,
  });
  const incident = await api.post("/relay/signals", {
    target_id: created.fixture.id,
    dedup_key: `${created.fixture.id}-stopped`,
    severity: "high",
  });
  return { ...api, incident };
}
async function proposed(page: Page) {
  const api = await demo(page);
  const investigation = await api.post(
    `/relay/${api.incident.id}/investigate`,
    { expected_revision: 1 },
  );
  const incident = await api.post(`/relay/${api.incident.id}/proposals`, {
    expected_revision: investigation.revision,
    target_id: investigation.target_id,
    target_revision: investigation.fixture.revision,
    bundle_id: investigation.bundle_id,
    reason: "Review exact demo snapshot and independent verification.",
  });
  return { ...api, incident };
}
async function closed(page: Page) {
  const api = await proposed(page),
    id = api.incident.id,
    proposal = api.incident.proposal;
  await api.post(`/relay/${id}/approve`, {
    payload_hash: proposal.payload_hash,
    reason: "Explicit human review",
  });
  const recovered = await api.post(`/relay/${id}/execute`, {
    proposal_id: proposal.id,
    payload_hash: proposal.payload_hash,
    idempotency_key: "browser-recovery",
  });
  const incident = await api.post(`/relay/${id}/close`, {
    expected_revision: recovered.revision,
  });
  const replay = await api.post(
    `/bench/capsules/${incident.capsule_id}/replay`,
  );
  return { ...api, incident, replay };
}

test("real demo UI → contradiction → exact Core approval → verified capsule → memory Bench", async ({
  page,
}) => {
  const api = await setup(page);
  await page.getByLabel("Nama fixture demo").fill("Keyboard recovery worker");
  await page.getByRole("button", { name: "Buat fixture healthy" }).click();
  await expect(page.getByLabel("Target fixture demo")).not.toHaveValue("");
  await page.getByRole("button", { name: "Hentikan fixture demo" }).click();
  await expect(
    page.getByRole("button", { name: "Terima signal demo" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Terima signal demo" }).click();
  await expect(page).toHaveURL(/\/relay\/incident_/);
  const id = page.url().split("/").at(-1)!;
  await page.getByRole("button", { name: "Investigasi read-only" }).click();
  await expect(page.getByText("CONFLICTING · Coverage 2/2")).toBeVisible();
  await page.getByRole("link", { name: /Buka EvidenceBundle/ }).click();
  await expect(
    page.getByRole("heading", { name: "Counterevidence", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Evidence pendukung", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Periksa provenance sumber" })
    .first()
    .click();
  await expect(page.getByText(/Quality: disposable_demo/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download evidence JSON" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^aryn-bundle_.+\.json$/,
  );
  await page.goto(`/relay/${id}`);
  await page
    .getByLabel("Alasan proposal")
    .fill("Restart isolated target after reviewing conflicting observations.");
  await page
    .getByRole("button", { name: "Buat proposal exact target" })
    .click();
  await expect(
    page.getByRole("button", { name: "Jalankan recovery demo" }),
  ).toBeDisabled();
  const current = await api.get(`/relay/${id}`);
  await expect(page.getByTestId("proposal-hash")).toHaveText(
    current.proposal.payload_hash,
  );
  await page
    .getByLabel("Alasan review manusia")
    .fill(
      "Reviewed exact hash, target revision and independent health contract.",
    );
  await page.getByRole("button", { name: "Setujui hash proposal" }).click();
  await expect(page.getByText(/Approval Core terverifikasi:/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Jalankan recovery demo" }),
  ).toBeDisabled();
  await page
    .getByLabel(
      "Saya mengonfirmasi target demo dan hash proposal yang ditampilkan.",
    )
    .check();
  await page.getByRole("button", { name: "Jalankan recovery demo" }).click();
  await expect(
    page.getByText(/RECOVERED · health contract terpenuhi/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Tutup incident terverifikasi" })
    .click();
  await page.getByRole("link", { name: "Replay aman di Bench" }).click();
  await expect(
    page.getByRole("heading", { name: "Capsule terverifikasi" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Jalankan replay memory" }).click();
  await expect(page.getByText(/Live recovery write calls: 0/)).toBeVisible();
  await expect(page.getByText(/tidak mengizinkan promotion/)).toBeVisible();
  const final = await api.get(`/relay/${id}`);
  expect(final.status).toBe("CLOSED");
  expect(final.fixture.revision).toBe(3);
  expect(final.verification.recovered).toBe(true);
  await expect(
    page.getByRole("link", { name: "Incident health evidence" }),
  ).toBeVisible();
});

test("failed health, abstention, empty, forbidden and offline states retain their boundaries", async ({
  page,
}) => {
  const api = await demo(page, true),
    id = api.incident.id;
  let incident = await api.post(`/relay/${id}/investigate`, {
    expected_revision: 1,
    source_ids: [],
  });
  await page.goto(`/relay/${id}`);
  await expect(page.getByText(/Abstain: required fresh/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Buat proposal exact target" }),
  ).toBeDisabled();
  incident = await api.post(`/relay/${id}/investigate`, {
    expected_revision: incident.revision,
  });
  incident = await api.post(`/relay/${id}/proposals`, {
    expected_revision: incident.revision,
    target_id: incident.target_id,
    target_revision: incident.fixture.revision,
    bundle_id: incident.bundle_id,
    reason: "Blocking health contract variant",
  });
  await api.post(`/relay/${id}/approve`, {
    payload_hash: incident.proposal.payload_hash,
    reason: "Review failure variant",
  });
  incident = await api.post(`/relay/${id}/execute`, {
    proposal_id: incident.proposal.id,
    payload_hash: incident.proposal.payload_hash,
    idempotency_key: "health-failed",
  });
  expect(incident.status).toBe("DEGRADED");
  await page.reload();
  await expect(
    page.getByText(/DEGRADED · health contract gagal/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Tutup incident terverifikasi" }),
  ).toHaveCount(0);
  await page.route(`**${api.prefix}/relay/${id}`, (r) =>
    r.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ message: "Akses proyek dicabut." }),
    }),
  );
  await page.getByRole("button", { name: "Perbarui koneksi dan data" }).click();
  await expect(
    page.getByRole("heading", { name: "Akses evidence dibatasi" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Investigasi read-only" }),
  ).toHaveCount(0);
  await page.unroute(`**${api.prefix}/relay/${id}`);
  await page.route(`**${api.prefix}/brief**`, (r) => r.abort());
  await page.goto("/brief");
  await expect(page.getByRole("alert")).toContainText(
    "Koneksi ke API terputus",
  );
});

test("scoped document search, abstention and safe text rendering", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/brief");
  await expect(page.getByText("Belum ada evidence bundle")).toBeVisible();
  await page.getByLabel("Judul dokumen").fill("Disposable document");
  await page
    .getByLabel("Isi dokumen demo")
    .fill("Verified literal marker <script>window.compromised=true</script>");
  await page
    .getByRole("button", { name: "Simpan & kumpulkan dokumen" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: /Disposable document/ }),
  ).toBeVisible();
  await page.getByLabel("Judul bundle").fill("Literal text investigation");
  await page
    .getByLabel("Pertanyaan hipotesis")
    .fill("Does the literal marker exist?");
  await page.getByLabel("Teks literal", { exact: true }).fill("marker");
  await page.getByRole("checkbox", { name: /Disposable document/ }).check();
  await page.getByRole("button", { name: "Evaluasi & simpan bundle" }).click();
  await expect(
    page.getByText("SUPPORTED", { exact: true }).first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { compromised?: boolean }).compromised,
    ),
  ).toBeUndefined();
  await page.getByRole("link", { name: "Seluruh bundle" }).click();
  await page.getByLabel("Cari bundle").fill("no-match");
  await expect(page.getByText("Belum ada evidence bundle")).toBeVisible();
});

test("project switch removes selected incident, evidence and capsule authority", async ({
  page,
}) => {
  const data = await closed(page);
  await page.goto(`/relay/${data.incident.id}`);
  await expect(
    page.getByText(data.incident.capsule_id, { exact: false }).first(),
  ).toBeVisible();
  await page
    .getByLabel("Pilih proyek")
    .selectOption("proj_studio_browser_secondary");
  await expect(page).toHaveURL(/\/$/);
  await page.goto(`/relay/${data.incident.id}`);
  await expect(
    page.getByRole("heading", {
      name: "Sumber daya tidak tersedia",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Replay aman di Bench" }),
  ).toHaveCount(0);
  await page.goto(`/brief/${data.incident.bundle_id}`);
  await expect(
    page.getByRole("heading", {
      name: "Sumber daya tidak tersedia",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download evidence JSON" }),
  ).toHaveCount(0);
  await page.goto(`/bench/replays?capsule=${data.incident.capsule_id}`);
  await expect(
    page.getByRole("heading", {
      name: "Sumber daya tidak tersedia",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Jalankan replay memory" }),
  ).toHaveCount(0);
});

for (const width of [390, 768, 1440]) {
  for (const theme of ["dark", "light"]) {
    test(`actual Brief, proposal and replay accessible at ${width} ${theme}`, async ({
      page,
    }, info) => {
      test.setTimeout(90000);
      await page.setViewportSize({ width, height: 1000 });
      await page.addInitScript(
        (t) => localStorage.setItem("aryn-theme", t),
        theme,
      );
      const data = await closed(page);
      const review = await proposed(page);
      const paths = [
        `/brief/${data.incident.bundle_id}`,
        `/relay/${review.incident.id}`,
        `/bench/replays/${data.replay.id}`,
      ];
      for (const [i, path] of paths.entries()) {
        await page.goto(path);
        await expect(page.locator("main h1")).toBeVisible();
        await expect(page.locator("main .busy")).toHaveCount(0);
        expect(
          (
            await new AxeBuilder({ page })
              .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
              .analyze()
          ).violations,
        ).toEqual([]);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await page.keyboard.press("Tab");
        await expect(page.locator(":focus")).toBeVisible();
        await page.screenshot({
          path: info.outputPath(
            `${["brief", "relay-proposal", "bench-replay"][i]}-${width}-${theme}.png`,
          ),
          fullPage: true,
        });
      }
    });
  }
}

test("bounded evidence API and usable incident navigation performance", async ({
  page,
}, info) => {
  test.setTimeout(90000);
  const data = await proposed(page);
  const samples: number[] = [],
    navigation: number[] = [];
  for (let i = 0; i < 20; i++) {
    const start = performance.now();
    await data.get(`/brief/${data.incident.bundle_id}`);
    samples.push(performance.now() - start);
  }
  for (let i = 0; i < 10; i++) {
    const start = performance.now();
    await page.goto(`/relay/${data.incident.id}`);
    await expect(page.getByTestId("proposal-hash")).toHaveText(
      data.incident.proposal.payload_hash,
    );
    navigation.push(performance.now() - start);
  }
  const p95 = (v: number[]) =>
    [...v].sort((a, b) => a - b)[Math.ceil(v.length * 0.95) - 1];
  expect(p95(samples)).toBeLessThan(2000);
  expect(p95(navigation)).toBeLessThan(3000);
  writeFileSync(
    info.outputPath("intelligence-browser-performance.json"),
    JSON.stringify(
      {
        source_sha: execFileSync("git", ["rev-parse", "HEAD"], {
          encoding: "utf8",
        }).trim(),
        source_modified: !!execFileSync("git", ["status", "--porcelain"], {
          encoding: "utf8",
        }).trim(),
        runtime: "isolated test only",
        dataset:
          "one actual incident, two distinct observations, one exact proposal",
        api_samples_ms: samples,
        api_p95_ms: p95(samples),
        navigation_samples_ms: navigation,
        navigation_p95_ms: p95(navigation),
      },
      null,
      2,
    ),
  );
});
