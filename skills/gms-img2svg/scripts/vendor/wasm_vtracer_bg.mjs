let wasm;
export function __wbg_set_wasm(val) {
    wasm = val;
}

function addHeapObject(obj) {
    if (heap_next === heap.length) heap.push(heap.length + 1);
    const idx = heap_next;
    heap_next = heap[idx];

    heap[idx] = obj;
    return idx;
}

function _assertClass(instance, klass) {
    if (!(instance instanceof klass)) {
        throw new Error(`expected instance of ${klass.name}`);
    }
}

function dropObject(idx) {
    if (idx < 132) return;
    heap[idx] = heap_next;
    heap_next = idx;
}

let cachedDataViewMemory0 = null;
function getDataViewMemory0() {
    if (cachedDataViewMemory0 === null || cachedDataViewMemory0.buffer.detached === true || (cachedDataViewMemory0.buffer.detached === undefined && cachedDataViewMemory0.buffer !== wasm.memory.buffer)) {
        cachedDataViewMemory0 = new DataView(wasm.memory.buffer);
    }
    return cachedDataViewMemory0;
}

function getStringFromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return decodeText(ptr, len);
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function getObject(idx) { return heap[idx]; }

let heap = new Array(128).fill(undefined);
heap.push(undefined, null, true, false);

let heap_next = heap.length;

function passArray8ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 1, 1) >>> 0;
    getUint8ArrayMemory0().set(arg, ptr / 1);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (realloc === undefined) {
        const buf = cachedTextEncoder.encode(arg);
        const ptr = malloc(buf.length, 1) >>> 0;
        getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf);
        WASM_VECTOR_LEN = buf.length;
        return ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

function takeObject(idx) {
    const ret = getObject(idx);
    dropObject(idx);
    return ret;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

const cachedTextEncoder = new TextEncoder();

if (!('encodeInto' in cachedTextEncoder)) {
    cachedTextEncoder.encodeInto = function (arg, view) {
        const buf = cachedTextEncoder.encode(arg);
        view.set(buf);
        return {
            read: arg.length,
            written: buf.length
        };
    }
}

let WASM_VECTOR_LEN = 0;

const TracerConfigFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_tracerconfig_free(ptr >>> 0, 1));

/**
 * Color mode for the tracer
 * @enum {0 | 1}
 */
export const ColorMode = Object.freeze({
    /**
     * Full color tracing
     */
    Color: 0, "0": "Color",
    /**
     * Binary (black/white) tracing
     */
    Binary: 1, "1": "Binary",
});

/**
 * Hierarchical clustering mode
 * @enum {0 | 1}
 */
export const Hierarchical = Object.freeze({
    /**
     * Stacked layers (shapes can overlap)
     */
    Stacked: 0, "0": "Stacked",
    /**
     * Cutout mode (shapes cut holes in layers below)
     */
    Cutout: 1, "1": "Cutout",
});

/**
 * Path simplification mode
 * @enum {0 | 1 | 2}
 */
export const PathSimplifyMode = Object.freeze({
    /**
     * Polygon paths (straight lines only)
     */
    Polygon: 0, "0": "Polygon",
    /**
     * Spline curves (smooth Bezier curves)
     */
    Spline: 1, "1": "Spline",
    /**
     * No simplification (raw pixel edges)
     */
    None: 2, "2": "None",
});

/**
 * Configuration for the bitmap-to-SVG tracer.
 *
 * All parameters have sensible defaults optimized for pixel art.
 * Create with `TracerConfig::new()` and modify as needed.
 */
