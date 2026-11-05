# Production runtime benchmark

This comparison measures the original Node production package and the Bun production package while they are serving the application. It is separate from the install/build/test-runner timings in `BENCHMARK_RESULTS.md`. Complete unchanged test coverage is in `COMPATIBILITY_RESULTS.md`.

## Workload and isolation

- Linux ARM64 containers on Docker Desktop, Apple M4 Pro host. Each application receives **2 CPUs and 2 GiB memory**. The original Node image calculates a 1 GiB V8 heap cap from that cgroup limit; Bun uses its default JavaScriptCore heap management.
- Production images: `home-assistant-matter-hub:node-baseline` (Node 24.19.0, original commit `2a32ff3890a77c7d2df329768331a97c6af8dcd1`) and `bun-home-assistant-matter-hub:local` (Bun 1.4.2, migrated application).
- Profiles: no bridge/zero entities; one active Matter bridge with **100** entities; one active bridge with **500** entities. Half the entities are temperature sensors and half are switches. Every entity has a separate synthetic Home Assistant device.
- A separate fixture supplies the Home Assistant WebSocket protocol and entity/device/state registries. It uses no real token, Home Assistant instance or physical device. The bridge creates real matter.js endpoints in an isolated IPv4/IPv6 Docker network.
- The fixture has one CPU/256 MiB. The fixed Node HTTP generator has four CPUs/512 MiB, four producer threads and **16 concurrent keep-alive requests**. Neither helper's memory/CPU is counted as application resource use. Producer CPU is retained to identify a possible client bottleneck.
- Every fresh application gets two seconds of API warm-up and five seconds to settle, followed by ten-second phases: idle; 100 state changes/second for nonempty bridges; then API load while those updates continue. A five-second recovery period follows after updates stop. Three rounds alternate Node/Bun order, using new processes and fresh storage each time.
- A cyclic issue counter assigns exactly one quarter of requests to each route; every retained run must satisfy the route-count balance assertion. API traffic mixes entity listing (up to 100 per response), Home Assistant statistics, detailed bridge health and application metrics. Responses are parsed and checked for HTTP status, entity/endpoint counts and healthy state. The fixture records how many updates it delivers to subscriptions. The app must remain healthy with every expected endpoint and terminate normally without an OOM kill. A post-measurement Matter state snapshot verifies that sensor values changed from their initial state.
- The benchmark records startup until the registry/API is ready and bridge creation separately. Startup includes the application's built-in five-second wait for Home Assistant's RUNNING state.

## Resource definitions

The RAM figure is the **application process's current RSS from Linux `/proc/<pid>/smaps_rollup`**, not JavaScript heap size and not container image size. It includes resident native code, libraries and the engine. PSS and private dirty pages are retained separately in the raw results. The cgroup memory counter is also retained; it can include file cache and sampler/helper overhead inside the application container.

CPU time comes from the application container's cgroup `cpu.stat`. Percentage uses one CPU as 100%, so the two-CPU quota permits up to 200%. Samples are taken approximately once per second using a small `docker exec` shell. Its cost is included in the cgroup CPU, so small idle CPU differences should be treated cautiously. API efficiency is also expressed as CPU milliseconds per successful request; API phases on nonempty bridges include the continuing background state updates.

The reported values are medians across three runs. API throughput and latency come from the fixed external generator; the same producer, connection count, request mix and response validation apply to both servers. Startup/bridge creation and initial idle RAM are short-run measurements, not claims about a process that has run for days. Recovery RAM shows the working set after this workload; memory is not forcibly garbage-collected.

## Reproduce

Build the original Node production image from the unchanged baseline checkout after `pnpm run build`:

```bash
docker build --build-arg NODE_VERSION=24.19.0 \
  -f apps/home-assistant-matter-hub/standalone.Dockerfile \
  -t home-assistant-matter-hub:node-baseline apps/home-assistant-matter-hub
```

In this Bun checkout:

