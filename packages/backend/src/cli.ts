#!/usr/bin/env bun
import "./bootstrap.js";
import "./polyfills.js";

// Finish configuring matter.js before loading modules that initialize it.
const { cli } = await import("./cli-main.js");
export { cli };
await cli(process.argv);
