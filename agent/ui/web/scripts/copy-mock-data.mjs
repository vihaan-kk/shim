// Copies the committed reference outputs from data/reference/ into public/mock/
// so the mock API can serve real meshes and real validation reports.
// The source files are read, never modified.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..", "..");
const source = join(repoRoot, "data", "reference");
const target = join(here, "..", "public", "mock");

const files = [
  "standardized_limb.stl",
  "standardized_socket.stl",
  "standardized_limb_validation.json",
  "standardized_socket_report.json",
];

mkdirSync(target, { recursive: true });
for (const name of files) {
  const from = join(source, name);
  if (!existsSync(from)) {
    console.warn(`[mock] missing ${from}; that region will show an empty state`);
    continue;
  }
  copyFileSync(from, join(target, name));
}
console.log(`[mock] copied reference files to ${target}`);
