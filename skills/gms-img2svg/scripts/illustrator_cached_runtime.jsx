#target illustrator
(function () {
  var config = IMG2SVG_CONFIG;
  var cacheFile = new File(config.cachePath);
  var outputAI = new File(config.outputAI);
  var outputPNG = new File(config.outputPNG);
  var document = null;
  var root = null;
  var cache = null;
  var gradientObjects = {};

  function fail(message) {
    throw new Error(message);
  }

  function readCache() {
    if (!cacheFile.exists) fail("Geometry cache does not exist.");
    cacheFile.encoding = "UTF-8";
    if (!cacheFile.open("r")) fail("Could not open geometry cache.");
    var raw = cacheFile.read();
    cacheFile.close();
    return eval("(" + raw + ")");
  }

  function sameFile(left, right) {
    try {
      return left.fsName.toLowerCase() === right.fsName.toLowerCase();
    } catch (error) {
      return false;
    }
  }

  function documentIsOutput() {
    try {
      return sameFile(document.fullName, outputAI);
    } catch (error) {
      return false;
    }
  }

  function findTopLevelGroup(name) {
    var found = null;
    for (var index = 0; index < document.groupItems.length; index += 1) {
      var item = document.groupItems[index];
      if (item.name !== name) continue;
      if (item.parent.typename !== "Layer" && item.parent.typename !== "Document") continue;
      if (found !== null) fail("Multiple root groups named " + name + " were found; repair the document before resuming.");
      found = item;
    }
    return found;
  }

  function findChildGroup(container, name) {
    for (var index = 0; index < container.groupItems.length; index += 1) {
      if (container.groupItems[index].name === name && container.groupItems[index].parent === container) return container.groupItems[index];
    }
    return null;
  }

  function semanticContainer(batchGroup, atom) {
    var container = batchGroup;
    var path = atom.groupPath || [];
    for (var index = 0; index < path.length; index += 1) {
      var descriptor = path[index];
      var group = findChildGroup(container, descriptor.id);
      if (group === null) {
        group = container.groupItems.add();
        group.name = descriptor.id;
        group.note = "source=" + descriptor.id + (descriptor.role ? "|role=" + descriptor.role : "");
      }
      container = group;
    }
    return container;
  }

  function rgb(values) {
    var value = new RGBColor();
    value.red = values[0];
    value.green = values[1];
    value.blue = values[2];
    return value;
  }

  function findDocumentGradient(name) {
    for (var index = 0; index < document.gradients.length; index += 1) {
      if (document.gradients[index].name === name) return document.gradients[index];
    }
    return null;
  }

  function stableGradientName(identifier) {
    var source = cache.jobId + "_" + identifier;
    var hash = 0;
    for (var index = 0; index < source.length; index += 1) {
      hash = ((hash << 5) - hash + source.charCodeAt(index)) & 0x7fffffff;
    }
    var readable = identifier.replace(/[^0-9A-Za-z_]+/g, "_").substring(0, 14);
    return "I2S_" + readable + "_" + hash.toString(36);
  }

  function illustratorGradient(identifier) {
    if (gradientObjects[identifier]) return gradientObjects[identifier];
    var definition = cache.gradients[identifier];
    if (!definition) fail("Gradient definition is missing: " + identifier);
    var name = stableGradientName(identifier);
    var gradient = findDocumentGradient(name);
    if (gradient === null) {
      gradient = document.gradients.add();
      gradient.name = name;
      gradient.type = definition.type === "radial" ? GradientType.RADIAL : GradientType.LINEAR;
      while (gradient.gradientStops.length < definition.stops.length) gradient.gradientStops.add();
      while (gradient.gradientStops.length > definition.stops.length) gradient.gradientStops[gradient.gradientStops.length - 1].remove();
      for (var index = 0; index < definition.stops.length; index += 1) {
        var source = definition.stops[index];
        var target = gradient.gradientStops[index];
        target.rampPoint = source.offset;
        target.color = rgb(source.color);
        target.opacity = source.opacity;
      }
    }
    gradientObjects[identifier] = gradient;
    return gradient;
  }

  function paintColor(paint, mapper) {
    if (paint instanceof Array) return rgb(paint);
    var definition = cache.gradients[paint.gradientId];
    var result = new GradientColor();
    result.gradient = illustratorGradient(paint.gradientId);
    if (definition.type === "radial") {
      result.origin = mapper.point(definition.center);
      result.length = definition.radius * mapper.scale;
    } else {
      var start = mapper.point(definition.start);
      var end = mapper.point(definition.end);
      var deltaX = end[0] - start[0];
      var deltaY = end[1] - start[1];
      result.origin = start;
      result.length = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
      try { result.angle = Math.atan2(deltaY, deltaX) * 180 / Math.PI; } catch (angleError) {}
    }
    return result;
  }

  function equalPoints(left, right) {
    return Math.abs(left[0] - right[0]) < 0.0001 && Math.abs(left[1] - right[1]) < 0.0001;
  }

  function makeMapper(cache) {
    var viewBox = cache.viewBox;
    var board = document.artboards[document.artboards.getActiveArtboardIndex()].artboardRect;
    var boardWidth = board[2] - board[0];
    var boardHeight = board[1] - board[3];
    var sourceWidth = viewBox[2];
    var sourceHeight = viewBox[3];
    if (sourceWidth <= 0 || sourceHeight <= 0) fail("Geometry cache has an invalid viewBox.");
    var scale = Math.min(
      boardWidth * config.maxWidthFraction / sourceWidth,
      boardHeight * config.maxHeightFraction / sourceHeight
    );
    if (!isFinite(scale) || scale <= 0) fail("Could not calculate playback scale.");
    var width = sourceWidth * scale;
    var height = sourceHeight * scale;
    var marginX = boardWidth * (1 - config.maxWidthFraction) / 2;
    var marginY = boardHeight * (1 - config.maxHeightFraction) / 2;
    var left = board[0] + (boardWidth - width) / 2;
    var top = board[1] - (boardHeight - height) / 2;
    if (config.placement === "top-left") {
      left = board[0] + marginX; top = board[1] - marginY;
    } else if (config.placement === "top-right") {
      left = board[2] - marginX - width; top = board[1] - marginY;
    } else if (config.placement === "bottom-left") {
      left = board[0] + marginX; top = board[3] + marginY + height;
    } else if (config.placement === "bottom-right") {
      left = board[2] - marginX - width; top = board[3] + marginY + height;
    }
    return {
      scale: scale,
      point: function (value) {
        return [
          left + (value[0] - viewBox[0]) * scale,
          top - (value[1] - viewBox[1]) * scale
        ];
      }
    };
  }

  function applyPathStyle(path, style, mapper) {
    path.filled = style.fill !== null;
    if (path.filled) path.fillColor = paintColor(style.fill, mapper);
    path.stroked = style.stroke !== null;
    if (path.stroked) {
      path.strokeColor = paintColor(style.stroke, mapper);
      path.strokeWidth = style.strokeWidth * mapper.scale;
    }
    path.opacity = style.opacity;
    try { path.evenodd = style.evenodd; } catch (error) {}
  }

  function applyIdentity(item, atom) {
    if (atom.atomId) item.name = atom.atomId;
    var details = [];
    if (atom.sourceId) details.push("source=" + atom.sourceId);
    if (atom.role) details.push("role=" + atom.role);
    if (details.length) item.note = details.join("|");
  }

  function wireframeStyle(style, mapper) {
    var visibleFill = style.fill && style.fill.gradientId ? style.fill.preview : style.fill;
    var visibleStroke = style.stroke && style.stroke.gradientId ? style.stroke.preview : style.stroke;
    return {
      fill: null,
      stroke: visibleStroke !== null ? visibleStroke : (visibleFill !== null ? visibleFill : [128, 128, 128]),
      strokeWidth: config.wireframeStrokeWidth / mapper.scale,
      opacity: Math.max(55, style.opacity),
      evenodd: style.evenodd
    };
  }

  function drawSubpath(path, subpath, style, mapper) {
    var useEntirePath = subpath.points.length <= 10;
    var index;
    if (useEntirePath) {
      for (index = 1; index < subpath.points.length; index += 1) {
        var previous = mapper.point(subpath.points[index - 1].a);
        var current = mapper.point(subpath.points[index].a);
        var deltaX = current[0] - previous[0];
        var deltaY = current[1] - previous[1];
        if (Math.sqrt(deltaX * deltaX + deltaY * deltaY) < 2) {
          useEntirePath = false;
          break;
        }
      }
    }
    if (useEntirePath) {
      var anchors = [];
      for (index = 0; index < subpath.points.length; index += 1) {
        anchors.push(mapper.point(subpath.points[index].a));
      }
      path.setEntirePath(anchors);
    }
    for (index = 0; index < subpath.points.length; index += 1) {
      if (!useEntirePath && index > 0 && index % 96 === 0) $.sleep(1);
      var sourcePoint = subpath.points[index];
      var targetPoint = useEntirePath ? path.pathPoints[index] : path.pathPoints.add();
      targetPoint.anchor = mapper.point(sourcePoint.a);
      targetPoint.leftDirection = mapper.point(sourcePoint.l);
      targetPoint.rightDirection = mapper.point(sourcePoint.r);
      targetPoint.pointType = equalPoints(sourcePoint.l, sourcePoint.r) ? PointType.CORNER : PointType.SMOOTH;
    }
    path.closed = subpath.closed;
    applyPathStyle(path, style, mapper);
  }

  function drawPath(container, atom, mapper, useWireframe) {
    var appearance = useWireframe ? wireframeStyle(atom.style, mapper) : atom.style;
    if (atom.subpaths.length === 1) {
      var path = container.pathItems.add();
      drawSubpath(path, atom.subpaths[0], appearance, mapper);
      applyIdentity(path, atom);
      return;
    }
    var compound = container.compoundPathItems.add();
    for (var index = 0; index < atom.subpaths.length; index += 1) {
      drawSubpath(compound.pathItems.add(), atom.subpaths[index], appearance, mapper);
    }
    applyIdentity(compound, atom);
  }

  function drawText(container, atom, mapper, hidden) {
    var data = atom.text;
    var frame = container.textFrames.pointText(mapper.point(data.position));
    frame.contents = data.contents.replace(/\n/g, "\r");
    frame.opacity = data.opacity;
    var range = frame.textRange;
    range.characterAttributes.size = data.fontSize * mapper.scale;
    range.characterAttributes.fillColor = rgb(data.fill);
    try { range.characterAttributes.textFont = matchingFont(data.fontFamily, data.fontWeight, data.fontStyle); } catch (fontError) {}
    try {
      range.characterAttributes.autoLeading = false;
      range.characterAttributes.leading = data.fontSize * (data.lineHeight || 1.2) * mapper.scale;
      range.characterAttributes.tracking = Math.round((data.letterSpacing || 0) / data.fontSize * 1000);
    } catch (spacingError) {}
    if (data.anchor === "middle") range.paragraphAttributes.justification = Justification.CENTER;
    else if (data.anchor === "end") range.paragraphAttributes.justification = Justification.RIGHT;
    else range.paragraphAttributes.justification = Justification.LEFT;
    if (data.rotation) frame.rotate(data.rotation);
    applyIdentity(frame, atom);
    if (hidden) frame.opacity = 0;
  }

  function matchingFont(family, weight, fontStyle) {
    try { return app.textFonts.getByName(family); } catch (exactError) {}
    var wanted = String(family || "").toLowerCase().replace(/\s+/g, "");
    var numericWeight = parseInt(weight || "400", 10);
    var wantsItalic = String(fontStyle || "").toLowerCase().indexOf("italic") >= 0;
    var best = null;
    var bestScore = -999;
    for (var index = 0; index < app.textFonts.length; index += 1) {
      var candidate = app.textFonts[index];
      var candidateFamily = String(candidate.family || "").toLowerCase().replace(/\s+/g, "");
      var candidateName = String(candidate.name || "").toLowerCase().replace(/\s+/g, "");
      if (candidateFamily !== wanted && candidateName.indexOf(wanted) < 0) continue;
      var style = String(candidate.style || "").toLowerCase();
      var score = candidateFamily === wanted ? 20 : 10;
      var isItalic = style.indexOf("italic") >= 0 || style.indexOf("oblique") >= 0;
      if (isItalic === wantsItalic) score += 4;
      if (numericWeight <= 300 && (style.indexOf("light") >= 0 || style.indexOf("thin") >= 0)) score += 5;
      else if (numericWeight >= 600 && (style.indexOf("bold") >= 0 || style.indexOf("demi") >= 0 || style.indexOf("semibold") >= 0)) score += 5;
      else if (numericWeight > 300 && numericWeight < 600 && (style.indexOf("regular") >= 0 || style.indexOf("roman") >= 0 || style.indexOf("book") >= 0)) score += 5;
      if (score > bestScore) { best = candidate; bestScore = score; }
    }
    if (best !== null) return best;
    return app.textFonts.getByName("ArialMT");
  }

  function drawAtom(container, atom, mapper, useWireframe) {
    if (atom.kind === "path") drawPath(container, atom, mapper, useWireframe);
    else if (atom.kind === "text") drawText(container, atom, mapper, useWireframe);
    else fail("Unsupported cache atom: " + atom.kind);
  }

  function findNamedPageItem(container, name) {
    for (var index = 0; index < container.pageItems.length; index += 1) {
      if (container.pageItems[index].name === name) return container.pageItems[index];
    }
    for (var groupIndex = 0; groupIndex < container.groupItems.length; groupIndex += 1) {
      var group = container.groupItems[groupIndex];
      if (group.parent !== container) continue;
      var nested = findNamedPageItem(group, name);
      if (nested !== null) return nested;
    }
    return null;
  }

  function paintAtom(item, atom, mapper) {
    if (atom.kind === "text") {
      item.opacity = atom.text.opacity;
      return;
    }
    if (item.typename === "PathItem") {
      applyPathStyle(item, atom.style, mapper);
      return;
    }
    if (item.typename === "CompoundPathItem") {
      for (var index = 0; index < item.pathItems.length; index += 1) {
        applyPathStyle(item.pathItems[index], atom.style, mapper);
      }
      return;
    }
    fail("Cannot paint atom " + atom.atomId + " from " + item.typename);
  }

  function saveCheckpoint() {
    if (outputAI.exists && !documentIsOutput()) {
      fail("Output AI already exists and is not the active document. Refusing to overwrite it.");
    }
    if (documentIsOutput()) {
      document.save();
      return;
    }
    var options = new IllustratorSaveOptions();
    options.pdfCompatible = true;
    options.compressed = true;
    document.saveAs(outputAI, options);
  }

  function exportPNG() {
    if (outputPNG.exists && !config.resume) {
      fail("Output PNG already exists. Refusing to overwrite it without --resume.");
    }
    var options = new ExportOptionsPNG24();
    options.antiAliasing = true;
    options.transparency = true;
    options.artBoardClipping = true;
    options.horizontalScale = 100;
    options.verticalScale = 100;
    document.exportFile(outputPNG, ExportType.PNG24, options);
  }

  try {
    if (app.documents.length < 1) fail("Open the target Illustrator document first.");
    var majorVersion = parseInt(app.version.split(".")[0], 10);
    if (majorVersion < 30 && !config.compatibilityProbed) {
      fail("Illustrator " + app.version + " requires a passing per-file compatibility probe.");
    }
    document = app.activeDocument;
    if (outputAI.exists && !config.resume && !documentIsOutput()) {
      fail("Output AI already exists. Use a new path or --resume.");
    }
    cache = readCache();
    if (!cache.gradients) cache.gradients = {};
    if (cache.schema !== "img2svg-geometry-1.0") fail("Unsupported geometry cache schema.");
    var mapper = makeMapper(cache);
    var rootName = "IMG2SVG_" + cache.jobId;
    root = findTopLevelGroup(rootName);
    if (root === null) {
      root = document.groupItems.add();
      root.name = rootName;
      root.note = "img2svg immutable geometry playback: " + cache.source;
    } else if (!config.resume) {
      fail("The target document already contains " + rootName + ". Use --resume or a new job id.");
    }

    var completed = 0;
    var created = 0;
    for (var batchIndex = 0; batchIndex < cache.batches.length; batchIndex += 1) {
      var batch = cache.batches[batchIndex];
      var existingBatch = findChildGroup(root, batch.name);
      if (existingBatch !== null) {
        completed += 1;
        continue;
      }
      var batchGroup = root.groupItems.add();
      batchGroup.name = batch.name;
      try {
        for (var atomIndex = batch.start; atomIndex < batch.end; atomIndex += 1) {
          var atom = cache.atoms[atomIndex];
          drawAtom(semanticContainer(batchGroup, atom), atom, mapper, config.twoPassLive);
          var creationDelay = config.twoPassLive ? config.wireframeDelayMs : config.liveDelayMs;
          if (creationDelay > 0) {
            app.redraw();
            $.sleep(creationDelay);
          }
        }
        batchGroup.note = (config.twoPassLive ? "WIREFRAME|" : "COMPLETE|") + batch.start + "|" + batch.end;
        saveCheckpoint();
        completed += 1;
        created += 1;
      } catch (batchError) {
        try { batchGroup.remove(); } catch (cleanupError) {}
        throw batchError;
      }
    }
    if (config.twoPassLive) {
      completed = 0;
      for (batchIndex = 0; batchIndex < cache.batches.length; batchIndex += 1) {
        batch = cache.batches[batchIndex];
        batchGroup = findChildGroup(root, batch.name);
        if (batchGroup === null) fail("Wireframe batch is missing: " + batch.name);
        if (batchGroup.note.indexOf("COMPLETE|") === 0) {
          completed += 1;
          continue;
        }
        for (atomIndex = batch.start; atomIndex < batch.end; atomIndex += 1) {
          var atom = cache.atoms[atomIndex];
          var target = findNamedPageItem(batchGroup, atom.atomId);
          if (target === null) fail("Wireframe atom is missing: " + atom.atomId);
          paintAtom(target, atom, mapper);
          if (config.paintDelayMs > 0) {
            app.redraw();
            $.sleep(config.paintDelayMs);
          }
        }
        batchGroup.note = "COMPLETE|" + batch.start + "|" + batch.end;
        saveCheckpoint();
        completed += 1;
      }
    }
    exportPNG();
    document.save();
    app.redraw();
    return "OK|version=" + app.version + "|root=" + rootName + "|batches=" + completed + "|created=" + created +
      "|playback=" + (config.twoPassLive ? "wireframe-paint" : "single-pass");
  } catch (error) {
    return "ERROR|version=" + app.version + "|message=" + error.message + "|line=" + error.line;
  }
})();
