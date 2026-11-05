#!/usr/bin/env python3
"""Parse a validated SVG once into an immutable Illustrator playback cache."""

from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path.parser import parse_path

from validate_svg import audit

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
TRANSFORM_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def compose(first, second):
    a, b, c, d, e, f = first
    g, h, i, j, k, l = second
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j, a*k+c*l+e, b*k+d*l+f)


def point(matrix, value):
    x, y = value
    a, b, c, d, e, f = matrix
    return [round(a*x+c*y+e, 6), round(b*x+d*y+f, 6)]


def parse_transform(value: str):
    result = IDENTITY
    for name, raw in TRANSFORM_RE.findall(value or ""):
        values = [float(item) for item in NUMBER_RE.findall(raw)]
        name = name.lower()
        if name == "matrix" and len(values) == 6:
            current = tuple(values)
        elif name == "translate" and values:
            current = (1, 0, 0, 1, values[0], values[1] if len(values) > 1 else 0)
        elif name == "scale" and values:
            current = (values[0], 0, 0, values[1] if len(values) > 1 else values[0], 0, 0)
        elif name == "rotate" and values:
            radians = math.radians(values[0]); cosine = math.cos(radians); sine = math.sin(radians)
            rotation = (cosine, sine, -sine, cosine, 0, 0)
            if len(values) >= 3:
                cx, cy = values[1], values[2]
                current = compose((1, 0, 0, 1, cx, cy), compose(rotation, (1, 0, 0, 1, -cx, -cy)))
            else:
                current = rotation
        else:
            raise ValueError(f"Unsupported transform: {name}({raw})")
        result = compose(result, current)
    return result


