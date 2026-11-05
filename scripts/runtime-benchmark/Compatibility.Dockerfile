FROM oven/bun:1.4.2-alpine
WORKDIR /app
COPY . .
RUN bun install --frozen-lockfile && bun run build:minimum
ENV HAMH_LOOPBACK=1
# Run as root in an isolated container so the port-80 tests can bind the port.
CMD ["bun", "run", "test", "--maxWorkers=4"]
