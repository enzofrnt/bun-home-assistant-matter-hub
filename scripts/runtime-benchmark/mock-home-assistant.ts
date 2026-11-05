import type { ServerWebSocket } from "bun";

type SubscriptionData = { subscriptions: Map<number, Set<string>> };
interface FixtureState {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
  context: { id: string; user_id: null; parent_id: null };
  last_changed: string;
  last_updated: string;
}

// Synthetic Home Assistant protocol fixture. No real credentials or devices.
const count = Number(process.env.ENTITY_COUNT ?? 100);
const entities: Record<string, unknown>[] = [];
const devices: Record<string, unknown>[] = [];
const states: Record<string, FixtureState> = {};
const sockets = new Set<ServerWebSocket<SubscriptionData>>();
let sequence = 0;
let sentUpdates = 0;
let rate = 0;
let timer: ReturnType<typeof setInterval> | undefined;
const fixedDate = "2026-11-05T12:00:00.000Z";
for (let i = 0; i < count; i++) {
  const domain = i % 2 ? "switch" : "sensor";
  const entity_id = `${domain}.bench_${String(i).padStart(5, "0")}`;
  const device_id = `bench-device-${i}`;
  entities.push({
    entity_id,
    device_id,
    unique_id: `bench-${i}`,
    id: `bench-${i}`,
    platform: "benchmark",
    name: `Bench ${i}`,
    original_name: `Bench ${i}`,
    area_id: "bench",
    labels: [],
    categories: {},
    disabled_by: null,
    hidden_by: null,
    entity_category: null,
    has_entity_name: false,
  });
  devices.push({
    id: device_id,
    name: `Bench ${i}`,
    name_by_user: null,
    manufacturer: "Benchmark",
    model: "Virtual",
    model_id: "bench",
    area_id: "bench",
    labels: [],
    connections: [],
    identifiers: [["benchmark", String(i)]],
    sw_version: "1.0",
    hw_version: "1.0",
  });
  states[entity_id] = {
    entity_id,
    state: domain === "sensor" ? "20.0" : "off",
    attributes: {
      friendly_name: `Bench ${i}`,
      ...(domain === "sensor"
        ? {
            device_class: "temperature",
            unit_of_measurement: "°C",
            state_class: "measurement",
          }
        : {}),
    },
    context: { id: "fixture", user_id: null, parent_id: null },
    last_changed: fixedDate,
    last_updated: fixedDate,
  };
}
const ids = Object.keys(states);
function compressed(id: string) {
  const s = states[id];
  return { s: s.state, a: s.attributes, c: "fixture", lc: Date.now() / 1000 };
}
function setRate(value: number) {
  if (timer) clearInterval(timer);
  rate = value;
  if (!value || !count) return;
  timer = setInterval(() => {
    const changed: Record<string, unknown> = {};
    for (let j = 0; j < Math.max(1, Math.round(value / 10)); j++) {
      const id = ids[sequence++ % ids.length];
      const s = states[id];
      s.state = id.startsWith("sensor.")
        ? (20 + ((sequence / count) % 10)).toFixed(2)
        : s.state === "on"
          ? "off"
          : "on";
      s.last_changed = s.last_updated = new Date().toISOString();
      changed[id] = { "+": compressed(id) };
    }
    for (const socket of sockets) {
      for (const [subId, selected] of socket.data.subscriptions) {
        const filtered = Object.fromEntries(
          Object.entries(changed).filter(([id]) => selected.has(id)),
        );
        if (Object.keys(filtered).length) {
          socket.send(
            JSON.stringify({
              id: subId,
              type: "event",
              event: { c: filtered },
            }),
          );
          sentUpdates += Object.keys(filtered).length;
        }
      }
    }
  }, 100);
}
Bun.serve<SubscriptionData>({
  hostname: "0.0.0.0",
  port: 18123,
  async fetch(request, server) {
    const url = new URL(request.url);
    if (url.pathname === "/control") {
      if (request.method === "POST")
        setRate(Number(((await request.json()) as { rate: number }).rate));
      return Response.json({
        count,
        rate,
        sequence,
        sentUpdates,
        connections: sockets.size,
        subscriptions: [...sockets].reduce(
          (n, s) => n + s.data.subscriptions.size,
          0,
        ),
      });
    }
    if (server.upgrade(request, { data: { subscriptions: new Map() } })) return;
    return Response.json({ fixture: true, count });
  },
  websocket: {
    open(socket) {
      sockets.add(socket);
      socket.send(
        JSON.stringify({ type: "auth_required", ha_version: "2026.11.0" }),
      );
    },
    close(socket) {
      sockets.delete(socket);
    },
    message(socket, raw) {
      const message = JSON.parse(String(raw));
      if (message.type === "auth") {
        socket.send(
          JSON.stringify({ type: "auth_ok", ha_version: "2026.11.0" }),
        );
        return;
      }
      if (message.type === "ping") {
        socket.send(JSON.stringify({ id: message.id, type: "pong" }));
        return;
      }
      let result: unknown = null;
      switch (message.type) {
        case "get_config":
          result = {
            state: "RUNNING",
            components: [],
            version: "2026.11.0",
            unit_system: {},
            location_name: "Benchmark",
          };
          break;
        case "config/entity_registry/list":
          result = entities;
          break;
        case "config/device_registry/list":
          result = devices;
          break;
        case "config/area_registry/list":
          result = [{ area_id: "bench", name: "Benchmark" }];
          break;
        case "config/label_registry/list":
          result = [];
          break;
        case "get_states":
          result = Object.values(states);
          break;
        case "get_services":
          result = {};
          break;
        case "unsubscribe_events":
          socket.data.subscriptions.delete(message.subscription);
          result = true;
          break;
      }
      socket.send(
        JSON.stringify({
          id: message.id,
          type: "result",
          success: true,
          result,
        }),
      );
      if (message.type === "subscribe_entities") {
        const selected = new Set<string>(message.entity_ids ?? ids);
        socket.data.subscriptions.set(message.id, selected);
        socket.send(
          JSON.stringify({
            id: message.id,
            type: "event",
            event: {
              a: Object.fromEntries(
                [...selected]
                  .filter((id) => states[id])
                  .map((id) => [id, compressed(id)]),
              ),
              c: {},
            },
          }),
        );
      }
    },
  },
});
console.log(JSON.stringify({ fixture: "ready", count }));
