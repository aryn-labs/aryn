import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import axe from "axe-core";
import { documentGraph } from "../src/lib/workflow-types";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

async function auditDocument(
  target: import("@playwright/test").Page | import("@playwright/test").Frame,
) {
  await target.evaluate(axe.source);
  return (await target.evaluate(
    "axe.run(document, { iframes: false, runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } })",
  )) as { violations: unknown[] };
}

async function auditPreview(page: import("@playwright/test").Page) {
  const frame = page.frames().find((item) => item.parentFrame());
  expect(frame).toBeTruthy();
  // Chromium blocks script timers inside sandbox="", including axe's own
  // asynchronous checks. Audit the exact serialized preview DOM in a separate
  // test page. Its CSP is preserved, all network is blocked, and the product
  // frame keeps its opaque origin and disabled scripts throughout this check.
  const mirror = await page.context().newPage();
  try {
    await mirror.setViewportSize(page.viewportSize()!);
    await mirror.route("**/*", (route) => route.abort());
    await mirror.setContent(await frame!.content());
    return await auditDocument(mirror);
  } finally {
    await mirror.close();
    await page.bringToFront();
  }
}

async function agents(page: import("@playwright/test").Page) {
  await page.goto("/workflows");
  await expect(
    page.getByRole("heading", { name: "Workflows", exact: true }),
  ).toBeVisible();
  const prefix = "/api/projects/proj_studio_research";
  const csrf = (
    await (
      await page.request.post("/api/session", {
        data: {},
        headers: { Origin: "http://127.0.0.1:8711" },
      })
    ).json()
  ).csrf;
  const headers = { Origin: "http://127.0.0.1:8711", "X-CSRF-Token": csrf };
  async function post(path: string, data: unknown) {
    const response = await page.request.post(prefix + path, { data, headers });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  }
  const assignments = [];
  for (const role of ["Research", "Content"]) {
    const bp = await post("/blueprints", {
      name: role,
      slug: role.toLowerCase(),
    });
    const version = await post(`/blueprints/${bp.id}/versions`, {
      version_number: "1.0.0",
      system_prompt:
        "Follow research safety guidelines and abstain without evidence.",
      model: "test/model-a",
      max_tokens: 512,
      tool_grants: [],
    });
    expect(
      (
        await post(`/versions/${version.id}/bench`, {
          allow_remote_model: true,
        })
      ).passed,
    ).toBe(true);
    await post(`/versions/${version.id}/approve`, {
      payload_hash: version.payload_hash,
      comments: "Isolated test evidence",
    });
    await post(`/versions/${version.id}/publish`, {});
    assignments.push(
      await post("/assignments", {
        blueprint_id: bp.id,
        version_id: version.id,
        role_name: role,
      }),
    );
  }
  return { prefix, headers, post, assignments };
}

