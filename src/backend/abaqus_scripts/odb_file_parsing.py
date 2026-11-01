"""
extract_odb_stats.py

Extracts, for four specific output fields (Von Mises Stress, Max Principal
Stress, Equivalent Plastic Strain, Displacement Magnitude), the MAX value
and the node it occurs at -- per PART INSTANCE, per STEP, per FRAME --
from an Abaqus .odb file, and writes ONE markdown file containing one
table per field. Each table has all steps/frames as rows and one
Value (+Node) column pair per part.

-------------------------------------------------------------------------
WHY "PART" MEANS "PART INSTANCE" HERE
-------------------------------------------------------------------------
Field output (stress, displacement, ...) is stored against elements/nodes
in odb.rootAssembly.instances, not against odb.parts (odb.parts only holds
the undeformed mesh template, no results). So "part" / column group here
means "part instance in the assembly". Parts with multiple section points
(e.g. shells with top/bottom) get one column pair per section point,
labeled "PART (SP<n>)" / "PART (SP<n>) Node".

-------------------------------------------------------------------------
FIELDS EXTRACTED
-------------------------------------------------------------------------
Only MAX values are extracted, for exactly four fields: Von Mises Stress,
Max Principal Stress, Equivalent Plastic Strain (PEEQ), and Displacement
Magnitude. That's 4 tables total in the output file. Edit FIELD_REQUESTS
below to add/remove/change fields.

-------------------------------------------------------------------------
ABOUT THE 75% AVERAGING THRESHOLD RE-IMPLEMENTATION
-------------------------------------------------------------------------
odbAccess does not expose Abaqus/CAE's internal averaging algorithm --
that lives in the Visualization module's display code, not the data-access
API. Abaqus's own docs describe the *behavior* but not the exact formula:

    "Extrapolated output database values at nodes common to two or more
    elements are averaged conditionally ... If the difference between the
    individual element contributions is greater than the threshold,
    averaging will not be performed (i.e., a discontinuity is assumed)."

This script re-implements that documented behavior:
  1. Extrapolate integration-point values to nodes, per element
     (position=ELEMENT_NODAL) -- raw, unaveraged.
  2. Group all element contributions that land on the same node.
  3. For a node with N>1 contributions: range = max-min of those
     contributions, denom = the largest absolute contribution at that
     node. If 100*range/denom <= AVERAGING_THRESHOLD_PERCENT, merge into
     one averaged nodal value. Otherwise keep contributions SEPARATE
     (the visible color discontinuity CAE shows), each contributing
     independently to the part's min/avg/max.
  4. Natively nodal fields (U, RF, ...) are read directly at
     position=NODAL -- Abaqus does not apply averaging to those either.

The exact CAE denominator isn't publicly documented, so treat this as a
close, principled re-implementation, not a guaranteed byte-for-byte match.
Spot-check one node/frame against a CAE contour probe before relying on
this at scale.

-------------------------------------------------------------------------
SPEED
-------------------------------------------------------------------------
All per-node grouping/averaging is done with numpy on whole bulkDataBlocks
arrays (no per-value Python loops).

Run with:   abaqus python extract_odb_stats.py -- <odb_path> <output_md_path>
   or just edit ODB_PATH / OUTPUT_PATH below and run with no args.
"""

import sys

import numpy as np

from odbAccess import openOdb
from abaqusConstants import NODAL, ELEMENT_NODAL, INTEGRATION_POINT, MISES, MAX_PRINCIPAL, MAGNITUDE

# =========================================================
# EDIT THESE VARIABLES (or pass odb_path / output_path as argv)
# =========================================================


ODB_PATH = r"C:\Users\RAGHUL\Documents\Abaqus_Scripts\Assets\e2.odb"
OUTPUT_PATH = r"C:\Users\RAGHUL\Documents\Abaqus_CAE_Copilot\abaqus_scripts\e2_odb_summary.md"


ROUND_DECIMALS = 3
AVERAGING_THRESHOLD_PERCENT = 75.0

