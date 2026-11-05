# Running on Low-Resource Devices

This fork uses Bun and JavaScriptCore. Memory estimates from the upstream Node/V8 version do not describe this runtime. Measure the workload on your target device before selecting a memory limit.

## Runtime and architecture

The Docker images target Linux amd64 and arm64. Bun does not support 32-bit ARM, so arm/v7 images are not built.

Bun manages its JavaScript heap automatically. The upstream `heap_size_mb` add-on setting and V8's `NODE_OPTIONS=--max-old-space-size=...` do not control Bun's heap. The add-on logs when the legacy setting is ignored.

## Reducing memory usage

Expose only the entities you need and stop other memory-heavy add-ons. Splitting the same entities across several bridges adds Matter nodes in the same process and does not reduce the total entity count.

Use container memory limits to bound total process memory and monitor the result under your normal workload. A limit below the application's working set can cause an OOM kill.

## Monitoring and diagnosing OOM kills

```bash
docker stats <container>
docker inspect <container> --format '{{.State.OOMKilled}}'
dmesg | grep -i 'oom\|killed'
```

`docker stats` reports live container use. `HostConfig.Memory` is the configured limit, not the observed peak. A log ending in `Killed`, exit code 137 or `OOMKilled: true` can indicate a kernel OOM kill.

The repository includes a macOS comparison harness in `scripts/benchmark.py`. It measures development workloads; its results do not predict the memory usage of a live Home Assistant bridge or a Raspberry Pi.
