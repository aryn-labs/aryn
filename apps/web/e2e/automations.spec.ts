import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { documentGraph } from "../src/lib/workflow-types";

async function setup(page: Page) {
  await page.goto("/automations");
  await expect(
    page.getByRole("heading", { name: "Automations", exact: true }),
  ).toBeVisible();
  const origin = "http://127.0.0.1:8711",
    prefix = "/api/projects/proj_studio_research";
  const bootstrap = await page.request.post("/api/session", {
    data: {},
    headers: { Origin: origin },
  });
  const headers = {
    Origin: origin,
    "X-CSRF-Token": (await bootstrap.json()).csrf,
  };
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
  return { prefix, headers, post, get };
}
async function seed(page: Page) {
  const data = await setup(page);
  const bp = await data.post("/blueprints", {
    name: "Scheduled research",
    slug: "scheduled-research",
  });
  const version = await data.post(`/blueprints/${bp.id}/versions`, {
    version_number: "1.0.0",
    system_prompt:
      "Follow research safety guidelines and abstain without evidence.",
    model: "test/model-a",
    max_tokens: 512,
    tool_grants: [],
  });
  expect(
    (
      await data.post(`/versions/${version.id}/bench`, {
        allow_remote_model: true,
      })
    ).passed,
  ).toBe(true);
  await data.post(`/versions/${version.id}/approve`, {
    payload_hash: version.payload_hash,
    comments: "Explicit isolated human review",
  });
  await data.post(`/versions/${version.id}/publish`);
  const assignment = await data.post("/assignments", {
    blueprint_id: bp.id,
    version_id: version.id,
    role_name: "Scheduled researcher",
  });
  return { ...data, bp, version, assignment };
}
async function saved(page: Page) {
  const data = await seed(page);
  const definition = await data.post("/automations", {
    title: "Governed research schedule",
    input: "Research safe internal evidence.",
    allow_remote_model: true,
    target: {
      kind: "agent",
      id: data.assignment.id,
      version_id: data.version.id,
      payload_hash: data.version.payload_hash,
      activation_id: data.assignment.current_transition_id,
    },
    schedule: {
      kind: "daily",
      timezone: "Asia/Bangkok",
      local_time: "09:00",
      start_at: new Date().toISOString(),
    },
  });
  await data.post(`/automations/${definition.id}/approve`, {
    expected_revision: 1,
    payload_hash: definition.payload_hash,
    reason: "Review schedule, pinned activation and bounded budget.",
  });
  await data.post(`/automations/${definition.id}/state`, {
    expected_revision: 1,
    enabled: true,
  });
  const occurrence = await data.post(`/automations/${definition.id}/run`, {
    expected_revision: 1,
    idempotency_key: "initial-review",
  });
  expect(occurrence.status).toBe("completed");
  return { ...data, definition, occurrence };
}

