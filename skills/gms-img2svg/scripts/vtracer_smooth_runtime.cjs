"use strict";

const fs = require("node:fs");
const tracer = require("./vendor/vtracer_v1");

if (process.argv.length !== 5) {
  process.stderr.write("usage: node vtracer_smooth_runtime.cjs INPUT OUTPUT OPTIONS_JSON\n");
  process.exit(1);
}

const [, , inputPath, outputPath, optionsJson] = process.argv;
try {
  const options = JSON.parse(optionsJson);
  let svg = tracer.convertBuffer(fs.readFileSync(inputPath), options);
  svg = svg.replace("<svg ", '<svg shape-rendering="geometricPrecision" ');
  fs.writeFileSync(outputPath, svg, "utf8");
} catch (error) {
  process.stderr.write(`${error && error.message ? error.message : error}\n`);
  process.exit(1);
}
