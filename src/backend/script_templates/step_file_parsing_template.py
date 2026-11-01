STEP_FILE_PARSER_TEMPLATE = """
import json
import os
import traceback

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_FACE
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepGProp import brepgprop_VolumeProperties, brepgprop_SurfaceProperties
from OCC.Core.GProp import GProp_GProps

print("=== STEP Parser (geometry only) ===")

# =========================================================
# EDIT THESE VARIABLES BEFORE RUNNING
# =========================================================

STEP_FILE_PATH = __STEP_FILE_PATH__
OUTPUT_SUMMARY_JSON_PATH = __OUTPUT_SUMMARY_JSON_PATH__

# =========================================================
# OCC geometry extraction
# =========================================================

def shape_mass_properties(shape):
    try:
        bbox = Bnd_Box()
        brepbndlib_Add(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

        vol_props = GProp_GProps()
        brepgprop_VolumeProperties(shape, vol_props)
        volume = vol_props.Mass()
        com = vol_props.CentreOfMass()

        area_props = GProp_GProps()
        brepgprop_SurfaceProperties(shape, area_props)
        area = area_props.Mass()

        return {
            "bbox": {"x": [xmin, xmax], "y": [ymin, ymax], "z": [zmin, zmax]},
            "volume": float(volume),
            "surface_area": float(area),
            "centroid": [float(com.X()), float(com.Y()), float(com.Z())]
        }
    except Exception as e:
        return {"error": str(e)}


def count_faces(solid):
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    count = 0
    while exp.More():
        count += 1
        exp.Next()
    return count


def extract_solids(path):
    print("Loading STEP file...")
    reader = STEPControl_Reader()
    status = reader.ReadFile(path)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEPControl_Reader failed to read '{}' (status={})".format(path, status))
    reader.TransferRoot()
    shape = reader.OneShape()

    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    idx = 0
    while explorer.More():
        solid = explorer.Current()
        idx += 1
        solids.append({
            "solid_index": idx,
            "face_count": count_faces(solid),
            "geometry": shape_mass_properties(solid)
        })
        explorer.Next()
    return solids


# =========================================================
# Driver
# =========================================================

def parse_step_file(path):
    solids = extract_solids(path)
    return {
        "backend": "pythonocc_core_step_control_reader",
        "solids": solids,
        "_meta": {
            "solid_count": len(solids),
        }
    }


def main():
    path = STEP_FILE_PATH
    out_path = OUTPUT_SUMMARY_JSON_PATH 

    if not os.path.isfile(path):
        print("ERROR: STEP file not found:", path)
        return

    try:
        summary = parse_step_file(path)
        with open(out_path, "w") as f:
            json.dump(summary, f, default=str)

        print("Solids (with real geometry):", summary["_meta"]["solid_count"])
        print("Summary saved to:", out_path)
    except Exception:
        print("ERROR occurred:")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
"""