import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import {
  mkdtemp,
  mkdir,
  copyFile,
  readFile,
  readdir,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));

test("Vercel build publishes only the public shell and its five assets", async () => {
  execFileSync(process.execPath, ["scripts/build_dashboard.mjs"], {
    cwd: root,
  });
  const files = (
    await readdir(path.join(root, "dist"), {
      recursive: true,
      withFileTypes: true,
    })
  )
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
  assert.deepEqual(files, [
    "accounts.js",
    "app.js",
    "i18n.js",
    "index.html",
    "paper.js",
    "style.css",
  ]);
  const original = await readFile(
    path.join(root, "apps/dashboard/static/index.html"),
    "utf8",
  );
  assert.equal(
    await readFile(path.join(root, "dist/index.html"), "utf8"),
    original,
  );
  for (const asset of ["accounts.js", "app.js", "i18n.js", "paper.js", "style.css"]) {
    assert.equal(
      await readFile(path.join(root, "dist/dashboard/assets", asset), "utf8"),
      await readFile(path.join(root, "apps/dashboard/static", asset), "utf8"),
    );
  }
});

test("Render origin configuration changes only same-origin proxy targets and rejects credentials", async () => {
  const folder = await mkdtemp(path.join(tmpdir(), "hq-vercel-"));
  try {
    await mkdir(path.join(folder, "scripts"));
    await copyFile(
      path.join(root, "scripts/configure_vercel_api.mjs"),
      path.join(folder, "scripts/configure_vercel_api.mjs"),
    );
    await copyFile(
      path.join(root, "vercel.json"),
      path.join(folder, "vercel.json"),
    );
    const script = path.join(folder, "scripts/configure_vercel_api.mjs");
    execFileSync(process.execPath, [
      script,
      "https://example-api.onrender.com",
    ]);
    const config = JSON.parse(
      await readFile(path.join(folder, "vercel.json"), "utf8"),
    );
    assert.equal(
      config.rewrites.find((r) => r.source.startsWith("/api/")).destination,
      "https://example-api.onrender.com/api/v1/:path*",
    );
    assert.equal(
      config.rewrites.find((r) => r.source === "/dashboard").destination,
      "/index.html",
    );
    const saved = await readFile(path.join(folder, "vercel.json"), "utf8");
    for (const invalid of [
      "http://example.onrender.com",
      "https://attacker.test",
      "https://user:secret@example.onrender.com",
      "https://example.onrender.com/path",
      "https://example.onrender.com?key=secret",
    ]) {
      const result = spawnSync(process.execPath, [script, invalid], {
        encoding: "utf8",
      });
      assert.equal(result.status, 1);
      assert.equal(result.stderr.includes("secret"), false);
      assert.equal(
        await readFile(path.join(folder, "vercel.json"), "utf8"),
        saved,
      );
    }
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});