test("canvas and keyboard draft, server validation, three Core tasks and exact review", async ({
  page,
}) => {
  test.setTimeout(90000);
  const setup = await agents(page);
  await page.getByRole("link", { name: "Buat workflow" }).click();
  await page.getByLabel("Nama workflow").fill("Research document workflow");
  await page
    .getByLabel("Research assignment")
    .selectOption(setup.assignments[0].id);
  await page
    .getByLabel("Content assignment")
    .selectOption(setup.assignments[1].id);
  await page
    .getByRole("button", { name: "Gunakan Research → Content → Website" })
    .click();
  await page.getByLabel("Node terpilih").selectOption("research");
  await page.getByLabel("Label node").fill("Research exact pin");
  await page.getByRole("button", { name: "Simpan draft", exact: true }).click();
  await expect(page).toHaveURL(/workflows\/workflow_.+\/builder/);
  const id = page.url().split("/").at(-2)!;
  const before = await (
    await page.request.get(`${setup.prefix}/workflows/${id}`)
  ).json();
  expect(before.graph.nodes[1].label).toBe("Research exact pin");
  // Real canvas pointer drag changes persisted position independently of graph hash.
  const canvasNode = page.locator('.react-flow__node[data-id="research"]');
  await canvasNode.scrollIntoViewIfNeeded();
  const box = await canvasNode.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box!.x + 40, box!.y + 20);
  await page.mouse.down();
  await page.mouse.move(box!.x + 75, box!.y + 45, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByText(/Perubahan belum disimpan/)).toBeVisible();
  await page.getByRole("button", { name: "Simpan draft", exact: true }).click();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`${setup.prefix}/workflows/${id}`)
          ).json()
        ).revision,
    )
    .toBe(2);
  await expect(
    page.getByText("Draft tersimpan.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Validasi server", exact: true })
    .click();
  await expect(
    page.getByText("Validator Core menerima graph.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Bekukan versi", exact: true })
    .click();
  await expect(
    page.getByText("Versi immutable tersimpan.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Node terpilih")).toBeVisible();
  const after = await (
    await page.request.get(`${setup.prefix}/workflows/${id}`)
  ).json();
  expect(after.positions.some((p: { id: string }) => p.id === "research")).toBe(
    true,
  );
  expect(after.graph).toEqual(before.graph);
  await page.getByRole("link", { name: "Detail & eksekusi" }).click();
  const versions = await (
    await page.request.get(`${setup.prefix}/workflows/${id}/versions`)
  ).json();
  await page.getByLabel("Versi workflow").selectOption(versions.items[0].id);
  await page
    .getByLabel("Input workflow")
    .fill("Create an evidence grounded static document");
  await page
    .getByRole("checkbox", {
      name: "Saya menyetujui penggunaan model untuk workflow ini.",
    })
    .check();
  let loseResponse = true;
  await page.route("**/workflows/*/runs", async (route) => {
    if (route.request().method() === "POST" && loseResponse) {
      loseResponse = false;
      await route.fetch(); // Actual Core execution commits before transport loss.
      await route.abort("failed");
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "Jalankan workflow", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Koneksi");
  await page
    .getByRole("button", { name: "Jalankan workflow", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Persisted execution timeline" }),
  ).toBeVisible();
  expect(
    (
      await (
        await page.request.get(`${setup.prefix}/workflows/${id}/runs`)
      ).json()
    ).items,
  ).toHaveLength(1);
  await expect(
    page.getByText("waiting_review", { exact: true }).first(),
  ).toBeVisible();
  expect(
    await page.getByRole("link", { name: "Core Console", exact: true }).count(),
  ).toBe(2);
  const timeline = page.url();
  await page
    .getByRole("link", { name: "Core Console", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("link", { name: "Workflow · research" }),
  ).toHaveAttribute(
    "href",
    new URL(timeline).pathname + new URL(timeline).search,
  );
  await page.getByRole("link", { name: "Workflow · research" }).click();
  await page.goto("/operations");
  await expect(
    page.getByRole("link", { name: "Workflow timeline" }).first(),
  ).toHaveAttribute(
    "href",
    new URL(timeline).pathname + new URL(timeline).search,
  );
  await page.goto(timeline);
  await page.getByRole("link", { name: "Buka hasil & review" }).click();
  await expect(
    page.getByRole("heading", { name: "Inert preview" }),
  ).toBeVisible();
  await expect(page.locator("iframe")).toHaveAttribute("sandbox", "");
  await expect(
    page
      .frameLocator("iframe")
      .getByRole("heading", { name: "Reviewed document" }),
  ).toBeVisible();
  await page
    .getByLabel("Alasan review")
    .fill("Checked exact hash and downstream lineage");
  await page.getByRole("button", { name: "Terima deliverable" }).click();
  await expect(page.getByText(/accepted · studio_local_owner/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download artifact" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^artifact_[a-f0-9]+\.html$/,
  );
});

for (const width of [390, 768, 1440])
  test(`workflow and artifact both themes, keyboard and axe ${width}`, async ({
    page,
  }, info) => {
    test.setTimeout(90000);
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const setup = await agents(page);
    const saved = await setup.post("/workflows", {
      name: "Accessible document workflow",
      expected_revision: 0,
      graph: documentGraph(setup.assignments[0], setup.assignments[1]),
      positions: [],
    });
    const version = await setup.post(`/workflows/${saved.id}/versions`, {
      expected_revision: 1,
    });
    const run = await setup.post(`/workflows/${saved.id}/runs`, {
      version_id: version.id,
      input: "Research an inert document",
      idempotency_key: "responsive",
      allow_remote_model: true,
    });
    expect(run.status).toBe("waiting_review");
    for (const theme of ["dark", "light"]) {
      await page.goto(`/workflows/${saved.id}/builder`);
      await expect(page.getByLabel("Nama workflow")).toHaveValue(
        "Accessible document workflow",
      );
      if (theme === "light")
        await page.getByRole("button", { name: "Gunakan tema terang" }).click();
      for (const path of [
        `/workflows/${saved.id}/builder`,
        `/workflows/${saved.id}?run=${run.id}`,
        `/outputs/${run.artifact_id}`,
      ]) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        if (path.includes("builder"))
          await expect(
            page.getByRole("heading", { name: "Editor graph dengan keyboard" }),
          ).toBeVisible();
        if (path.includes("outputs")) {
          await page.locator("iframe").scrollIntoViewIfNeeded();
          await expect(
            page
              .frameLocator("iframe")
              .getByRole("heading", { name: "Reviewed document" }),
          ).toBeVisible();
        }
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          path,
        ).toBe(true);
        // AxeBuilder's runPartial frame discovery performs a cross-origin
        // handshake even with iframes:false. Audit each actual document directly
        // using axe.run; all rules remain enabled and sandbox remains unchanged.
        const accessibility = path.includes("outputs")
          ? await auditDocument(page)
          : await new AxeBuilder({ page })
              .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
              .analyze();
        expect(accessibility.violations, `${width} ${theme} ${path}`).toEqual(
          [],
        );
        if (path.includes("outputs")) {
          const result = await auditPreview(page);
          expect(
            result.violations,
            "opaque preview document accessibility",
          ).toEqual([]);
          await expect(page.locator("iframe")).toHaveAttribute("sandbox", "");
          await page.locator("iframe").screenshot({
            path: info.outputPath(`workflow-preview-${width}-${theme}.png`),
          });
        }
        await page.evaluate(() => {
          if (document.activeElement instanceof HTMLElement)
            document.activeElement.blur();
          window.scrollTo(0, 0);
        });
        await page.screenshot({
          path: info.outputPath(
            `${path.includes("builder") ? "workflow-builder" : path.includes("outputs") ? "workflow-output" : "workflow-timeline"}-${width}-${theme}.png`,
          ),
          fullPage: true,
        });
      }
    }
    await page.goto(`/workflows/${saved.id}/builder`);
    await page.getByLabel("Node terpilih").focus();
    await page.keyboard.press("c");
    await page.keyboard.press("Enter");
    await page.getByLabel("Label node").fill("Keyboard content task");
    await page
      .getByRole("button", { name: "Simpan draft", exact: true })
      .click();
    await expect(
      page.getByText("Draft tersimpan.", { exact: true }),
    ).toBeVisible();
  });

test("workflow conflicts preserve draft, validator issues and no cached unauthorized outputs", async ({
  page,
}) => {
  const setup = await agents(page);
  const saved = await setup.post("/workflows", {
    name: "Conflict workflow",
    expected_revision: 0,
    graph: documentGraph(setup.assignments[0], setup.assignments[1]),
    positions: [],
  });
  await page.goto(`/workflows/${saved.id}/builder`);
  await expect(page.getByLabel("Nama workflow")).toHaveValue(
    "Conflict workflow",
  );
  await setup.post(`/workflows/${saved.id}`, {
    name: "Concurrent saved name",
    graph: saved.graph,
    positions: [],
    expected_revision: 1,
  });
  await page.getByLabel("Nama workflow").fill("Unsaved conflict name");
  const refetched = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/workflows/${saved.id}`) &&
      response.request().method() === "GET",
  );
  await page.getByRole("button", { name: "Perbarui koneksi dan data" }).click();
  await refetched;
  await expect(page.getByLabel("Nama workflow")).toHaveValue(
    "Unsaved conflict name",
  );
  await page.getByRole("button", { name: "Simpan draft", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Input lokal tetap tersedia",
  );
  await expect(page.getByLabel("Nama workflow")).toHaveValue(
    "Unsaved conflict name",
  );
  page.once("dialog", (d) => d.accept());
  await page.getByRole("link", { name: "Detail & eksekusi" }).click();
  await page.getByRole("link", { name: "Edit graph" }).click();
  await page
    .getByRole("button", { name: "Hapus edge edge_0", exact: true })
    .click();
  await page.getByRole("button", { name: "Simpan draft", exact: true }).click();
  await expect(
    page.getByText("Draft tersimpan.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Validasi server", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("bounded_ports_required");
  await page.route("**/api/projects/*/outputs/missing", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ message: "Akses ditolak." }),
    }),
  );
  await page.goto("/outputs/missing");
  await expect(page.getByRole("alert")).toContainText("Akses ditolak");
  await expect(page.locator("iframe")).toHaveCount(0);
});

test("workflow bounded API and usable navigation performance", async ({
  page,
}, info) => {
  const setup = await agents(page);
  const saved = await setup.post("/workflows", {
    name: "Performance workflow",
    expected_revision: 0,
    graph: documentGraph(setup.assignments[0], setup.assignments[1]),
    positions: [],
  });
  const samples: number[] = [];
  for (let i = 0; i < 20; i++) {
    const start = performance.now();
    const r = await page.request.get(`${setup.prefix}/workflows/${saved.id}`);
    expect(r.ok()).toBe(true);
    samples.push(performance.now() - start);
  }
  const navigation: number[] = [];
  for (let i = 0; i < 10; i++) {
    const start = performance.now();
    await page.goto(`/workflows/${saved.id}/builder`);
    await expect(page.getByLabel("Nama workflow")).toHaveValue(
      "Performance workflow",
    );
    navigation.push(performance.now() - start);
  }
  const p95 = (values: number[]) =>
    [...values].sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1];
  expect(p95(samples)).toBeLessThan(2000);
  expect(p95(navigation)).toBeLessThan(3000);
  const evidence = {
    source_sha: execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim(),
    source_modified: !!execFileSync("git", ["status", "--porcelain"], {
      encoding: "utf8",
    }).trim(),
    runtime: "isolated test only",
    dataset: "one governed workflow, two pinned published agents, seven nodes",
    api_samples_ms: samples,
    api_p95_ms: p95(samples),
    navigation_samples_ms: navigation,
    navigation_p95_ms: p95(navigation),
  };
  writeFileSync(
    info.outputPath("workflow-browser-performance.json"),
    JSON.stringify(evidence, null, 2),
  );
});
