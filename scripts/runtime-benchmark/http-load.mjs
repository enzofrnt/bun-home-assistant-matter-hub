// Fixed Node load generator for both runtimes, with four independent producers.
import http from "node:http";
import { performance } from "node:perf_hooks";
import {
  isMainThread,
  parentPort,
  Worker,
  workerData,
} from "node:worker_threads";

async function produce({ base, seconds, concurrency, expected, index }) {
  const paths = [
    "/api/home-assistant/entities?limit=100",
    "/api/home-assistant/stats",
    "/api/health/detailed",
    "/api/metrics",
  ];
  const agent = new http.Agent({ keepAlive: true, maxSockets: concurrency });
  const latencies = [];
  const byPath = {};
  let requests = 0,
    errors = 0,
    bytes = 0,
    issued = 0;
  const started = performance.now();
  const until = started + seconds * 1000;
  async function connection() {
    while (performance.now() < until) {
      const path = paths[(issued++ + index) % paths.length];
      const t = performance.now();
      await new Promise((resolve) => {
        const req = http.get(
          new URL(path, base),
          { agent, timeout: 10000 },
          (res) => {
            const chunks = [];
            res.on("data", (chunk) => chunks.push(chunk));
            res.on("end", () => {
              try {
                const body = Buffer.concat(chunks);
                bytes += body.length;
                const value = JSON.parse(body);
                if (res.statusCode !== 200) throw new Error("HTTP status");
                if (path.includes("/entities?") && value.total !== expected)
                  throw new Error("Entity count");
                if (
                  path.endsWith("/stats") &&
                  value.entities.total !== expected
                )
                  throw new Error("Stats count");
                if (path.endsWith("/detailed") && value.status !== "healthy")
                  throw new Error("Bridge health");
                if (
                  path.endsWith("/metrics") &&
                  value.bridges.totalDevices !== expected
                )
                  throw new Error("Matter count");
                latencies.push(performance.now() - t);
              } catch {
                errors++;
              }
              byPath[path] = (byPath[path] ?? 0) + 1;
              requests++;
              resolve();
            });
          },
        );
        req.on("timeout", () => req.destroy(new Error("Timeout")));
        req.on("error", () => {
          errors++;
          requests++;
          resolve();
        });
      });
    }
  }
  await Promise.all(Array.from({ length: concurrency }, () => connection()));
  agent.destroy();
  return {
    requests,
    errors,
    bytes,
    latencies,
    byPath,
    elapsed_seconds: (performance.now() - started) / 1000,
  };
}
if (!isMainThread) {
  parentPort.postMessage({ ready: true });
  parentPort.once("message", async () =>
    parentPort.postMessage(await produce(workerData)),
  );
} else {
  const [base, seconds = "10", concurrency = "16", expected = "0"] =
    process.argv.slice(2);
  const workers = [];
  const ready = [];
  const results = [];
  for (let index = 0; index < 4; index++) {
    const worker = new Worker(new URL(import.meta.url), {
      workerData: {
        base,
        seconds: Number(seconds),
        concurrency: Number(concurrency) / 4,
        expected: Number(expected),
        index,
      },
    });
    workers.push(worker);
    ready.push(
      new Promise((resolve, reject) => {
        worker.once("message", resolve);
        worker.once("error", reject);
      }),
    );
    results.push(
      new Promise((resolve, reject) => {
        worker.on("message", (message) => {
          if (!message.ready) resolve(message);
        });
        worker.on("error", reject);
        worker.on("exit", (code) => {
          if (code) reject(new Error(`Worker exit ${code}`));
        });
      }),
    );
  }
  await Promise.all(ready);
  for (const worker of workers) worker.postMessage("start");
  const parts = await Promise.all(results);
  const latencies = parts.flatMap((p) => p.latencies).sort((a, b) => a - b);
  const requests = parts.reduce((n, p) => n + p.requests, 0);
  const errors = parts.reduce((n, p) => n + p.errors, 0);
  const elapsed = Math.max(...parts.map((p) => p.elapsed_seconds));
  const percentile = (p) =>
    latencies[
      Math.min(latencies.length - 1, Math.floor(latencies.length * p))
    ] ?? null;
  const byPath = {};
  for (const part of parts)
    for (const [path, n] of Object.entries(part.byPath))
      byPath[path] = (byPath[path] ?? 0) + n;
  console.log(
    JSON.stringify({
      requests,
      errors,
      bytes: parts.reduce((n, p) => n + p.bytes, 0),
      elapsed_seconds: elapsed,
      requests_per_second: requests / elapsed,
      p50_ms: percentile(0.5),
      p95_ms: percentile(0.95),
      p99_ms: percentile(0.99),
      concurrency: Number(concurrency),
      producer_threads: 4,
      byPath,
    }),
  );
  process.exitCode = errors ? 1 : 0;
}
