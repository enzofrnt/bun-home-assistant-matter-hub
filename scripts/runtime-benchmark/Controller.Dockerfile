FROM bun-home-assistant-matter-hub:compatibility-tests
COPY matter-controller.mjs /app/packages/backend/runtime-matter-controller.mjs
ENTRYPOINT ["bun", "/app/packages/backend/runtime-matter-controller.mjs"]
