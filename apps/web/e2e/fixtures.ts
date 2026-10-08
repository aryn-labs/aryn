import { test as base, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import { resolve } from "node:path";

// One actual API/Core server and fresh authority/database per test. No reset API
// exists in the product, and test state cannot leak into the next browser case.
export const test = base.extend<{ studioServer: void }>({
  studioServer: [
    async ({}, use, testInfo) => {
      const env: NodeJS.ProcessEnv = {};
      for (const name of [
        "PATH",
        "Path",
        "SystemRoot",
        "USERPROFILE",
        "HOME",
        "TEMP",
        "TMP",
        "VIRTUAL_ENV",
      ])
        if (process.env[name]) env[name] = process.env[name];
      const log = createWriteStream(testInfo.outputPath("server.log"));
      const child = spawn(
        process.env.ARYN_TEST_PYTHON || "python",
        ["-m", "tests.studio_server"],
        {
          cwd: resolve(import.meta.dirname, "../../.."),
          env,
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      child.stdout.pipe(log);
      child.stderr.pipe(log);
      const closed = once(child, "close");
      let ready = false;
      try {
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline && child.exitCode === null) {
          try {
            ready = (await fetch("http://127.0.0.1:8711/")).ok;
          } catch {
            /* Listener has not started yet. */
          }
          if (ready) break;
          await new Promise((resolve) => setTimeout(resolve, 100));
        }
        expect(
          ready,
          "Isolated Studio server must start with a built frontend",
        ).toBe(true);
        await use();
      } finally {
        child.kill();
        await closed;
        log.end();
      }
    },
    { auto: true },
  ],
});
export { expect };
