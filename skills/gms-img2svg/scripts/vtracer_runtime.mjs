import fs from "node:fs";
import * as bindings from "./vendor/wasm_vtracer_bg.mjs";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

if (process.argv.length !== 7) {
  fail("usage: node vtracer_runtime.mjs INPUT.rgba WIDTH HEIGHT CONFIG.json OUTPUT.svg");
}

const [, , rawPath, widthText, heightText, configPath, outputPath] = process.argv;
const width = Number.parseInt(widthText, 10);
const height = Number.parseInt(heightText, 10);
if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
  fail("width and height must be positive integers");
}

const raw = fs.readFileSync(rawPath);
if (raw.length !== width * height * 4) {
  fail(`invalid RGBA byte length: expected ${width * height * 4}, got ${raw.length}`);
}

const options = JSON.parse(fs.readFileSync(configPath, "utf8"));
const wasmBytes = fs.readFileSync(new URL("./vendor/wasm_vtracer_bg.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiate(wasmBytes, {
  "./wasm_vtracer_bg.js": bindings,
});
bindings.__wbg_set_wasm(instance.exports);
instance.exports.__wbindgen_start();

const tracer = new bindings.TracerConfig();
try {
  if (options.mode === "lineart") tracer.presetLineArt();
  else if (options.mode === "pixel") tracer.presetPixelArt();
  else tracer.presetPhoto();

  if (options.mode !== "lineart") tracer.setColorMode(0);
  tracer.setHierarchical(options.mode === "pixel" ? 0 : 1);
  tracer.setPathSimplifyMode(options.mode === "pixel" ? 0 : 1);

  const detail = Math.max(0, Math.min(1, Number(options.detail) / 100));
  const smoothing = Math.max(0, Math.min(1, Number(options.smoothing) / 100));
  tracer.setFilterSpeckle(Math.round(1 + smoothing * 10 + (1 - detail) * 8));
  tracer.setColorPrecision(Math.max(1, Math.min(8, Number(options.colorPrecision))));
  tracer.setLayerDifference(Math.round(12 + smoothing * 24 + (1 - detail) * 16));
  tracer.setCornerThreshold(Math.round(35 + smoothing * 55));
  tracer.setLengthThreshold(3.5 + smoothing * 2.5);
  tracer.setMaxIterations(Math.round(10 + detail * 12));
  tracer.setSpliceThreshold(Math.round(45 + smoothing * 45));
  tracer.setPathPrecision(3);

  let svg = bindings.convertImageToSvg(new Uint8Array(raw), width, height, tracer);
  if (!/<svg(?:\s|>)/i.test(svg)) {
    fail(`vtracer did not return SVG XML: ${svg.slice(0, 160)}`);
  }
  svg = svg.replace("<svg ", '<svg shape-rendering="geometricPrecision" ');
  fs.writeFileSync(outputPath, svg, "utf8");
} finally {
  tracer.free();
}
