FROM node:24.19.0-alpine
WORKDIR /bench
COPY http-load.mjs .
CMD ["sleep", "infinity"]
