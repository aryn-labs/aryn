import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";

async function blueprint(page: import("@playwright/test").Page) {
  await page.goto("/factory");
  await page
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await page.getByLabel("Nama agent").fill("Evidence Research Agent");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Buat blueprint", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Evidence Research Agent", exact: true }),
  ).toBeVisible();
  const id = new URL(page.url()).pathname.split("/")[2];
  await page.getByRole("button", { name: "Buka AgentBuilder" }).click();
  await expect(
    page.getByRole("heading", { name: /AgentBuilder/ }),
  ).toBeVisible();
  return { id, prefix: `/api/projects/proj_studio_research/blueprints/${id}` };
}

test("typed editor roundtrip, explicit candidate, separate layout and responsive keyboard form", async ({
  page,
}, info) => {
  test.setTimeout(90000);
  const { id, prefix } = await blueprint(page);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  await expect(page.locator(".react-flow__handle.connectable")).toHaveCount(0);
  await page.getByRole("button", { name: "Form lengkap", exact: true }).focus();
  await page.keyboard.press("Enter");
  const identity = page.getByRole("group", { name: "Identity & Objective" });
  await identity.getByLabel("Role", { exact: true }).fill("researcher");
  await identity
    .getByLabel("Objective", { exact: true })
    .fill("Evidence grounded synthesis");
  await identity.getByLabel("Owner", { exact: true }).fill("research-team");
  await identity
    .getByLabel("Metadata", { exact: true })
    .fill('{"purpose":"analysis"}');
  await page
    .getByLabel("Instruksi sistem")
    .fill(
      "Provide evidence grounded research. Refuse host access and abstain without verified evidence.",
    );
  const model = page.getByRole("group", { name: "Model Policy" });
  await model.getByLabel("temperature", { exact: true }).fill("0.2");
  await model.getByLabel("max tokens", { exact: true }).fill("512");
  await model
    .getByLabel("allowed models")
    .fill(await model.getByLabel("primary model").inputValue());
  await model.getByLabel("stop sequences").fill("END");
  const output = page.getByRole("group", { name: "Output Contract" });
  await output.getByLabel("format", { exact: true }).selectOption("json");
  await output.getByLabel("description").fill("Grounded report");
  await output.getByLabel("required sections").fill("Evidence\nLimitations");
  await output
    .getByLabel("schema definition")
    .fill('{"type":"object","properties":{"answer":{"type":"string"}}}');
  await output.getByLabel("strict").check();
  const constraints = page.getByRole("group", { name: "Constraints" });
  await constraints.getByLabel("disallowed actions").fill("host access");
  await constraints.getByLabel("operational rules").fill("cite sources");
  await constraints.getByLabel("max execution time seconds").fill("90");
  const budget = page.getByRole("group", { name: "Budget Policy" });
  await budget.getByLabel("max tokens per run").fill("512");
  await budget.getByLabel("max turns").fill("3");
  await budget.getByLabel("max cost usd").fill("0.1");
  await budget.getByLabel("timeout seconds").fill("90");
  await expect(
    page
      .getByRole("group", { name: "Tool Policy" })
      .getByLabel("network access"),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Simpan working copy", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Tersimpan · generation 1" }),
  ).toBeVisible();
  const saved = await (await page.request.get(`${prefix}/working-copy`)).json();
  expect(saved.definition.model_policy.stop_sequences).toEqual(["END"]);
  expect(saved.definition.output_contract.required_sections).toEqual([
    "Evidence",
    "Limitations",
  ]);
  expect(saved.definition.constraints.operational_rules).toEqual([
    "cite sources",
  ]);
  expect(saved.definition.budget_policy.max_cost_usd).toBe(0.1);
  expect(saved.definition.tool_grants).toEqual([]);
  expect(saved.definition.metadata).toEqual({ purpose: "analysis" });
  expect(saved.definition.evaluation_reference.required_scenarios).toHaveLength(
    4,
  );
  await page.reload();
  await page.getByRole("button", { name: "Form lengkap", exact: true }).click();
  await expect(page.getByLabel("Objective", { exact: true })).toHaveValue(
    "Evidence grounded synthesis",
  );
  await expect(page.getByLabel("stop sequences")).toHaveValue("END");
  await page
    .getByRole("button", { name: "Buat candidate versi", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`/factory/${id}/versions/`));
  const versionId = new URL(page.url()).pathname.split("/")[4];
  const canonical = await (
    await page.request.get(
      `/api/projects/proj_studio_research/lifecycle?version_id=${versionId}`,
    )
  ).json();
  const version = canonical.versions.find(
    (item: { id: string }) => item.id === versionId,
  );
  for (const [field, value] of Object.entries(saved.definition))
    expect(version[field], field).toEqual(value);
  const hash = version.payload_hash;
  await page.goto(`/factory/${id}/builder`);
  const node = page.locator('.react-flow__node[data-id="model"]');
  await expect(node).toBeVisible();
  const box = await node.boundingBox();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + 30);
  await page.mouse.down();
  await page.mouse.move(box!.x + 80, box!.y + 80, { steps: 10 });
  await page.mouse.up();
  await page
    .getByRole("button", { name: "Simpan layout", exact: true })
    .click();
  const layout = await (
    await page.request.get(`${prefix}/editor-layout`)
  ).json();
  expect(layout.generation).toBe(1);
  const unchanged = await (
    await page.request.get(
      `/api/projects/proj_studio_research/lifecycle?version_id=${versionId}`,
    )
  ).json();
  expect(unchanged.versions[0].payload_hash).toBe(hash);
  expect(unchanged.versions).toHaveLength(1);
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) =>
        /prompt|credential|draft/i.test(key),
      ),
    ),
  ).toEqual([]);
  for (const theme of ["dark", "light"] as const) {
    if (theme === "light")
      await page.getByRole("button", { name: "Gunakan tema terang" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await page.evaluate(async () => {
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
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page
        .getByRole("button", { name: "Instructions", exact: true })
        .click();
      await expect(page.getByLabel("Instruksi sistem")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.evaluate(() => {
        (document.activeElement as HTMLElement | null)?.blur();
        window.scrollTo(0, 0);
      });
      await page.screenshot({
        path: info.outputPath(`agent-builder-${theme}-${width}.png`),
        fullPage: true,
      });
    }
  }
});

test("conflict preserves local input, reload restores generation, undo and discard stay explicit", async ({
  page,
}) => {
  const { prefix } = await blueprint(page);
  await page
    .getByLabel("Objective", { exact: true })
    .fill("Original objective");
  await page
    .getByRole("button", { name: "Simpan working copy", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "generation 1" }),
  ).toBeVisible();
  const copy = await (await page.request.get(`${prefix}/working-copy`)).json();
  const csrf = await (
    await page.request.post("/api/session", {
      data: {},
      headers: { Origin: "http://127.0.0.1:8711" },
    })
  ).json();
  const headers = {
    Origin: "http://127.0.0.1:8711",
    "X-CSRF-Token": csrf.csrf,
  };
  const concurrent = await page.request.post(`${prefix}/working-copy`, {
    data: {
      expected_generation: 1,
      definition: { ...copy.definition, objective: "Concurrent editor" },
    },
    headers,
  });
  expect(concurrent.status()).toBe(200);
  await page
    .getByLabel("Objective", { exact: true })
    .fill("My preserved input");
  await page
    .getByRole("button", { name: "Simpan working copy", exact: true })
    .click();
  await expect(page.getByRole("alert").first()).toContainText(
    /changed|generation/i,
  );
  await expect(page.getByLabel("Objective", { exact: true })).toHaveValue(
    "My preserved input",
  );
  await page.getByRole("button", { name: "Muat ulang working copy" }).click();
  await expect(page.getByLabel("Objective", { exact: true })).toHaveValue(
    "Concurrent editor",
  );
  await page.getByRole("button", { name: "Pulihkan input lokal" }).click();
  await expect(page.getByLabel("Objective", { exact: true })).toHaveValue(
    "My preserved input",
  );
  await page.getByLabel("Role", { exact: true }).fill("changed-role");
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByLabel("Role", { exact: true })).toHaveValue(
    "general_agent",
  );
  await page
    .getByRole("button", { name: "Simpan working copy", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "generation 3" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Buang working copy" }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`${prefix}/working-copy`)).json())
          .definition,
    )
    .toBeNull();
});
