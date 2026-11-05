// Fixed external Matter commissioner/client for both server runtimes.
import { lookup } from "node:dns/promises";
import { config } from "@matter/nodejs/config";

config.loadConfigFile = false;
config.loadProcessArgv = false;
config.loadProcessEnv = false;
config.trapProcessSignals = false;
const {
  Environment,
  VariableService,
  Logger,
  Seconds,
  ControllerBehavior,
  ServerNode,
  VendorId,
} = await import("@matter/main");
await import("@matter/nodejs");
const { Read, Subscribe } = await import("@matter/main/protocol");
const { TemperatureMeasurement, OnOff } = await import("@matter/main/clusters");
Logger.level = "error";
let controller, client, subscription;
let ready = false;
let received = 0,
  changed = 0,
  reports = 0;
let pairingSeconds = 0;
const values = new Map();
const selectors = () => [
  Read.Attribute({
    cluster: TemperatureMeasurement.Complete,
    attributes: "measuredValue",
  }),
  Read.Attribute({ cluster: OnOff.Complete, attributes: "onOff" }),
];
async function consume(data, track = false) {
  let count = 0;
  for await (const chunk of data)
    for (const entry of chunk) {
      if (entry.kind === "attr-status")
        throw new Error(`Matter attribute status: ${JSON.stringify(entry)}`);
      if (entry.kind !== "attr-value") continue;
      count++;
      if (track) {
        const key = `${entry.path.endpointId}:${entry.path.clusterId}:${entry.path.attributeId}`;
        if (values.has(key) && values.get(key) !== entry.value) changed++;
        values.set(key, entry.value);
        received++;
      }
    }
  if (track) reports++;
  return count;
}
async function start() {
  const bridges = await (
    await fetch("http://hamh-runtime-bench-app:8482/api/matter/bridges")
  ).json();
  const bridge = bridges[0];
  if (!bridge || bridge.status !== "running")
    throw new Error("Bridge not running");
  const environment = new Environment("controller", Environment.default);
  environment
    .get(VariableService)
    .set("storage.path", "/tmp/runtime-controller");
  environment.get(VariableService).set("runtime.signals", false);
  controller = await ServerNode.create(
    ServerNode.RootEndpoint.with(ControllerBehavior),
    {
      environment,
      id: "runtime-controller",
      network: { port: 0 },
      basicInformation: { vendorId: VendorId(0xfff1), productId: 0x8001 },
    },
  );
  await controller.start();
  const ip = (await lookup("hamh-runtime-bench-app", { family: 4 })).address;
  client = await controller.peers.forDescriptor({
    addresses: [{ type: "udp", ip, port: bridge.port }],
    deviceIdentifier: "runtime-bridge",
    D: bridge.commissioning.discriminator,
    CM: 1,
  });
  const t = performance.now();
  await client.commission({
    passcode: bridge.commissioning.passcode,
    discriminator: bridge.commissioning.discriminator,
    autoSubscribe: false,
    autoStateInitialize: false,
  });
  pairingSeconds = (performance.now() - t) / 1000;
  const req = Subscribe(
    {
      keepSubscriptions: true,
      minIntervalFloor: 0,
      maxIntervalCeiling: Seconds(10),
    },
    ...selectors(),
  );
  req.includeKnownVersions = true;
  req.updated = (data) => consume(data, true).then(() => {});
  subscription = await client.interaction.subscribe(req);
  ready = true;
}
Bun.serve({
  idleTimeout: 180,
  hostname: "0.0.0.0",
  port: 18124,
  async fetch(request) {
    const path = new URL(request.url).pathname;
    try {
      if (path === "/start" && request.method === "POST") {
        await start();
        return Response.json({
          ready,
          received,
          changed,
          reports,
          pairingSeconds,
        });
      }
      if (path === "/reads" && request.method === "POST") {
        const { seconds = 10, expected = 100 } = await request.json();
        const latencies = [];
        let requests = 0,
          errors = 0,
          attributes = 0;
        const t0 = performance.now();
        while (performance.now() - t0 < seconds * 1000) {
          const t = performance.now();
          try {
            const request = Read(...selectors());
            request.includeKnownVersions = true;
            const n = await consume(client.interaction.read(request));
            if (n !== expected)
              throw new Error(`Expected ${expected} values, got ${n}`);
            attributes += n;
            requests++;
            latencies.push(performance.now() - t);
          } catch (error) {
            errors++;
            console.error(error);
          }
        }
        const elapsed = (performance.now() - t0) / 1000;
        latencies.sort((a, b) => a - b);
        return Response.json({
          requests,
          errors,
          attributes,
          seconds: elapsed,
          requests_per_second: requests / elapsed,
          p50_ms: latencies[Math.floor(latencies.length * 0.5)] ?? null,
          p95_ms: latencies[Math.floor(latencies.length * 0.95)] ?? null,
        });
      }
      return Response.json({
        ready,
        received,
        changed,
        reports,
        values: values.size,
        pairingSeconds,
      });
    } catch (error) {
      console.error(error);
      return Response.json({ error: String(error) }, { status: 500 });
    }
  },
});
process.on("SIGTERM", async () => {
  subscription?.close();
  await controller?.close();
  process.exit(0);
});
console.log("Matter controller RPC ready");
