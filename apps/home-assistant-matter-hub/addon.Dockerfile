ARG BUN_VERSION="1.4.2"

FROM oven/bun:${BUN_VERSION}-alpine AS bunbuild

FROM ghcr.io/hassio-addons/base:18.2.1

# Copy the musl build so the runtime matches the Alpine-based add-on.
RUN apk add --no-cache libstdc++ libgcc bash
COPY --from=bunbuild /usr/local/bin/bun /usr/local/bin/bun

ENV SUPERVISOR_TOKEN=""
VOLUME /config

COPY addon.docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ARG PACKAGE_VERSION="unknown"
ENV APP_VERSION="${PACKAGE_VERSION}"
LABEL \
  io.hass.version="$PACKAGE_VERSION" \
  io.hass.type="addon" \
  io.hass.arch="aarch64|amd64"

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

CMD ["/docker-entrypoint.sh"]
