FROM oven/bun:1.4.2-alpine
WORKDIR /bench
COPY mock-home-assistant.ts .
CMD ["bun", "mock-home-assistant.ts"]
