"""Shared helpers for the probes: render the real parts with OpenSCAD, read
the derived numbers from params.scad, boolean-intersect with manifold.

    source ~/.local/opt/openscad/env.sh
    python3 probes/lid_retention.py
"""
import os, re, subprocess, sys, tempfile
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)


def scad(args, out):
    exe = os.environ.get("OPENSCAD_BIN")
    if not exe:
        sys.exit("OPENSCAD_BIN not set: source ~/.local/opt/openscad/env.sh first")
    r = subprocess.run([exe, "--backend=manifold", *args, "-o", out],
                       capture_output=True, text=True, cwd=PROJECT)
    if r.returncode != 0 or "ERROR" in r.stderr:
        sys.exit("OpenSCAD failed:\n" + r.stderr[-2000:])
    return r.stderr


def params():
    with tempfile.TemporaryDirectory() as d:
        err = scad([os.path.join(HERE, "params_dump.scad")], os.path.join(d, "x.stl"))
    return {m.group(1): float(m.group(2))
            for m in re.finditer(r'PROBE (\w+)=([-\d.eE+]+)', err)}


def parts(names=("body", "pick_lid")):
    out = {}
    with tempfile.TemporaryDirectory() as d:
        for n in names:
            p = os.path.join(d, n + ".stl")
            scad([os.path.join("parts", n + ".scad")], p)
            m = trimesh.load(p)
            assert m.is_watertight, n + " is not watertight"
            out[n] = m
    return out


def overlap_mm3(a, b):
    """Exact volume of a AND b, by manifold."""
    r = trimesh.boolean.intersection([a, b], engine="manifold")
    return 0.0 if r.is_empty else float(r.volume)


def moved(mesh, T):
    m = mesh.copy()
    m.apply_transform(T)
    return m


def translation(v):
    T = np.eye(4)
    T[:3, 3] = v
    return T