```bash
bun install --frozen-lockfile
bun run build
docker build -f apps/home-assistant-matter-hub/standalone.Dockerfile \
  -t bun-home-assistant-matter-hub:local apps/home-assistant-matter-hub
docker build -f scripts/runtime-benchmark/Fixture.Dockerfile \
  -t hamh-runtime-benchmark:fixture scripts/runtime-benchmark
docker build -f scripts/runtime-benchmark/Load.Dockerfile \
  -t hamh-runtime-benchmark:load scripts/runtime-benchmark
python3 scripts/runtime-benchmark/run.py \
  --output benchmark-results/runtime --rounds 3 --entities 0 100 500 \
  --seconds 10 --settle 5
```

Use a quiet machine. The script refuses to reuse its existing benchmark network, creates only its own named containers and removes them and their fresh anonymous data volumes on exit. It does not stop other containers. Docker health checks are disabled for the measured app so their timing cannot affect one runtime differently. Raw reports retain image IDs, Docker/VM characteristics, samples, response errors, latency percentiles, endpoint counts and shutdown status.

For complete tests, use a source-only Docker build context (for example, `git archive HEAD` extracted into a temporary directory), then build `scripts/runtime-benchmark/Compatibility.Dockerfile` from that context. Run the image as root in its own container so port 80 is available. `HAMH_LOOPBACK=1` is set by the image. The test worker limit does not change any assertion or timeout.

## Interpretation limits

This measures the two deployed versions, including their packaging and dependency layouts. It does not isolate only the JavaScript engine with a byte-identical module graph. The original bundle includes matter.js internals and uses npm's flatter production installation; the migration leaves runtime libraries external and uses Bun installation. Direct dependency versions remain pinned, while transitive resolution/layout can differ.

The primary HTTP workload has no paired external controller. The additional paired-controller workload below measures actual encrypted Matter exchanges with a software controller. State changes exercise Home Assistant subscriptions and Matter endpoint updates, but throughput is for the HTTP API, not encrypted Matter commands, controller subscriptions, video streaming or camera transcoding. Those protocol paths have functional test coverage; their production performance is not inferred from HTTP requests/second. The results do not establish long-term leak behavior or performance on a Raspberry Pi.

A Docker Desktop restart was needed before measurement because container creation and exec operations had stalled. The user authorized it; the four pre-existing myownnotion services were checked healthy afterward. Compatibility tests and preliminary functional runs were completed before the retained performance trials. The other desktop services remained present; this is a local comparative experiment rather than a dedicated physical benchmark host.

A preliminary series was discarded because its route selector depended on response completion order, which changed the request mix between runtimes. The retained series was restarted from zero after replacing it with cyclic request issuance and adding an exact balance assertion. Draft throughput figures are not included in the retained results.

## Paired Matter controller comparison

A second experiment uses one fixed Bun 1.4.2/matter.js 0.18.0 software controller with a fresh fabric, against a 100-endpoint bridge. It subscribes to the 50 temperature values and 50 OnOff values (minimum interval 0 s, maximum 10 s), receives changes during a 100-state-changes/s stream, and performs sequential encrypted Read transactions of 100 attributes. `includeKnownVersions` disables injected version filters so every Read requests all 100 values remotely.

The app still receives 2 CPUs/2 GiB; the separate controller receives 2 CPUs/1 GiB. The controller's CPU and network counters are retained separately. Each of three alternating rounds measures paired idle, updates only, Reads plus updates (10 seconds each), then recovery (5 seconds). There is no HTTP saturation warm-up in this experiment. Its absolute RSS values should not be compared directly with the API-warmed process in the first experiment.

Build the source-only compatibility image first, then:

```bash
docker build -f scripts/runtime-benchmark/Controller.Dockerfile \
  -t hamh-runtime-benchmark:controller scripts/runtime-benchmark
python3 scripts/runtime-benchmark/paired-run.py \
  --output benchmark-results/paired --rounds 3 --seconds 10 --entities 100
```

The script verifies a commissioned fabric, 100 initial subscribed values, changed subscription values, complete Read responses, healthy bridge/device counts, clean application logs, no OOM and graceful exit. This is one sequential controller and a batch of 100 values, not a test of maximum possible Matter transaction throughput or a physical controller.

Measured medians, CPU/RAM tables and conclusions are in [RUNTIME_RESULTS.md](RUNTIME_RESULTS.md).