def style(element: ET.Element, inherited: dict) -> dict:
    result = dict(inherited)
    declarations = {}
    for part in element.attrib.get("style", "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1); declarations[key.strip()] = value.strip()
    for key in ("fill", "stroke", "stroke-width", "fill-rule", "opacity", "fill-opacity", "stroke-opacity", "stroke-linecap", "stroke-linejoin"):
        if key in element.attrib: declarations[key] = element.attrib[key]
    result.update(declarations)
    return result


def color(value: str | None):
    if not value or value == "none": return None
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        value = "#" + "".join(char*2 for char in value[1:])
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return [int(value[index:index+2], 16) for index in (1, 3, 5)]
    match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
    if match: return [min(255, int(part)) for part in match.groups()]
    raise ValueError(f"Only solid hex/rgb colors are supported: {value}")


def gradient_coordinate(value: str | None, start: float, length: float, default: str) -> float:
    raw = (value or default).strip()
    if raw.endswith("%"):
        return start + float(raw[:-1]) * length / 100
    return float(raw)


def parse_gradients(root: ET.Element, viewbox: list[float]) -> dict[str, dict]:
    gradients: dict[str, dict] = {}
    x, y, width, height = viewbox
    for element in root.iter():
        kind = local(element.tag)
        if kind not in {"linearGradient", "radialGradient"}:
            continue
        identifier = element.attrib.get("id")
        if not identifier:
            raise ValueError("Every SVG gradient must have an id.")
        if element.attrib.get("gradientUnits", "objectBoundingBox") != "userSpaceOnUse":
            raise ValueError(f"Gradient {identifier} must use gradientUnits='userSpaceOnUse'.")
        if element.attrib.get("gradientTransform"):
            raise ValueError(f"Gradient {identifier} uses unsupported gradientTransform.")
        stops = []
        for stop in list(element):
            if local(stop.tag) != "stop":
                continue
            declarations = {}
            for part in stop.attrib.get("style", "").split(";"):
                if ":" in part:
                    key, item = part.split(":", 1)
                    declarations[key.strip()] = item.strip()
            offset_raw = stop.attrib.get("offset", "0")
            offset = float(offset_raw[:-1]) if offset_raw.endswith("%") else float(offset_raw) * 100
            stop_color = color(stop.attrib.get("stop-color", declarations.get("stop-color", "#000000")))
            opacity = float(stop.attrib.get("stop-opacity", declarations.get("stop-opacity", "1"))) * 100
            stops.append({"offset": round(max(0, min(100, offset)), 4), "color": stop_color, "opacity": round(max(0, min(100, opacity)), 4)})
        if len(stops) < 2:
            raise ValueError(f"Gradient {identifier} must contain at least two stops.")
        stops.sort(key=lambda item: item["offset"])
        if kind == "linearGradient":
            gradients[identifier] = {
                "type": "linear",
                "start": [
                    gradient_coordinate(element.attrib.get("x1"), x, width, "0%"),
                    gradient_coordinate(element.attrib.get("y1"), y, height, "0%"),
                ],
                "end": [
                    gradient_coordinate(element.attrib.get("x2"), x, width, "100%"),
                    gradient_coordinate(element.attrib.get("y2"), y, height, "0%"),
                ],
                "stops": stops,
            }
        else:
            gradients[identifier] = {
                "type": "radial",
                "center": [
                    gradient_coordinate(element.attrib.get("cx"), x, width, "50%"),
                    gradient_coordinate(element.attrib.get("cy"), y, height, "50%"),
                ],
                "radius": gradient_coordinate(element.attrib.get("r"), 0, min(width, height), "50%"),
                "stops": stops,
            }
    return gradients


def paint(value: str | None, gradients: dict[str, dict]):
    if value:
        match = re.fullmatch(r"url\(\s*#([^)\s]+)\s*\)", value.strip())
        if match:
            identifier = match.group(1)
            if identifier not in gradients:
                raise ValueError(f"Unknown SVG gradient: {identifier}")
            stops = gradients[identifier]["stops"]
            preview = stops[len(stops) // 2]["color"]
            return {"gradientId": identifier, "preview": preview}
    return color(value)


def path_data(element: ET.Element) -> str:
    name = local(element.tag); a = element.attrib
    if name == "path": return a.get("d", "")
    if name == "line": return f"M{a.get('x1',0)} {a.get('y1',0)}L{a.get('x2',0)} {a.get('y2',0)}"
    if name in {"polyline", "polygon"}:
        pairs = NUMBER_RE.findall(a.get("points", "")); commands = []
        for index in range(0, len(pairs)-1, 2): commands.append(("M" if index == 0 else "L") + pairs[index] + " " + pairs[index+1])
        return "".join(commands) + ("Z" if name == "polygon" else "")
    if name == "rect":
        x=float(a.get("x",0)); y=float(a.get("y",0)); w=float(a.get("width",0)); h=float(a.get("height",0))
        return f"M{x} {y}H{x+w}V{y+h}H{x}Z"
    if name in {"circle", "ellipse"}:
        cx=float(a.get("cx",0)); cy=float(a.get("cy",0)); rx=float(a.get("r",a.get("rx",0))); ry=float(a.get("r",a.get("ry",0)))
        k=0.5522847498; return f"M{cx-rx} {cy}C{cx-rx} {cy-k*ry} {cx-k*rx} {cy-ry} {cx} {cy-ry}C{cx+k*rx} {cy-ry} {cx+rx} {cy-k*ry} {cx+rx} {cy}C{cx+rx} {cy+k*ry} {cx+k*rx} {cy+ry} {cx} {cy+ry}C{cx-k*rx} {cy+ry} {cx-rx} {cy+k*ry} {cx-rx} {cy}Z"
    return ""


def subpaths(data: str, matrix) -> list[dict]:
    pen = RecordingPen(); parse_path(data, pen)
    output=[]; current=None; cursor=None
    def add(anchor, left=None, right=None):
        nonlocal cursor
        p=point(matrix, anchor); current["points"].append({"a":p,"l":point(matrix,left or anchor),"r":point(matrix,right or anchor)}); cursor=anchor
    for command, args in pen.value:
        if command == "moveTo":
            if current and current["points"]: output.append(current)
            current={"closed":False,"points":[]}; add(args[0])
        elif command == "lineTo": add(args[0])
        elif command == "curveTo":
            for index in range(0,len(args),3):
                c1,c2,end=args[index:index+3]; current["points"][-1]["r"]=point(matrix,c1); add(end,c2,end)
        elif command == "qCurveTo":
            for control,end in zip(args[:-1],args[1:]):
                if end is None: continue
                c1=(cursor[0]+2*(control[0]-cursor[0])/3,cursor[1]+2*(control[1]-cursor[1])/3)
                c2=(end[0]+2*(control[0]-end[0])/3,end[1]+2*(control[1]-end[1])/3)
                current["points"][-1]["r"]=point(matrix,c1); add(end,c2,end)
        elif command == "closePath":
            current["closed"]=True
            if len(current["points"])>1 and current["points"][-1]["a"]==current["points"][0]["a"]: current["points"].pop()
            output.append(current); current=None
        elif command == "endPath":
            output.append(current); current=None
    if current and current["points"]: output.append(current)
    return [item for item in output if len(item["points"]) >= 2]


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("svg",type=Path); parser.add_argument("--output-dir",type=Path,required=True); parser.add_argument("--batch-size",type=int,default=30); parser.add_argument("--job-id")
    args=parser.parse_args()
    if not 20 <= args.batch_size <= 50: raise SystemExit("--batch-size must be 20-50")
    source=args.svg.resolve(); report=audit(source)
    if report["status"]!="PASS": raise SystemExit("SVG validation failed: "+"; ".join(report["errors"]))
    root=ET.parse(source).getroot(); viewbox=[float(v) for v in NUMBER_RE.findall(root.attrib.get("viewBox",""))]
    if len(viewbox)!=4: viewbox=[0,0,float(root.attrib.get("width",0)),float(root.attrib.get("height",0))]
    gradients=parse_gradients(root,viewbox)
    atoms=[]
    def atom_identity(element: ET.Element, inherited_id: str | None, inherited_role: str | None) -> tuple[str | None, str | None, str]:
        source_id = element.attrib.get("id") or element.attrib.get("data-source-id") or inherited_id
        role = element.attrib.get("data-role") or inherited_role
        base = re.sub(r"[^0-9A-Za-z_.-]+", "_", source_id or "atom").strip("_") or "atom"
        return source_id, role, f"{base}__{len(atoms) + 1:05d}"

    def walk(element, parent_matrix=IDENTITY, inherited=None, inherited_id=None, inherited_role=None, group_path=None):
        inherited=inherited or {"fill":"#000000","stroke":"none","opacity":"1"}
        group_path=group_path or []
        matrix=compose(parent_matrix,parse_transform(element.attrib.get("transform",""))); appearance=style(element,inherited); name=local(element.tag)
        source_id, role, atom_id = atom_identity(element, inherited_id, inherited_role)
        if name == "defs":
            return
        current_group_path = group_path
        if name == "g" and element.attrib.get("id") and element.attrib.get("data-role"):
            current_group_path = group_path + [{"id": element.attrib["id"], "role": element.attrib["data-role"]}]
        if name in {"path","rect","circle","ellipse","line","polyline","polygon"}:
            paths=subpaths(path_data(element),matrix)
            if paths:
                opacity=float(appearance.get("opacity",1)); fill=paint(appearance.get("fill"),gradients); stroke=paint(appearance.get("stroke"),gradients)
                atoms.append({"kind":"path","atomId":atom_id,"sourceId":source_id,"role":role,"groupPath":current_group_path,"subpaths":paths,"style":{"fill":fill,"stroke":stroke,"strokeWidth":float(appearance.get("stroke-width",1)),"opacity":round(opacity*100,4),"evenodd":appearance.get("fill-rule")=="evenodd"}})
        elif name == "text":
            x=float(element.attrib.get("x",0)); y=float(element.attrib.get("y",0)); position=point(matrix,(x,y)); fill=color(appearance.get("fill")) or [0,0,0]
            a,b,c,d,_,_=matrix
            font_size=float(appearance.get("font-size",element.attrib.get("font-size",16)))
            lines=["".join(child.itertext()) for child in list(element) if local(child.tag)=="tspan"]
            contents="\n".join(lines) if lines else "".join(element.itertext())
            line_height=1.2
            tspans=[child for child in list(element) if local(child.tag)=="tspan"]
            if len(tspans)>1:
                dy=NUMBER_RE.findall(tspans[1].attrib.get("dy",""))
                if dy and font_size>0: line_height=float(dy[0])/font_size
            letter_spacing=NUMBER_RE.findall(element.attrib.get("letter-spacing","0"))
            atoms.append({"kind":"text","atomId":atom_id,"sourceId":source_id,"role":role,"groupPath":current_group_path,"text":{"contents":contents,"position":position,"fontFamily":appearance.get("font-family",element.attrib.get("font-family","Arial")),"fontSize":font_size*math.hypot(c,d),"fontWeight":str(element.attrib.get("font-weight","400")),"fontStyle":str(element.attrib.get("font-style","normal")),"lineHeight":line_height,"letterSpacing":float(letter_spacing[0]) if letter_spacing else 0,"rotation":round(-math.degrees(math.atan2(b,a)),6),"fill":fill,"opacity":float(appearance.get("opacity",1))*100,"anchor":appearance.get("text-anchor",element.attrib.get("text-anchor","start"))}})
        else:
            for child in list(element): walk(child,matrix,appearance,source_id,role,current_group_path)
    walk(root)
    if not atoms: raise SystemExit("No supported atoms found")
    batches=[]
    for start in range(0,len(atoms),args.batch_size): batches.append({"name":f"IMG2SVG_BATCH_{len(batches)+1:04d}","start":start,"end":min(len(atoms),start+args.batch_size)})
    job_id=re.sub(r"[^0-9A-Za-z_-]+","_",args.job_id or source.stem)[:48] or "job"
    payload={"schema":"img2svg-geometry-1.0","jobId":job_id,"source":str(source),"viewBox":viewbox,"gradients":gradients,"atoms":atoms,"batches":batches}
    output_dir=args.output_dir.resolve(); output_dir.mkdir(parents=True,exist_ok=True); target=output_dir/"geometry-cache.json"
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=output_dir,delete=False) as handle: json.dump(payload,handle,ensure_ascii=False,separators=(",",":")); temporary=Path(handle.name)
    temporary.replace(target)
    print(json.dumps({"ok":True,"cache":str(target),"atoms":len(atoms),"batches":len(batches)},ensure_ascii=False)); return 0


if __name__=="__main__": raise SystemExit(main())
