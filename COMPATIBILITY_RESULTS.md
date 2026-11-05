# Bun compatibility validation

Validated on 5 November 2026 against upstream commit `2a32ff3890a77c7d2df329768331a97c6af8dcd1`, using Bun 1.4.2. No test source, fixtures, assertions, Vitest configurations or test timeouts were modified.

## Complete Linux test coverage

| Workspace | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Common | 134 | 0 | 0 |
| Backend | 1,993 | 0 | 0 |
| Frontend | 88 | 0 | 0 |
| Packaged application | 2 | 0 | 0 |
| **Total** | **2,217** | **0** | **0** |

The backend ran in an Alpine Linux ARM64 container with four CPUs, 5 GiB memory and four Vitest workers. The other workspaces ran in the same test image, with four workers and 3 GiB memory. Application dependency versions came from the frozen Bun lock. Reports include per-assertion statuses.

`HAMH_LOOPBACK=1` activates five integration tests: four camera/WebRTC live-view cases and one Matter vacuum subscription case. Two other tests call `ctx.skip()` when they cannot bind loopback port 80. The isolated Linux container runs as root and owns port 80, so those tests execute too.

This corrects the earlier shorthand description of the seven skipped tests: five require the environment flag; two depend on port availability/permissions.

## macOS cross-check

With `HAMH_LOOPBACK=1 bun run test`, 2,215 tests passed and two port-80 tests skipped through their existing environment guard. The default macOS run had 2,210 passes and seven skips. No test was disabled specifically for Bun.

The unchanged Node baseline, with loopback enabled, encountered two failures in the parallel macOS backend run: the existing VeSync locking failure and a WebRTC provider cleanup locking/transaction failure. These did not occur in the Bun validation. Logs retain these results; failures are not omitted from the comparison.

## Scope

These results cover all tests provided by the repository, including simulated controller commissioning, encrypted Matter exchanges, camera media loopback and subscription updates. They do not certify interoperability with every physical Matter controller or camera, long-term stability, or a real Home Assistant Supervisor installation.

Runtime resource measurements and reproduction commands are documented separately in `RUNTIME_BENCHMARK.md`. The build/install benchmarks remain in `BENCHMARK_RESULTS.md`.