export class TracerConfig {
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        TracerConfigFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_tracerconfig_free(ptr, 0);
    }
    /**
     * Create a new TracerConfig with default values optimized for pixel art.
     */
    constructor() {
        const ret = wasm.tracerconfig_new();
        this.__wbg_ptr = ret >>> 0;
        TracerConfigFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * Set the color mode (Color = 0, Binary = 1)
     * @param {ColorMode} mode
     */
    setColorMode(mode) {
        wasm.tracerconfig_setColorMode(this.__wbg_ptr, mode);
    }
    /**
     * Set the hierarchical mode (Stacked = 0, Cutout = 1)
     * @param {Hierarchical} mode
     */
    setHierarchical(mode) {
        wasm.tracerconfig_setHierarchical(this.__wbg_ptr, mode);
    }
    /**
     * Set the path simplification mode (Polygon = 0, Spline = 1, None = 2)
     * @param {PathSimplifyMode} mode
     */
    setPathSimplifyMode(mode) {
        wasm.tracerconfig_setPathSimplifyMode(this.__wbg_ptr, mode);
    }
    /**
     * Filter out speckles smaller than this many pixels.
     * Default: 4. Range: 0+
     * @param {number} val
     */
    setFilterSpeckle(val) {
        wasm.tracerconfig_setFilterSpeckle(this.__wbg_ptr, val);
    }
    /**
     * Color precision for quantization (bits per channel).
     * Default: 6. Range: 1-8
     * @param {number} val
     */
    setColorPrecision(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setColorPrecision(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Color difference threshold for layer separation.
     * Default: 16. Range: 0-255
     * @param {number} val
     */
    setLayerDifference(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setLayerDifference(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Corner detection threshold in degrees.
     * Default: 60. Range: 0-180
     * @param {number} val
     */
    setCornerThreshold(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setCornerThreshold(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Minimum length for path segments.
     * Default: 4.0. Range: 3.5-10.0
     * @param {number} val
     */
    setLengthThreshold(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setLengthThreshold(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Maximum iterations for curve fitting.
     * Default: 10. Range: 1+
     * @param {number} val
     */
    setMaxIterations(val) {
        wasm.tracerconfig_setMaxIterations(this.__wbg_ptr, val);
    }
    /**
     * Splice threshold in degrees for curve joining.
     * Default: 45. Range: 0-180
     * @param {number} val
     */
    setSpliceThreshold(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setSpliceThreshold(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Decimal precision for path coordinates in SVG output.
     * Default: 2. Range: 0-8
     * @param {number} val
     */
    setPathPrecision(val) {
        try {
            const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
            wasm.tracerconfig_setPathPrecision(retptr, this.__wbg_ptr, val);
            var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
            var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
            if (r1) {
                throw takeObject(r0);
            }
        } finally {
            wasm.__wbindgen_add_to_stack_pointer(16);
        }
    }
    /**
     * Preset for pixel art: sharp edges, no curve smoothing
     */
    presetPixelArt() {
        wasm.tracerconfig_presetPixelArt(this.__wbg_ptr);
    }
    /**
     * Preset for photos: smooth curves, speckle filtering
     */
    presetPhoto() {
        wasm.tracerconfig_presetPhoto(this.__wbg_ptr);
    }
    /**
     * Preset for line art: binary mode, high contrast
     */
    presetLineArt() {
        wasm.tracerconfig_presetLineArt(this.__wbg_ptr);
    }
}
if (Symbol.dispose) TracerConfig.prototype[Symbol.dispose] = TracerConfig.prototype.free;

/**
 * Convert RGBA image data to SVG string.
 *
 * # Arguments
 * * `image_data` - Raw RGBA pixel data (4 bytes per pixel)
 * * `width` - Image width in pixels
 * * `height` - Image height in pixels
 * * `config` - Tracer configuration
 *
 * # Returns
 * SVG string on success, or error message on failure.
 *
 * # Example (JavaScript)
 * ```js
 * const config = new TracerConfig();
 * config.presetPixelArt();
 * const svg = convertImageToSvg(imageData, 64, 64, config);
 * ```
 * @param {Uint8Array} image_data
 * @param {number} width
 * @param {number} height
 * @param {TracerConfig} config
 * @returns {string}
 */
export function convertImageToSvg(image_data, width, height, config) {
    let deferred3_0;
    let deferred3_1;
    try {
        const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
        const ptr0 = passArray8ToWasm0(image_data, wasm.__wbindgen_export2);
        const len0 = WASM_VECTOR_LEN;
        _assertClass(config, TracerConfig);
        wasm.convertImageToSvg(retptr, ptr0, len0, width, height, config.__wbg_ptr);
        var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
        var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
        var r2 = getDataViewMemory0().getInt32(retptr + 4 * 2, true);
        var r3 = getDataViewMemory0().getInt32(retptr + 4 * 3, true);
        var ptr2 = r0;
        var len2 = r1;
        if (r3) {
            ptr2 = 0; len2 = 0;
            throw takeObject(r2);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
        wasm.__wbindgen_export(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Convert RGBA image data to SVG with default configuration.
 *
 * Convenience function using default settings.
 * @param {Uint8Array} image_data
 * @param {number} width
 * @param {number} height
 * @returns {string}
 */
export function convertImageToSvgDefault(image_data, width, height) {
    let deferred3_0;
    let deferred3_1;
    try {
        const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
        const ptr0 = passArray8ToWasm0(image_data, wasm.__wbindgen_export2);
        const len0 = WASM_VECTOR_LEN;
        wasm.convertImageToSvgDefault(retptr, ptr0, len0, width, height);
        var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
        var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
        var r2 = getDataViewMemory0().getInt32(retptr + 4 * 2, true);
        var r3 = getDataViewMemory0().getInt32(retptr + 4 * 3, true);
        var ptr2 = r0;
        var len2 = r1;
        if (r3) {
            ptr2 = 0; len2 = 0;
            throw takeObject(r2);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
        wasm.__wbindgen_export(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Convert RGBA image data to SVG optimized for pixel art.
 *
 * Uses polygon paths (no curves) and preserves sharp edges.
 * @param {Uint8Array} image_data
 * @param {number} width
 * @param {number} height
 * @returns {string}
 */
export function convertPixelArtToSvg(image_data, width, height) {
    let deferred3_0;
    let deferred3_1;
    try {
        const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
        const ptr0 = passArray8ToWasm0(image_data, wasm.__wbindgen_export2);
        const len0 = WASM_VECTOR_LEN;
        wasm.convertPixelArtToSvg(retptr, ptr0, len0, width, height);
        var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
        var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
        var r2 = getDataViewMemory0().getInt32(retptr + 4 * 2, true);
        var r3 = getDataViewMemory0().getInt32(retptr + 4 * 3, true);
        var ptr2 = r0;
        var len2 = r1;
        if (r3) {
            ptr2 = 0; len2 = 0;
            throw takeObject(r2);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
        wasm.__wbindgen_export(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Get the library version.
 * @returns {string}
 */
export function getVersion() {
    let deferred1_0;
    let deferred1_1;
    try {
        const retptr = wasm.__wbindgen_add_to_stack_pointer(-16);
        wasm.getVersion(retptr);
        var r0 = getDataViewMemory0().getInt32(retptr + 4 * 0, true);
        var r1 = getDataViewMemory0().getInt32(retptr + 4 * 1, true);
        deferred1_0 = r0;
        deferred1_1 = r1;
        return getStringFromWasm0(r0, r1);
    } finally {
        wasm.__wbindgen_add_to_stack_pointer(16);
        wasm.__wbindgen_export(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Initialize the WASM module. Call this once before using other functions.
 * Sets up panic hook for better error messages in browser console.
 */
export function init() {
    wasm.init();
}

/**
 * Check if the WASM module is ready.
 * @returns {boolean}
 */
export function isReady() {
    const ret = wasm.isReady();
    return ret !== 0;
}

export function __wbg_Error_52673b7de5a0ca89(arg0, arg1) {
    const ret = Error(getStringFromWasm0(arg0, arg1));
    return addHeapObject(ret);
};

export function __wbg___wbindgen_throw_dd24417ed36fc46e(arg0, arg1) {
    throw new Error(getStringFromWasm0(arg0, arg1));
};

export function __wbg_error_7534b8e9a36f1ab4(arg0, arg1) {
    let deferred0_0;
    let deferred0_1;
    try {
        deferred0_0 = arg0;
        deferred0_1 = arg1;
        console.error(getStringFromWasm0(arg0, arg1));
    } finally {
        wasm.__wbindgen_export(deferred0_0, deferred0_1, 1);
    }
};

export function __wbg_new_8a6f238a6ece86ea() {
    const ret = new Error();
    return addHeapObject(ret);
};

export function __wbg_stack_0ed75d68575b0f3c(arg0, arg1) {
    const ret = getObject(arg1).stack;
    const ptr1 = passStringToWasm0(ret, wasm.__wbindgen_export2, wasm.__wbindgen_export3);
    const len1 = WASM_VECTOR_LEN;
    getDataViewMemory0().setInt32(arg0 + 4 * 1, len1, true);
    getDataViewMemory0().setInt32(arg0 + 4 * 0, ptr1, true);
};

export function __wbindgen_object_drop_ref(arg0) {
    takeObject(arg0);
};
