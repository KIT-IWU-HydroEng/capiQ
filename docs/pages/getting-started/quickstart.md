# Quick start

This page runs the example queue shipped in `example_files/`: two scenarios, each with two discharges, on a small rectangular channel. It takes a few seconds. Run every command from the project root.

!!! info "Before you start"
    Confirm that capiQ is [installed](installation.md) and `BASEMENT_PATH` in `user_defined/constants.py` points to your BASEMENT installation.

## 1. Create the example mesh

The example mesh is not stored in the repository. Create it with:

```bash
uv run example_files/create_example_mesh.py
```

This writes a light triangular mesh of a rectangular channel to `example_files/meshes/rectangular-channel.2dm`. `user_defined/constants.py` already points `MESH_FOLDER` and `SUPPORT_FOLDER` to `example_files/`.

## 2. Copy the example input files

capiQ reads the simulations to run from `input/` in the project root. Copy the example inputs there (`input/` must not exist yet):

=== "Windows (PowerShell)"

    ```powershell
    Copy-Item -Recurse example_files\input input
    ```

=== "Linux and macOS"

    ```bash
    cp -r example_files/input input
    ```

`input/` now holds four simulations (`SCENARIO_Q001`, `SCENARIO_Q002`, `SCENARIO2_Q001`, `SCENARIO2_Q002`) and one `results.json`.

## 3. Run

```bash
uv run python -m capiq
```

A progress bar counts the finished simulations. With the default `user_options.yml`, two simulations run at the same time on the CPU.

## 4. Look at the results

```text
output
├── capiQ_user_options.json
├── SCENARIO_Q001
│   ├── SCENARIO_Q001_results.xdmf     ← open this one in ParaView
│   └── ...
├── SCENARIO_Q002
└── ...
```

The log file `capiQ_YYYY-MM-DD_HH-MM.log` in the project root lists each simulation with its run time. [Outputs](../user-guide/outputs.md) explains every file.

## Next steps

- Use your own mesh and discharges: [Configuration](../user-guide/configuration.md) and [Input files](../user-guide/input-files.md).
- Start one scenario from the results of another: [Initialization simulations](../user-guide/initialization.md).
- See every example file explained: [Examples](../examples/index.md).

!!! tip "Running the example again"
    Simulations whose results are complete are skipped on the next run. Set `overwrite: true` in `user_defined/user_options.yml`, or delete `output/`, to run them again.
