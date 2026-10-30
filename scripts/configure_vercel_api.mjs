// Run after Render assigns the actual public API hostname; never accepts credentials.
import { readFile, writeFile } from "node:fs/promises";
const input = process.argv[2];
let origin;
try {
  origin = new URL(input);
  if (
    origin.protocol !== "https:" ||
    !origin.hostname.endsWith(".onrender.com") ||
    origin.username ||
    origin.password ||
    origin.port ||
    origin.search ||
    origin.hash ||
    origin.pathname !== "/"
  )
    throw new Error();
} catch {
  console.error(
    "Usage: node scripts/configure_vercel_api.mjs https://YOUR-API.onrender.com",
  );
  process.exit(1);
}
const file = new URL("../vercel.json", import.meta.url);
const config = JSON.parse(await readFile(file, "utf8"));
for (const rule of config.rewrites) {
  if (rule.source.startsWith("/api/") || rule.source.startsWith("/health/")) {
    rule.destination = origin.origin + rule.source;
  }
}
await writeFile(file, JSON.stringify(config, null, 2) + "\n");
console.log("Configured same-origin Vercel rewrites for " + origin.origin);