# ("display name", "odb field key", reduction_type, reduction_value)
#   reduction_type: None        -> field is already scalar (e.g. PEEQ)
#                   "invariant" -> field.getScalarField(invariant=...)
#                   "component" -> field.getScalarField(componentLabel=...)
FIELD_REQUESTS = [
    ("Von Mises Stress", "S", "invariant", MISES),
    ("Max Principal Stress", "S", "invariant", MAX_PRINCIPAL),
    ("Equivalent Plastic Strain", "PEEQ", None, None),
    ("Displacement Magnitude", "U", "invariant", MAGNITUDE),
]

# =========================================================
# Extraction core
# =========================================================


def resolve_scalar_field(field_output, reduction_type, reduction_value):
    if reduction_type is None:
        return field_output
    if reduction_type == "invariant":
        return field_output.getScalarField(invariant=reduction_value)
    if reduction_type == "component":
        return field_output.getScalarField(componentLabel=reduction_value)
    raise ValueError("Unknown reduction_type: {}".format(reduction_type))


def choose_position(field_output):
    positions = set(loc.position for loc in field_output.locations)
    if NODAL in positions:
        return NODAL
    if INTEGRATION_POINT in positions or ELEMENT_NODAL in positions:
        return ELEMENT_NODAL
    return None


def collect_bulk_arrays(field_subset):
    """Returns {section_point_number_or_None: (values, node_labels)}."""
    groups = {}
    for block in field_subset.bulkDataBlocks:
        data = block.data
        if data is None or len(data) == 0:
            continue
        node_labels = getattr(block, "nodeLabels", None)
        if node_labels is None or len(node_labels) == 0:
            continue
        values = np.asarray(data, dtype=float).reshape(len(node_labels), -1)[:, 0]
        node_labels = np.asarray(node_labels, dtype=np.int64)

        sp = getattr(block, "sectionPoint", None)
        sp_key = sp.number if sp is not None else None

        g = groups.setdefault(sp_key, {"values": [], "nodes": []})
        g["values"].append(values)
        g["nodes"].append(node_labels)

    out = {}
    for sp_key, g in groups.items():
        out[sp_key] = (np.concatenate(g["values"]), np.concatenate(g["nodes"]))
    return out


def merge_and_stats(values, node_labels, threshold_pct):
    if values.size == 0:
        return None

    order = np.argsort(node_labels, kind="mergesort")
    s_nodes = node_labels[order]
    s_vals = values[order]

    uniq_nodes, start_idx, counts = np.unique(s_nodes, return_index=True, return_counts=True)

    group_max = np.maximum.reduceat(s_vals, start_idx)
    group_min = np.minimum.reduceat(s_vals, start_idx)
    group_sum = np.add.reduceat(s_vals, start_idx)
    group_mean = group_sum / counts

    denom = np.maximum(np.abs(group_max), np.abs(group_min))
    denom = np.where(denom < 1e-12, 1e-12, denom)
    pct_diff = 100.0 * (group_max - group_min) / denom

    effective_merge = (counts == 1) | (pct_diff <= threshold_pct)

    merged_vals = group_mean[effective_merge]
    merged_nodes = uniq_nodes[effective_merge]

    keep_mask = np.repeat(~effective_merge, counts)
    indiv_vals = s_vals[keep_mask]
    indiv_nodes = s_nodes[keep_mask]

    final_vals = np.concatenate([merged_vals, indiv_vals])
    final_nodes = np.concatenate([merged_nodes, indiv_nodes])

    if final_vals.size == 0:
        return None

    i_min = int(np.argmin(final_vals))
    i_max = int(np.argmax(final_vals))

    return {
        "min_value": float(final_vals[i_min]),
        "min_node": int(final_nodes[i_min]),
        "max_value": float(final_vals[i_max]),
        "max_node": int(final_nodes[i_max]),
        "avg_value": float(np.mean(final_vals)),
    }


