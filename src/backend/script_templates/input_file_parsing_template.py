ABAQUS_INP_PARSER_TEMPLATE = """
import json
import os
import re

from abaqus import *
from abaqusConstants import *
import inpParser

# =========================================================
# EDIT THESE VARIABLES BEFORE RUNNING
# =========================================================

INPUT_FILE_PATH = __INPUT_FILE_PATH__
OUTPUT_SUMMARY_JSON_PATH = __OUTPUT_SUMMARY_JSON_PATH__

# =========================================================

try:
    _STRING_TYPES = (str, unicode)  # Python 2 (Abaqus kernel)
except NameError:
    _STRING_TYPES = (str,)

# Keyword names (lowercase) whose *data* rows are bulk numeric content and
# must be reduced to inline stats instead of kept in full.
BULK_KEYWORDS = set(["node", "element", "nset", "elset", "surface"])

PROCEDURE_KEYWORDS = set([
    "static", "dynamic", "frequency", "buckle", "complex frequency",
    "steady state dynamics", "visco", "coupled temperature-displacement",
    "uncoupled temperature-displacement", "soils", "heat transfer",
    "modal dynamic", "random response", "substructure generate", "geostatic",
    "annealing",
])

LOAD_KEYWORDS = set([
    "cload", "dload", "dsload", "dsflow", "cflow", "moment", "cfilm",
    "dflux", "dsflux", "cflux",
])

OUTPUT_KEYWORDS = set([
    "output", "node output", "element output", "contact output",
    "energy output", "restart", "node file", "el file",
])


# ---------------------------------------------------------------------------
# Bulk data -> compact inline statistics (no storage, no references)
# ---------------------------------------------------------------------------

def ndarray_to_list(data):
    if data is None:
        return []
    if isinstance(data, _STRING_TYPES):
        return data
    try:
        return [ndarray_to_list(row) for row in data]
    except TypeError:
        return data


def _is_number(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def compute_bbox(rows):
    xs, ys, zs = [], [], []
    for row in rows:
        try:
            if len(row) >= 4 and all(_is_number(v) for v in row[1:4]):
                xs.append(float(row[1]))
                ys.append(float(row[2]))
                zs.append(float(row[3]))
        except (TypeError, ValueError, IndexError):
            continue
    if not xs:
        return None
    return {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)], "z": [min(zs), max(zs)]}


def summarize_generate(rows):
    flat = []
    for row in rows:
        flat.extend(row)
    flat = [v for v in flat if _is_number(v)]
    if len(flat) < 2:
        return None
    start, end = float(flat[0]), float(flat[1])
    step = float(flat[2]) if len(flat) >= 3 and flat[2] else 1.0
    count = int((end - start) // step) + 1 if step else None
    return {"generate": True, "count": count}


def summarize_bulk(rows, kind="generic", generate=False):
    rows = ndarray_to_list(rows) if not isinstance(rows, list) else rows

    if generate:
        gen = summarize_generate(rows) 
        if gen:
            return gen
        # fall through to generic handling if GENERATE parsing failed

    if not rows:
        return {"count": 0}

    stats = {"count": len(rows)}

    if kind == "node":
        bbox = compute_bbox(rows)
        if bbox:
            stats["bbox"] = bbox

    elif kind == "element":
        conn_lens = [len(row) - 1 for row in rows if row]
        if conn_lens:
            stats["nodes_per_element"] = {
                "min": min(conn_lens), "max": max(conn_lens)
            }

    elif kind == "ids":
        # flat id list (nset/elset without GENERATE, or surface defs) --
        # only the member count is kept, no actual IDs.
        flat = []
        for row in rows:
            flat.extend(row)
        numeric = [v for v in flat if _is_number(v)]
        non_numeric = [v for v in flat if not _is_number(v)]
        stats["count"] = len(flat)
        if non_numeric and not numeric:
            # e.g. set defined by referencing other set names
            stats["references_named_sets"] = True

    return stats


# ---------------------------------------------------------------------------
# Safe accessors for inpParser Keyword objects
# ---------------------------------------------------------------------------

def kw_name(kw):
    try:
        n = getattr(kw, "name", None)
        return n.lower() if isinstance(n, _STRING_TYPES) else None
    except Exception:
        return None


def kw_param(kw):
    try:
        p = getattr(kw, "parameter", None)
        return dict(p) if p else {}
    except Exception:
        return {}


def kw_data(kw):
    try:
        d = getattr(kw, "data", None)
        return d if d else []
    except Exception:
        return []


def kw_subs(kw):
    try:
        s = getattr(kw, "suboptions", None)
        return s if s else []
    except Exception:
        return []


def has_generate(p):
    for k, v in p.items():
        if str(k).lower() == "generate":
            return bool(v) if not isinstance(v, _STRING_TYPES) else True
    return False


def tally_other(container, name, data):
    bucket = container.setdefault("other_keywords", {})
    entry = bucket.setdefault(name or "unknown", {"occurrences": 0, "data_lines": 0})
    entry["occurrences"] += 1
    try:
        entry["data_lines"] += len(data)
    except TypeError:
        pass


# ---------------------------------------------------------------------------
# PART / orphan-mesh INSTANCE body: nodes, elements, sets, sections, surfaces
# ---------------------------------------------------------------------------

def process_container_body(subs, container):
    for kw in subs:
        n = kw_name(kw)
        p = kw_param(kw)
        d = kw_data(kw)

        if n == "node":
            container["nodes"] = summarize_bulk(d, kind="node")
            nset = p.get("nset")
            if nset:
                container.setdefault("nsets", {})[nset] = summarize_bulk(
                    d, kind="ids", generate=has_generate(p))

        elif n == "element":
            etype = p.get("type", "UNKNOWN")
            elset = p.get("elset")
            stats = summarize_bulk(d, kind="element")
            container.setdefault("elements", {}).setdefault("by_type", {})[etype] = stats
            if elset:
                container.setdefault("elsets", {})[elset] = summarize_bulk(
                    d, kind="ids", generate=has_generate(p))

        elif n == "nset":
            set_name = p.get("nset", "SET")
            container.setdefault("nsets", {})[set_name] = summarize_bulk(
                d, kind="ids", generate=has_generate(p))

        elif n == "elset":
            set_name = p.get("elset", "SET")
            container.setdefault("elsets", {})[set_name] = summarize_bulk(
                d, kind="ids", generate=has_generate(p))

        elif n == "surface":
            sname = p.get("name", "SURFACE")
            container.setdefault("surfaces", {})[sname] = {
                "type": p.get("type", "ELEMENT"),
                "definition": summarize_bulk(d, kind="ids"),
            }

        elif n and n.endswith("section"):
            container.setdefault("sections", []).append({
                "type": n, "elset": p.get("elset"), "material": p.get("material"),
                "parameters": p,
            })

        elif n == "orientation":
            container.setdefault("orientations", []).append(
                {"name": p.get("name"), "parameters": p, "data": ndarray_to_list(d)})

        elif n == "rigid body":
            container.setdefault("rigid_bodies", []).append(
                {"parameters": p, "data": ndarray_to_list(d)})

        else:
            tally_other(container, n, d)


# ---------------------------------------------------------------------------
# MATERIAL
# ---------------------------------------------------------------------------

def process_material(kw):
    p = kw_param(kw)
    name = p.get("name", "MATERIAL")
    mat = {"name": name}
    for sub in kw_subs(kw):
        sn = kw_name(sub)
        if not sn:
            continue
        mat[sn.replace(" ", "_")] = {
            "parameters": kw_param(sub),
            "data": ndarray_to_list(kw_data(sub)),
        }
    return name, mat


# ---------------------------------------------------------------------------
# ASSEMBLY / INSTANCE / constraints
# ---------------------------------------------------------------------------

def process_coupling(kw):
    entry = {"name": kw_param(kw).get("name"), "parameters": kw_param(kw),
             "data": ndarray_to_list(kw_data(kw))}
    for sub in kw_subs(kw):
        sn = kw_name(sub)
        if sn:
            entry[sn] = {"parameters": kw_param(sub), "data": ndarray_to_list(kw_data(sub))}
    return entry


def process_assembly(kw):
    asm = {"instances": {}, "nsets": {}, "elsets": {}, "surfaces": {},
           "ties": [], "couplings": [], "rigid_bodies": []}

    for sub in kw_subs(kw):
        sn = kw_name(sub)
        sp = kw_param(sub)
        sd = kw_data(sub)

        if sn == "instance":
            iname = sp.get("name", "INSTANCE")
            rows = ndarray_to_list(sd)
            inst = {"part": sp.get("part"),
                    "translate": rows[0] if len(rows) >= 1 else None,
                    "rotate": rows[1] if len(rows) >= 2 else None}
            own_mesh = {}
            process_container_body(kw_subs(sub), own_mesh)
            if own_mesh:
                inst["own_mesh"] = own_mesh  # orphan-mesh instance (no PART=)
            asm["instances"][iname] = inst

        elif sn == "nset":
            set_name = sp.get("nset", "SET")
            asm["nsets"][set_name] = summarize_bulk(sd, kind="ids", generate=has_generate(sp))

        elif sn == "elset":
            set_name = sp.get("elset", "SET")
            asm["elsets"][set_name] = summarize_bulk(sd, kind="ids", generate=has_generate(sp))

        elif sn == "surface":
            sname = sp.get("name", "SURFACE")
            asm["surfaces"][sname] = {
                "type": sp.get("type", "ELEMENT"),
                "definition": summarize_bulk(sd, kind="ids"),
            }

        elif sn == "tie":
            asm["ties"].append({"name": sp.get("name"), "parameters": sp,
                                 "data": ndarray_to_list(sd)})

        elif sn == "coupling":
            asm["couplings"].append(process_coupling(sub))

        elif sn == "rigid body":
            asm["rigid_bodies"].append({"parameters": sp, "data": ndarray_to_list(sd)})

        else:
            tally_other(asm, sn, sd)

    return asm


# ---------------------------------------------------------------------------
# STEP
# ---------------------------------------------------------------------------

def process_step(kw, index):
    p = kw_param(kw)
    step = {"name": p.get("name", "Step-{}".format(index)), "parameters": p,
            "procedure": None, "procedure_parameters": None,
            "boundary_conditions": [], "loads": [], "output_requests": []}

    for sub in kw_subs(kw):
        sn = kw_name(sub)
        sp = kw_param(sub)
        sd = ndarray_to_list(kw_data(sub))

        if sn in PROCEDURE_KEYWORDS:
            step["procedure"] = sn
            step["procedure_parameters"] = sp
        elif sn == "boundary":
            step["boundary_conditions"].append({"parameters": sp, "data": sd})
        elif sn in LOAD_KEYWORDS:
            step["loads"].append({"type": sn, "parameters": sp, "data": sd})
        elif sn in OUTPUT_KEYWORDS:
            variables = sorted(set(tok for row in sd for tok in row if tok))
            step["output_requests"].append({"type": sn, "parameters": sp, "variables": variables})
        else:
            tally_other(step, sn, sd)

    return step


# ---------------------------------------------------------------------------
# Top-level model
# ---------------------------------------------------------------------------

def build_model(keyword_sequence):
    model = {
        "heading": [],
        "parts": {},
        "assembly": None,
        "materials": {},
        "steps": [],
        "amplitudes": {},
        "surface_interactions": {},
        "contact_pairs": [],
        "root": {},
    }
    root_container = {}

    for kw in keyword_sequence:
        n = kw_name(kw)
        p = kw_param(kw)
        d = kw_data(kw)

        if n == "heading":
            model["heading"].extend(ndarray_to_list(d))

        elif n == "part":
            pname = p.get("name", "PART-{}".format(len(model["parts"]) + 1))
            container = {}
            process_container_body(kw_subs(kw), container)
            model["parts"][pname] = container

        elif n == "assembly":
            model["assembly"] = process_assembly(kw)

        elif n == "material":
            mname, mat = process_material(kw)
            model["materials"][mname] = mat

        elif n == "step":
            model["steps"].append(process_step(kw, len(model["steps"]) + 1))

        elif n == "amplitude":
            aname = p.get("name", "AMPLITUDE-{}".format(len(model["amplitudes"]) + 1))
            model["amplitudes"][aname] = {"parameters": p, "definition": ndarray_to_list(d)}

        elif n == "surface interaction":
            siname = p.get("name", "INTERACTION-{}".format(len(model["surface_interactions"]) + 1))
            entry = {"parameters": p}
            for sub in kw_subs(kw):
                sn = kw_name(sub)
                if sn:
                    entry[sn.replace(" ", "_")] = {
                        "parameters": kw_param(sub), "data": ndarray_to_list(kw_data(sub))}
            model["surface_interactions"][siname] = entry

        elif n == "contact pair":
            model["contact_pairs"].append({"parameters": p, "data": ndarray_to_list(d)})

        elif n in BULK_KEYWORDS:
            # flat .inp with no *PART wrapper: mesh sits at root level
            process_container_body([kw], root_container)

        else:
            tally_other(model, n, d)

    if root_container:
        model["root"] = root_container

    return model


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def parse_inp_file(inp_path):
    if not os.path.isfile(inp_path):
        raise IOError("Input file not found: {}".format(inp_path))

    input_file = inpParser.InputFile(inp_path)
    try:
        keyword_sequence = input_file.parse(
            organize=True, verbose=False, bulk=True, usePyArray=True)
    except Exception as e:
        raise RuntimeError("Failed to parse input file '{}': {}".format(inp_path, str(e)))

    model = build_model(keyword_sequence)
    model["_meta"] = {
        "source_file": inp_path,
        "part_names": list(model["parts"].keys()),
        "material_names": list(model["materials"].keys()),
        "step_names": [s["name"] for s in model["steps"]],
        "instance_names": list(model["assembly"]["instances"].keys()) if model["assembly"] else [],
        "note": (
            "Bulk numeric blocks (nodes/elements/nsets/elsets/surfaces) are "
            "represented as inline statistics only (count, bbox for nodes, "
            "nodes_per_element for elements). No individual node IDs, "
            "element IDs, sample rows, or raw arrays are included anywhere, "
            "and no separate geometry file exists."
        ),
    }

    return model


def main():
    inp_path = INPUT_FILE_PATH
    summary_path = OUTPUT_SUMMARY_JSON_PATH 

    try:
        summary = parse_inp_file(inp_path)
    except (IOError, RuntimeError) as e:
        print("ERROR: {}".format(str(e)))
        return

    with open(summary_path, "w") as f:
       json.dump(summary, f, default=str)

        
    print("Parts: {}".format(summary["_meta"]["part_names"]))
    print("Materials: {}".format(summary["_meta"]["material_names"]))
    print("Steps: {}".format(summary["_meta"]["step_names"]))
    print("Instances: {}".format(summary["_meta"]["instance_names"]))
    print("Summary saved to '{}'.".format(summary_path))


if __name__ == "__main__":
    main()
"""
