# Input files

Before running, these folders must exist and hold the files below.

```text
input/                               (project root)
├── SCENARIO_Q001_model.json         one pair per simulation
├── SCENARIO_Q001_simulation.json
├── SCENARIO_Q002_model.json
├── SCENARIO_Q002_simulation.json
└── results.json                     a single file for all simulations

MESH_FOLDER/                         (constants.py)
└── rectangular-channel.2dm

SUPPORT_FOLDER/                      (constants.py)
├── Q001.txt
└── Q002.txt

INITIALIZATION_FOLDER/               (constants.py, optional)
└── BASE_Q001_results.h5
```

If `input/` is missing or empty, or `MESH_FOLDER` is empty, capiQ stops before running anything, with a message naming that folder and showing this layout (a missing `input/` is created). Fill it, then run again.

!!! warning "All cases in one folder, no subfolders"
    Put the input files of every case (all scenarios and discharges) and the single `results.json` directly in `input/`. capiQ only reads the top level of `input/`: files in subfolders such as `input/SCENARIO/` or `input/Q001/` are ignored without a warning, and if no `_model.json` is left directly in `input/`, capiQ stops with *No scenarios found in the input folder*. Keep cases apart through their names (`SCENARIO_Q001`, `SCENARIO2_Q001`, …), not through folders.

    ```text title="✔ Read: every case directly in input/"
    input/
    ├── SCENARIO_Q001_model.json
    ├── SCENARIO_Q001_simulation.json
    ├── SCENARIO2_Q001_model.json
    ├── SCENARIO2_Q001_simulation.json
    └── results.json
    ```

    ```text title="✘ Ignored: cases in subfolders"
    input/
    ├── SCENARIO/
    │   ├── SCENARIO_Q001_model.json
    │   └── SCENARIO_Q001_simulation.json
    ├── SCENARIO2/
    │   └── ...
    └── results.json
    ```

## One simulation = one pair of files

Every simulation is named by its pair of BASEMENT input files: `NAME_model.json` and `NAME_simulation.json`. The name `NAME` is used for the output folder and all its files. Any name works; the examples use `SCENARIO_DISCHARGE` (e.g. `SCENARIO_Q001`) to keep scenarios and discharges apart.

### `NAME_model.json`

BASEMENT's model (setup) file: mesh, boundary conditions, friction, initial conditions, turbulence. Write it as for BASEMENT itself (see the BASEMENT user manual), with one difference:

!!! note "Paths to meshes and support files"
    capiQ only uses the **file names** of meshes and support files and replaces their folders with `MESH_FOLDER` and `SUPPORT_FOLDER` from `constants.py`. Any path can therefore be given, e.g. `"mesh_file": "path/to/meshes/rectangular-channel.2dm"` or `"discharge_file": "Q001.txt"`. Before running, capiQ checks that every mesh is found. Support files are looked up when each simulation starts: a missing one fails that simulation (*File 'Q001.txt' not found in support files* in the log), and the other simulations still run.

    capiQ never changes the files in `input/`. It writes the model file with the full paths to the simulation's output folder (`output/NAME/NAME_model.json`, see [Outputs](outputs.md)), and BASEMENT's setup reads that one.

```json title="example_files/input/SCENARIO_Q001_model.json (excerpt: geometry)"
--8<-- "example_files/input/SCENARIO_Q001_model.json:1:11"
```

```json title="example_files/input/SCENARIO_Q001_model.json (excerpt: inlet boundary)"
--8<-- "example_files/input/SCENARIO_Q001_model.json:78:85"
```

??? example "The full model file"

    ```json
    --8<-- "example_files/input/SCENARIO_Q001_model.json"
    ```

### `NAME_simulation.json`

BASEMENT's simulation file: start, end and output interval, time step and the output variables.

```json title="example_files/input/SCENARIO_Q001_simulation.json"
--8<-- "example_files/input/SCENARIO_Q001_simulation.json"
```

`SIMULATION.TIME` also tells capiQ how many outputs a finished simulation has, which matters when a queue is [resumed](resuming.md).

## `results.json`

One file for all simulations: how BASEMENT exports the results. capiQ uses it for the results step of every simulation.

```json title="example_files/input/results.json"
--8<-- "example_files/input/results.json"
```

## Meshes

BASEMENT `.2dm` meshes, in `MESH_FOLDER`. The example mesh is created by a script instead of being stored:

```bash
uv run example_files/create_example_mesh.py
```

??? example "example_files/create_example_mesh.py"

    ```python
    --8<-- "example_files/create_example_mesh.py"
    ```

## Support files

Text files referenced by the model files, for example the inflow hydrograph of a `froude_in` boundary: time in seconds and discharge in m³/s.

```text title="example_files/support_files/Q001.txt"
--8<-- "example_files/support_files/Q001.txt"
```

## Initialization files

Optional: results files used as initial conditions by `INITIAL` sections of type `continue`. See [Initialization simulations](initialization.md).
