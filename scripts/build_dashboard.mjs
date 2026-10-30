// Copy only the public dashboard shell. Python code, reports and secrets stay off Vercel.
import { cp, mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const output = path.join(root, "dist");
const source = path.join(root, "apps", "dashboard", "static");
await rm(output, { recursive: true, force: true });
await mkdir(path.join(output, "dashboard", "assets"), { recursive: true });
await cp(path.join(source, "index.html"), path.join(output, "index.html"));
for (const asset of ["app.js", "accounts.js", "i18n.js", "style.css"]) {
  await cp(
    path.join(source, asset),
    path.join(output, "dashboard", "assets", asset),
  );
}
console.log("Built public dashboard assets in dist/.");
