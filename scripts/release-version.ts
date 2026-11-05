import { readFileSync, writeFileSync } from "node:fs";

const version = process.argv[2];
if (
  !version ||
  !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(version)
) {
  throw new Error("Usage: bun run release:version <semver>");
}
// Keep every published workspace version in sync without creating a tag.
for (const file of [
  "package.json",
  "packages/common/package.json",
  "packages/backend/package.json",
  "packages/frontend/package.json",
  "apps/home-assistant-matter-hub/package.json",
]) {
  const pkg = JSON.parse(readFileSync(file, "utf8"));
  pkg.version = version;
  writeFileSync(file, `${JSON.stringify(pkg, null, 2)}\n`);
}
const result = Bun.spawnSync(["bun", "install", "--lockfile-only"]);
if (result.exitCode) {
  process.stderr.write(result.stderr);
  process.exit(result.exitCode);
}
