# Initialization simulations

A scenario can start from the results of another simulation instead of a dry or still channel, for example to start a morphodynamic run from a steady hydraulic state. In BASEMENT this is an `INITIAL` section of type `continue`, in `HYDRAULICS` or `TURBULENCE`:

```json
"INITIAL": {
    "type": "continue",
    "file": "BASE_Q001_results.h5",
    "time": 1000.0
}
```

`file` is the results file to start from, and `time` the output time in it to use.

## Where capiQ looks for the file

Before running, capiQ looks for every such file (file names are compared without regard to case):

1. **In the initialization folder** (`INITIALIZATION_FOLDER` in `constants.py`): the file is used as it is.
2. **Otherwise, in `input/`**: `BASE_Q001_results.h5` or `BASE_Q001.h5` is produced by `BASE_Q001_model.json`. That simulation runs first, the scenarios that need it start once it has finished, and its results are copied to the initialization folder (created at that point if it does not exist) under the requested name, so later runs find them there.
3. **Otherwise**, capiQ stops with an error listing the missing files.

Only complete results are copied to the initialization folder, so a cancelled initialization run never initializes other simulations.

## When an initialization simulation fails

The scenarios that depend on it are skipped and the others still run. Both are listed at the end of the log.

## Example

`example_files/initialization_example/input/` holds a base run and a scenario that continues from it, on the example mesh:

| File | Content |
| --- | --- |
| `BASE_Q001_model.json` | Same as `SCENARIO_Q001`: starts from a dry channel. |
| `CONTINUED_Q001_model.json` | Starts from the base run's results at t = 1000 s. |
| `*_simulation.json`, `results.json` | Same as the main example. |

The only difference between the two model files:

```json title="example_files/initialization_example/input/CONTINUED_Q001_model.json (excerpt)"
--8<-- "example_files/initialization_example/input/CONTINUED_Q001_model.json:94:98"
```

To run it, create the example mesh and use these files as `input/` (`input/` must not exist yet):

=== "Windows (PowerShell)"

    ```powershell
    uv run example_files/create_example_mesh.py
    Copy-Item -Recurse example_files\initialization_example\input input
    uv run python -m capiq
    ```

=== "Linux and macOS"

    ```bash
    uv run example_files/create_example_mesh.py
    cp -r example_files/initialization_example/input input
    uv run python -m capiq
    ```

capiQ finds no `BASE_Q001_results.h5` in `example_files/initialization/`, so it runs `BASE_Q001` first, copies its results there, and then runs `CONTINUED_Q001`:

```text title="capiQ log"
INFO - No initialization folder found
INFO - 1 initialization file(s) will be produced first: ['BASE_Q001_results.h5']
INFO - Simulation BASE_Q001 finished. Elapsed time: 0.99 seconds (00d 00h 00min 00s)
INFO - Initialization file BASE_Q001_results.h5 copied to ...\example_files\initialization
INFO - Simulation CONTINUED_Q001 finished. Elapsed time: 0.85 seconds (00d 00h 00min 00s)
```

On the next run, `BASE_Q001_results.h5` is found in the initialization folder. Delete it there to produce it again.
