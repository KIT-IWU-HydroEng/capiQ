# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

"""Create the rectangular mesh used by the example files.

Run from the project root before running the examples:

    python example_files/create_example_mesh.py

The mesh is written to example_files/meshes/rectangular-channel.2dm (or to the path given as argument).

Domain: x from -90 to 90 m (flow direction) and y from 0 to 5 m, split into cells of 5 m x 0.5 m (720 triangles).
Two friction zones: material 1 is the main channel (y < 2 m), material 2 the floodplain (y > 2 m).
The cross-section is flat, with a longitudinal bed slope of 0.0005, as the uniform_out boundary assumes.
The node strings match the STRINGDEF names of the example model files and run from y = 0 m towards y = 5 m.
"""

import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "meshes" / "rectangular-channel.2dm"

# Domain and cell size in m
X0, X1, DX = -90.0, 90.0, 5.0
Y0, Y1, DY = 0.0, 5.0, 0.5
Y_CHANNEL = 2.0  # Border between main channel and floodplain
SLOPE = 0.0005  # Longitudinal bed slope (-)

NX = round((X1 - X0) / DX) + 1
NY = round((Y1 - Y0) / DY) + 1


def node_id(i: int, j: int) -> int:
    """Node number (1-based) of the grid point i along x and j along y."""
    return i * NY + j + 1


def nodestring(name: str, x: float, y_start: float, y_end: float) -> str:
    """Node string across the channel at x, from y_start to y_end."""
    i = round((x - X0) / DX)
    nodes = [node_id(i, j) for j in range(round((y_start - Y0) / DY), round((y_end - Y0) / DY) + 1)]
    nodes[-1] = -nodes[-1]  # A negative node number ends the node string
    return "NS " + " ".join(str(n) for n in nodes) + f" {name}"


def write_rectangular_mesh(path: Path = DEFAULT_PATH) -> None:
    """Write the example mesh in the 2dm format to path."""
    lines = ["MESH2D", "NUM_MATERIALS_PER_ELEM 1"]

    # Elements: each cell is split into two triangles, nodes counterclockwise
    element = 0
    for i in range(NX - 1):
        for j in range(NY - 1):
            a, b, c, d = node_id(i, j), node_id(i + 1, j), node_id(i + 1, j + 1), node_id(i, j + 1)
            material = 1 if Y0 + (j + 0.5) * DY < Y_CHANNEL else 2
            # Alternate the diagonal for a symmetric pattern
            triangles = [(a, b, c), (a, c, d)] if (i + j) % 2 == 0 else [(a, b, d), (b, c, d)]
            for n1, n2, n3 in triangles:
                element += 1
                lines.append(f"E3T {element} {n1} {n2} {n3} {material}")

    # Nodes: bed elevation falls with the slope towards the outlet at x = X1
    for i in range(NX):
        x = X0 + i * DX
        z = SLOPE * (X1 - x)
        for j in range(NY):
            lines.append(f"ND {node_id(i, j)} {x:.1f} {Y0 + j * DY:.1f} {z:.4f}")

    lines += [
        nodestring("inlet", X0, Y0, Y_CHANNEL),
        nodestring("outlet", X1, Y0, Y1),
        nodestring("inlet_mc", 0.0, Y0, Y_CHANNEL),
        nodestring("inlet_fp", 0.0, Y_CHANNEL, Y1),
        nodestring("outlet_mc", 30.0, Y0, Y_CHANNEL),
        nodestring("outlet_fp", 30.0, Y_CHANNEL, Y1),
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n") as file:
        file.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    write_rectangular_mesh(output_path)
    print(f"Mesh written to {output_path}")