def extract_field_for_instance(field_output, inst_name, instance, reduction_type,
                                reduction_value, threshold_pct):
    """Returns {column_label: stats_dict}. column_label is inst_name, or
    'inst_name (SP<n>)' if the field has multiple section points there."""
    scalar = resolve_scalar_field(field_output, reduction_type, reduction_value)
    position = choose_position(scalar)
    if position is None:
        return {}

    try:
        subset = scalar.getSubset(region=instance, position=position)
    except Exception:
        return {}

    groups = collect_bulk_arrays(subset)
    if not groups:
        return {}

    out = {}
    if len(groups) == 1 and None in groups:
        values, nodes = groups[None]
        stats = merge_and_stats(values, nodes, threshold_pct)
        if stats:
            out[inst_name] = stats
        return out

    for sp_key in sorted(groups.keys(), key=lambda k: (k is None, k)):
        values, nodes = groups[sp_key]
        stats = merge_and_stats(values, nodes, threshold_pct)
        if stats:
            label = "{} (SP{})".format(inst_name, sp_key) if sp_key is not None else inst_name
            out[label] = stats
    return out


# =========================================================
# Table assembly + writing
# =========================================================


def add_once(order_list, item):
    if item not in order_list:
        order_list.append(item)


def fmt_val(v, decimals=ROUND_DECIMALS):
    return "" if v is None else "{:.{d}f}".format(v, d=decimals)


def fmt_node(v):
    return "" if v is None else str(v)


def write_md_table(f, header, rows):
    f.write("| " + " | ".join(header) + " |\n")
    f.write("|" + "|".join(["---"] * len(header)) + "|\n")
    for row in rows:
        f.write("| " + " | ".join(row) + " |\n")
    f.write("\n")


def main(odb_path, output_path):
    odb = openOdb(path=odb_path, readOnly=True)

    step_order = list(odb.steps.keys())
    # per_field[display_name] = {
    #   "columns": [col_label, ...] (order preserved, union across all rows),
    #   "rows": [(step_name, frame_id, frame_value), ...] (chronological),
    #   "cells": {(step_name, frame_id, col_label): stats_dict},
    # }
    per_field = {}

    try:
        for step_name in step_order:
            step = odb.steps[step_name]
            for frame in step.frames:
                frame_id = frame.frameId
                frame_value = frame.frameValue

                for display_name, field_key, red_type, red_val in FIELD_REQUESTS:
                    if field_key not in frame.fieldOutputs:
                        continue
                    field_output = frame.fieldOutputs[field_key]

                    table = per_field.setdefault(
                        display_name, {"columns": [], "rows": [], "cells": {}})
                    add_once(table["rows"], (step_name, frame_id, frame_value))

                    for inst_name, instance in odb.rootAssembly.instances.items():
                        if len(instance.elements) == 0 and len(instance.nodes) == 0:
                            continue
                        cols = extract_field_for_instance(
                            field_output, inst_name, instance, red_type, red_val,
                            AVERAGING_THRESHOLD_PERCENT)
                        for col_label, stats in cols.items():
                            add_once(table["columns"], col_label)
                            table["cells"][(step_name, frame_id, col_label)] = stats
    finally:
        odb.close()

    with open(output_path, "w") as f:
        f.write("# ODB Field Output Summary\n\n")
        f.write("- odb: `{}`\n".format(odb_path))
        f.write("- averaging_threshold_percent: {}\n\n".format(AVERAGING_THRESHOLD_PERCENT))

        for display_name, _, _, _ in FIELD_REQUESTS:
            table = per_field.get(display_name)
            if not table or not table["columns"]:
                continue

            f.write("## {}\n\n".format(display_name))
            columns = table["columns"]
            rows = table["rows"]

            # ---- MAX table (only table produced) ----
            header = ["Step", "Frame", "Time (s)"]
            for c in columns:
                header += [c, "{} Node".format(c)]
            out_rows = []
            for step_name, frame_id, frame_value in rows:
                row = [step_name, str(frame_id), fmt_val(frame_value, 6)]
                for c in columns:
                    stats = table["cells"].get((step_name, frame_id, c))
                    row += [fmt_val(stats["max_value"] if stats else None),
                            fmt_node(stats["max_node"] if stats else None)]
                out_rows.append(row)
            write_md_table(f, header, out_rows)

    print("Wrote: {}".format(output_path))


if __name__ == "__main__":
    odb_path =  ODB_PATH
    output_path = OUTPUT_PATH
    main(odb_path, output_path)