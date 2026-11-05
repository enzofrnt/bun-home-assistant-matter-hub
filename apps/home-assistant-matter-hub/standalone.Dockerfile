ARG BUN_VERSION="1.4.2"

FROM oven/bun:${BUN_VERSION}-alpine
RUN apk add --no-cache netcat-openbsd tini

ARG PACKAGE_VERSION="unknown"
ENV HAMH_STORAGE_LOCATION="/data"
ENV APP_VERSION="${PACKAGE_VERSION}"
VOLUME /data

LABEL package.version="$PACKAGE_VERSION"

RUN mkdir /install
COPY package.tgz /install/package.tgz
# Install the tarball inside a wrapper project so its "overrides" field
# applies at the project root, including transitive dependencies.
RUN printf '%s\n' \
      '{' \
      '  "name": "hamh-wrapper",' \
      '  "version": "0.0.0",' \
      '  "private": true,' \
      '  "dependencies": {' \
      '    "home-assistant-matter-hub": "file:/install/package.tgz"' \
      '  },' \
      '  "overrides": {' \
      '    "minimatch": "9.0.7",' \
      '    "path-to-regexp": "^8.4.0",' \
      '    "glob": "^13.0.0"' \
      '  }' \
      '}' > /install/package.json \
 && cd /install \
 && bun install --production \
 && ln -s /install/node_modules/.bin/home-assistant-matter-hub /usr/local/bin/home-assistant-matter-hub \
 && rm /install/package.tgz

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD wget -qO /dev/null http://localhost:8482/api/health/live || exit 1

# Bun uses JavaScriptCore and sizes its heap automatically. V8's
# NODE_OPTIONS/--max-old-space-size settings do not apply to this runtime.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["home-assistant-matter-hub", "start"]
