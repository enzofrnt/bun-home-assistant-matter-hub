# Bun migration

This fork starts from RiDDiX/home-assistant-matter-hub commit `2a32ff3890a77c7d2df329768331a97c6af8dcd1` (main). It uses Bun **1.4.2** as the package manager, script runner and JavaScript runtime. Node/pnpm are needed only for the comparison checkout.

## Development

```bash
bun install --frozen-lockfile
bun run lint
bun run test
bun run build
```

`bun run test` deliberately runs the existing Vitest suites under Bun. `bun test` would select Bun's own runner and is not a substitute for these tests. No test source, assertion, fixture, timeout or Vitest configuration has been changed.

For development, copy `.env.sample` to `.env`, enter your Home Assistant URL and token, then run `bun run serve`. For the assembled application, run `bun run production`. The root scripts explicitly build prerequisite workspaces, and Bun runs the existing pre/post hooks. All JavaScript tools use Bun through `[run].bun = true` in `bunfig.toml`.

The documentation remains a separate project, as in upstream, so its TypeScript and dependency overrides do not affect the application:

```bash
cd docs-site
bun install --frozen-lockfile
bun run build
```

## Dependency and runtime changes

- Imported `pnpm-lock.yaml` into the text `bun.lock`, preserving resolved package versions; replaced `pnpm.overrides` and workspace YAML with root workspace/override fields.
- Imported the documentation's npm lock into `docs-site/bun.lock`.
- Retained isolated dependency installation, explicitly trusting only the SWC postinstall that is needed by the toolchain. The documentation's core-js postinstall notices remain blocked; they are not needed for compilation.
- Preserved Vitest, Vite, TypeScript and esbuild. Porting package management/runtime does not require rewriting application code to Bun-specific APIs.
- Replaced tsx watch, Node entrypoint shebangs and runtime npm plugin installs with Bun equivalents. Plugin packages still come from the npm registry.
- Kept runtime libraries external to the backend bundle, while bundling the internal common workspace. This preserves each library's dependency tree and native/conditional imports. The upstream bundle leaves imports such as `@noble/hashes` in the app without declaring them directly; isolated resolution cannot find those imports. A flat production install can mask this upstream issue.
- Split the CLI entrypoint from its implementation. Loading the latter dynamically after bootstrap ensures matter.js is configured before its environment initializes. Both development and assembled CLI use the same sequence.
- Kept `node:*` imports and the `@matter/nodejs` adapter because Bun supports these APIs. matter.js falls back to its standard crypto implementation when Bun does not expose `aes-128-ccm` through Node's crypto interface; the existing crypto/device/loopback tests still execute.
- Used Bun for packing and release tooling, including an explicit version script. Package names and pinned application dependencies remain compatible with the original package tests.

The imported app lock contains the same resolved package identifiers as pnpm except four duplicate MUI 9 peer-context entries that Bun does not retain (`@mui/private-theming`, `@mui/styled-engine`, `@mui/system`, `@mui/utils`). No new app dependency versions were introduced. The comparison therefore measures the migrated installation as a whole, not a perfectly identical module layout.

## Docker and compatibility

```bash
bun run build
docker build -f apps/home-assistant-matter-hub/standalone.Dockerfile \
  -t bun-home-assistant-matter-hub:local apps/home-assistant-matter-hub
docker run --rm bun-home-assistant-matter-hub:local home-assistant-matter-hub --help
```

The standalone image uses `oven/bun:1.4.2-alpine`; the add-on copies the musl Bun executable into the Home Assistant base. Both install the packed app with Bun and retain the app's production dependency overrides. The standalone process uses tini for signal handling. The add-on still accepts Home Assistant configuration and the Supervisor token through its entrypoint.

Bun supports Linux amd64 and arm64, so the previous standalone arm/v7 target is removed. Neither a physical ARM32 device nor a real Home Assistant Supervisor deployment has been tested.

Bun uses JavaScriptCore and manages its heap automatically. `NODE_OPTIONS=--max-old-space-size` and the previous add-on `heap_size_mb` setting do not tune Bun. The add-on reports that the legacy option is ignored. Container memory limits still bound total process memory. Runtime pressure checks use Bun's `node:v8` compatibility statistics; they should be validated on the target host under a representative bridge load.

## CI and release behavior

CI uses `oven-sh/setup-bun@v2`, the pinned Bun version and frozen lockfiles. Documentation, tests, builds and Docker definitions use Bun. GitHub Actions implemented by third parties may internally use their own Node runtime; the project's scripts do not require it.

Release workflows are gated to the original repository because their publishing destinations still name the upstream npm package and add-on repository. Configure fork-owned destinations before enabling releases here. No npm package, container image, GitHub release or add-on dispatch was published during this migration.

Bun publish does not support npm provenance attestations. The migrated publishing commands omit the upstream `--provenance` flag; publication itself has not been exercised. See [Bun publishing documentation](https://bun.sh/docs/pm/cli/publish).

## Reproduce the performance comparison

The script is for macOS and requires Python 3, Node 24, pnpm 10.33.0 and Bun 1.4.2. It removes the root/application workspace `node_modules` directories in both checkouts, installs offline from their already-warmed caches and leaves source/tests intact. Do not run it alongside another build or test workload.

```bash
git worktree add --detach ../matter-hub-node-baseline 2a32ff3890a77c7d2df329768331a97c6af8dcd1
(cd ../matter-hub-node-baseline && pnpm install --frozen-lockfile)
bun install --frozen-lockfile
python3 scripts/benchmark.py \
  --baseline ../matter-hub-node-baseline \
  --output benchmark-results --rounds 3
```

Each round alternates Node/Bun order and measures installation, build, then the common/backend/frontend/package Vitest suites. Every suite runs even when an earlier one fails. The script checks SHA-256 hashes of tracked tests and fixtures before and after execution.

Wall time, CPU seconds and maximum process RSS come from macOS `/usr/bin/time -l`. The script also samples the sum of RSS across descendants about every 100 ms. This sum can double-count shared pages and miss brief peaks; it is not physical RAM. The result files preserve commands, exit codes, test counts, environment and raw logs. Full-suite time/CPU totals are sums across sequential suites; memory is the maximum observed across suites.

See [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) for measured results and limitations. Development/build measurements do not establish live Home Assistant throughput, paired Matter behavior, idle memory or Raspberry Pi performance.