test("create, preview, exact approval, override idempotency, reload, pause and edit", async ({
  page,
}) => {
  const data = await seed(page);
  await page.goto("/automations/new");
  await page.getByLabel("Nama jadwal").fill("Keyboard Core schedule");
  await page
    .getByLabel("Target terverifikasi")
    .selectOption(`${data.assignment.id}:${data.version.id}`);
  await page
    .getByLabel("Input pekerjaan")
    .fill("Research scoped safe evidence.");
  await page.getByLabel("Timezone IANA").fill("America/New_York");
  await page.getByLabel("Jam lokal").fill("01:30");
  await page.getByRole("button", { name: "Preview jadwal server" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page
      .getByRole("list", { name: "Preview occurrence" })
      .getByRole("listitem"),
  ).toHaveCount(5);
  await page.getByLabel(/Izinkan eksekusi model target/).check();
  await page.getByRole("button", { name: "Simpan jadwal paused" }).click();
  await expect(page).toHaveURL(/\/automations\/automation_/);
  const id = page.url().split("/").at(-1)!;
  await expect(
    page.getByRole("button", { name: "Resume jadwal" }),
  ).toBeDisabled();
  const definition = await data.get(`/automations/${id}`);
  await expect(page.getByTestId("automation-hash")).toHaveText(
    definition.payload_hash,
  );
  await page
    .getByLabel("Alasan review jadwal")
    .fill("Explicit keyboard review of exact schedule, target and budget.");
  await page.getByLabel(/Saya meninjau exact target/).check();
  await page.getByRole("button", { name: "Setujui exact jadwal" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Resume jadwal" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Resume jadwal" }).click();
  await page.getByLabel("Idempotency key override").fill("keyboard-override");
  await page
    .getByRole("button", { name: "Jalankan occurrence manual" })
    .click();
  await expect(
    page.getByRole("link", { name: "Buka captured Core Run" }),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: "Jalankan occurrence manual" })
    .click();
  await expect(
    page.getByRole("link", { name: "Buka captured Core Run" }),
  ).toHaveCount(1);
  await page.getByRole("link", { name: "Buka captured Core Run" }).click();
  await expect(
    page.getByRole("link", { name: "Core Automation occurrence" }),
  ).toHaveAttribute("href", new RegExp(`/automations/${id}#occurrence_`));
  await page.getByRole("link", { name: "Core Automation occurrence" }).click();
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Buka captured Core Run" }),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "Pause jadwal" }).click();
  await expect(
    page.getByRole("button", { name: "Jalankan occurrence manual" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Edit jadwal" }).click();
  await page
    .getByLabel("Input pekerjaan")
    .fill("Different reviewed input requires a fresh hash.");
  await page.getByRole("button", { name: "Simpan jadwal paused" }).click();
  await expect(page.getByTestId("automation-hash")).not.toHaveText(
    definition.payload_hash,
  );
  await expect(page.getByLabel(/Saya meninjau exact target/)).not.toBeChecked();
  await expect(
    page.getByRole("button", { name: "Resume jadwal" }),
  ).toBeDisabled();
});

test("revoked reads hide cached authority; offline and project switch never expose stale actions", async ({
  page,
}) => {
  const data = await saved(page);
  await page.goto(`/automations/${data.definition.id}`);
  await expect(page.getByTestId("automation-hash")).toBeVisible();
  await page.route(
    `**${data.prefix}/automations/${data.definition.id}`,
    (route) =>
      route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ message: "Membership revoked" }),
      }),
  );
  await page
    .getByRole("button", { name: "Periksa kembali", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Akses proyek dibatasi" }),
  ).toBeVisible();
  await expect(page.getByTestId("automation-hash")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Jalankan occurrence manual" }),
  ).toHaveCount(0);
  await page.unrouteAll();
  await page.reload();
  await expect(page.getByTestId("automation-hash")).toBeVisible();
  await page.route(
    `**${data.prefix}/automations/${data.definition.id}`,
    (route) => route.abort(),
  );
  await page
    .getByRole("button", { name: "Periksa kembali", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Data belum dapat diverifikasi" }),
  ).toBeVisible();
  await expect(page.getByTestId("automation-hash")).toHaveCount(0);
  await page.unrouteAll();
  await page.goto("/automations");
  await page
    .getByLabel("Pilih proyek")
    .selectOption("proj_studio_browser_secondary");
  await expect(
    page.getByRole("link", { name: data.definition.title }),
  ).toHaveCount(0);
  await page.goto(`/automations/${data.definition.id}`);
  await expect(
    page.getByRole("heading", { name: "Data belum dapat diverifikasi" }),
  ).toBeVisible();
  await expect(page.getByTestId("automation-hash")).toHaveCount(0);
});

for (const width of [390, 768, 1440])
  for (const theme of ["dark", "light"]) {
    test(`Core control surfaces ${width} ${theme}: axe, keyboard, reflow`, async ({
      page,
    }, info) => {
      const data = await saved(page);
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.evaluate(
        (value) => localStorage.setItem("aryn-theme", value),
        theme,
      );
      const routes = [
        "/automations",
        `/automations/${data.definition.id}`,
        "/capabilities",
      ];
      for (let index = 0; index < routes.length; index++) {
        await page.goto(routes[index]);
        await expect(
          page.getByRole("heading", {
            name: ["Automations", data.definition.title, "Capabilities"][index],
            exact: true,
          }),
        ).toBeVisible();
        if (index === 1)
          await expect(
            page.getByRole("link", { name: "Buka captured Core Run" }),
          ).toBeVisible();
        if (index === 2)
          await expect(
            page.getByRole("heading", { name: "host.file", exact: true }),
          ).toBeVisible();
        await page.evaluate(async () => {
          await document.fonts.ready;
          await Promise.all(
            document
              .getAnimations()
              .filter(
                (a) => a.effect?.getComputedTiming().iterations !== Infinity,
              )
              .map((a) => a.finished.catch(() => {})),
          );
        });
        const audit = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        expect(audit.violations).toEqual([]);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await page.keyboard.press("Tab");
        await expect(page.locator(":focus")).toBeVisible();
        await page.screenshot({
          path: info.outputPath(
            `${["automations", "automation-detail", "capabilities"][index]}-${width}-${theme}.png`,
          ),
          fullPage: true,
        });
      }
    });
  }

test.describe("persisted automation inventory", () => {
  test.use({ workspaceDataset: "automations" });
  test("bounded schedule list and usable detail navigation performance", async ({
    page,
  }, info) => {
    const data = await setup(page);
    const definition = (
      await data.get("/automations?q=Governed%20benchmark%20primary")
    ).items[0];
    const first = await data.get("/automations?limit=100");
    const second = await data.get(`/automations?limit=100&after=${first.next}`);
    expect(first.items.length + second.items.length).toBe(200);
    expect(second.next).toBeNull();
    expect(
      (await data.get(`/automations/${definition.id}/occurrences`)).items[0]
        .status,
    ).toBe("completed");
    const api: number[] = [],
      navigation: number[] = [];
    for (let index = 0; index < 20; index++) {
      const start = performance.now();
      await data.get("/automations?limit=25");
      api.push(performance.now() - start);
    }
    for (let index = 0; index < 10; index++) {
      const start = performance.now();
      await page.goto(`/automations/${definition.id}`);
      await expect(
        page.getByRole("link", { name: "Buka captured Core Run" }),
      ).toBeVisible();
      navigation.push(performance.now() - start);
    }
    const percentile = (values: number[], ratio: number) =>
      [...values].sort((a, b) => a - b)[Math.ceil(values.length * ratio) - 1];
    expect(percentile(api, 0.95)).toBeLessThan(2000);
    expect(percentile(navigation, 0.95)).toBeLessThan(3000);
    writeFileSync(
      info.outputPath("automations-browser-performance.json"),
      JSON.stringify(
        {
          source_sha: execFileSync("git", ["rev-parse", "HEAD"], {
            encoding: "utf8",
          }).trim(),
          source_modified: !!execFileSync("git", ["status", "--porcelain"], {
            encoding: "utf8",
          }).trim(),
          dataset:
            "200 signed persisted definitions, one enabled approved schedule, one actual captured occurrence; isolated runtime",
          api_samples_ms: api,
          api_p50_ms: percentile(api, 0.5),
          api_p95_ms: percentile(api, 0.95),
          navigation_samples_ms: navigation,
          navigation_p50_ms: percentile(navigation, 0.5),
          navigation_p95_ms: percentile(navigation, 0.95),
        },
        null,
        2,
      ),
    );
  });
});

test("single-project cross-domain golden reaches scheduled Core run and read-only audit", async ({
  page,
}) => {
  test.setTimeout(180000); // One complete product path, retaining normal per-action assertions.
  const data = await setup(page);
  const division = await data.post("/divisions", {
    name: "Evidence team",
    slug: "evidence-team",
  });
  await page.goto("/factory");
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await page.getByLabel("Nama agent").fill("Golden Research Agent");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await page.getByRole("button", { name: "Buka AgentBuilder" }).click();
  await page.getByRole("button", { name: "Form lengkap", exact: true }).click();
  await page
    .getByLabel("Instruksi sistem")
    .fill("Follow research safety guidelines and abstain without evidence.");
  await page
    .getByRole("group", { name: "Model Policy" })
    .getByLabel("max tokens", { exact: true })
    .fill("512");
  await page
    .getByRole("button", { name: "Simpan working copy", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Buat candidate versi", exact: true })
    .click();
  await expect(page).toHaveURL(/\/factory\/[^/]+\/versions\/[^/]+$/);
  const bp = page.url().split("/")[4],
    versionId = page.url().split("/")[6];
  const snapshot = await data.get(`/lifecycle?version_id=${versionId}`);
  const version = snapshot.versions.find(
    (value: { id: string }) => value.id === versionId,
  );
  expect(
    (
      await data.post(`/versions/${versionId}/bench`, {
        allow_remote_model: true,
      })
    ).passed,
  ).toBe(true);
  await data.post(`/versions/${versionId}/approve`, {
    payload_hash: version.payload_hash,
    comments: "Review isolated Bench gate",
  });
  await data.post(`/versions/${versionId}/publish`);
  const assignment = await data.post("/assignments", {
    blueprint_id: bp,
    version_id: versionId,
    role_name: "Golden researcher",
    division_id: division.id,
  });
  const direct = await data.post("/runs", {
    assignment_id: assignment.id,
    prompt: "Research scoped evidence",
    allow_remote_model: true,
    idempotency_key: "golden-direct-run-intent",
  });
  expect(direct.execution_claim_verified).toBe(true);
  await page.goto(`/runs/${direct.run_id}`);
  await expect(
    page.getByRole("heading", { name: "Captured Core execution", exact: true }),
  ).toBeVisible();
  const newer = await data.post(`/blueprints/${bp}/versions`, {
    version_number: "2.0.0",
    system_prompt:
      "Follow research safety guidelines and abstain without evidence.",
    model: version.model,
    max_tokens: 512,
  });
  expect(
    (
      await data.post(`/versions/${newer.id}/bench`, {
        allow_remote_model: true,
      })
    ).passed,
  ).toBe(true);
  await data.post(`/versions/${newer.id}/approve`, {
    payload_hash: newer.payload_hash,
    comments: "Reviewed alternate known-good version",
  });
  await data.post(`/versions/${newer.id}/publish`);
  const newerAssignment = await data.post("/assignments", {
    blueprint_id: bp,
    version_id: newer.id,
    role_name: "Golden rollback probe",
  });
  const rollback = await data.post(
    `/assignments/${newerAssignment.id}/rollback`,
    {
      target_version_id: versionId,
      expected_current_version_id: newer.id,
      expected_transition_id: newerAssignment.current_transition_id,
      reason: "Restore the prior governed known-good version",
      idempotency_key: "golden-known-good-rollback",
    },
  );
  expect(rollback.to_version_id).toBe(versionId);
  // The real graph executor produces all three tasks and an inert staging artifact.
  const wf = await data.post("/workflows", {
    name: "Golden staging workflow",
    expected_revision: 0,
    graph: documentGraph(assignment, assignment),
    positions: [],
  });
  const frozen = await data.post(`/workflows/${wf.id}/versions`, {
    expected_revision: 1,
  });
  const run = await data.post(`/workflows/${wf.id}/runs`, {
    version_id: frozen.id,
    input: "Research safe static staging",
    idempotency_key: "golden-workflow",
    allow_remote_model: true,
  });
  expect(run.status).toBe("waiting_review");
  expect(
    run.tasks.filter(
      (value: { node_id: string; status: string }) =>
        ["research", "content", "website"].includes(value.node_id) &&
        value.status === "completed",
    ),
  ).toHaveLength(3);
  const artifact = await data.get(`/outputs/${run.artifact_id}`);
  await data.post(`/workflow-runs/${run.id}/review`, {
    digest: artifact.digest,
    decision: "accepted",
    reason: "Human accepts isolated staging artifact",
  });
  const source = await data.post("/brief/sources", {
    source_ref: { kind: "artifact", id: artifact.id },
    title: "Actual staging artifact evidence",
  });
  const abstaining = await data.post("/brief", {
    title: "Explicit evidence gap",
    source_ids: [source.id],
    hypothesis: {
      question: "Is this claim supported?",
      predicate: "contains_text",
      text: "unobserved claim",
      minimum_sources: 2,
    },
    workflow_run_id: run.id,
  });
  expect(abstaining.evaluation.status).toBe("INSUFFICIENT_EVIDENCE");
  const fixture = await data.post("/relay/demo-fixtures", {
    name: "Golden disposable worker",
  });
  await data.post(`/relay/demo-fixtures/${fixture.fixture.id}`, {
    expected_revision: 1,
    running: false,
    blocking_fault: false,
  });
  let incident = await data.post("/relay/signals", {
    target_id: fixture.fixture.id,
    dedup_key: "golden-worker",
    severity: "high",
  });
  incident = await data.post(`/relay/${incident.id}/investigate`, {
    expected_revision: incident.revision,
  });
  expect(incident.bundle.evaluation.status).toBe("CONFLICTING");
  incident = await data.post(`/relay/${incident.id}/proposals`, {
    expected_revision: incident.revision,
    target_id: incident.target_id,
    target_revision: incident.fixture.revision,
    bundle_id: incident.bundle_id,
    reason: "Review exact isolated evidence",
  });
  await data.post(`/relay/${incident.id}/approve`, {
    payload_hash: incident.proposal.payload_hash,
    reason: "Human reviews exact target/action",
  });
  incident = await data.post(`/relay/${incident.id}/execute`, {
    proposal_id: incident.proposal.id,
    payload_hash: incident.proposal.payload_hash,
    idempotency_key: "golden-recovery",
  });
  expect(incident.status).toBe("RECOVERED");
  incident = await data.post(`/relay/${incident.id}/close`, {
    expected_revision: incident.revision,
  });
  const replay = await data.post(
    `/bench/capsules/${incident.capsule_id}/replay`,
  );
  expect(replay.passed).toBe(true);
  expect(replay.live_write_calls).toBe(0);
  expect(replay.promotion_evidence).toBe(false);
  const automation = await data.post("/automations", {
    title: "Golden approved schedule",
    input: "Research scoped evidence",
    allow_remote_model: true,
    target: {
      kind: "agent",
      id: assignment.id,
      version_id: versionId,
      payload_hash: version.payload_hash,
      activation_id: assignment.current_transition_id,
    },
    schedule: {
      kind: "interval",
      interval_minutes: 60,
      timezone: "UTC",
      start_at: new Date().toISOString(),
    },
  });
  await data.post(`/automations/${automation.id}/approve`, {
    expected_revision: 1,
    payload_hash: automation.payload_hash,
    reason: "Review exact recurrence, target, input and policy",
  });
  await data.post(`/automations/${automation.id}/state`, {
    expected_revision: 1,
    enabled: true,
  });
  const occurrence = await data.post(`/automations/${automation.id}/run`, {
    expected_revision: 1,
    idempotency_key: "golden-scheduled-override",
  });
  expect(occurrence.status).toBe("completed");
  expect(
    (
      await page.request.get(
        data.prefix.replace(
          "proj_studio_research",
          "proj_studio_browser_secondary",
        ) + `/automations/${automation.id}`,
      )
    ).status(),
  ).toBe(404);
  for (const [path, heading] of [
    [`/outputs/${artifact.id}`, "Artifact provenance"],
    [`/brief/${incident.bundle_id}`, "Hipotesis & coverage"],
    [`/relay/${incident.id}`, "Incident & original signal"],
    [`/bench/replays/${replay.id}`, "Hasil replay"],
    [`/automations/${automation.id}`, "Authority & schedule"],
    ["/capabilities", "Effective capability registry"],
    ["/governance", "Jejak audit"],
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Halaman tidak ditemukan", { exact: true }),
    ).toHaveCount(0);
  }
  expect(source.id).toBeTruthy();
});
