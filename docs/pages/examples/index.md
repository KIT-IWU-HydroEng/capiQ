# Examples

Every file on this page is included from the repository when the documentation is built, so what you see is exactly what is in `example_files/` and `user_defined/`. Use them as templates for your own project.

```text
example_files/
├── create_example_mesh.py             step 2: writes meshes/rectangular-channel.2dm
├── support_files/                     step 3
│   ├── Q001.txt
│   └── Q002.txt
├── input/                             step 4: the main example queue
│   ├── SCENARIO_Q001_model.json
│   ├── SCENARIO_Q001_simulation.json
│   ├── ... (SCENARIO_Q002, SCENARIO2_Q001, SCENARIO2_Q002)
│   └── results.json
└── initialization_example/input/      step 7: a scenario started from another one
    ├── BASE_Q001_model.json
    ├── CONTINUED_Q001_model.json
    └── ...
```

The example models a straight rectangular channel, 180 m long and 5 m wide, with a main channel and a floodplain of different roughness. Each scenario runs for 1000 s with an output every 100 s.

## Step 1: Configure

`user_defined/constants.py` points to the example folders by default. Only `BASEMENT_PATH` may need changing:

```python title="user_defined/constants.py"
--8<-- "user_defined/constants.py:30:38"
```

`user_defined/user_options.yml` runs two CPU simulations at a time with four threads each:

```yaml title="user_defined/user_options.yml"
--8<-- "user_defined/user_options.yml"
```

More: [Configuration](../user-guide/configuration.md).

## Step 2: Create the mesh

```bash
uv run example_files/create_example_mesh.py
```

The script writes a structured triangular mesh with two material zones and the node strings named in the model files:

```python title="example_files/create_example_mesh.py (header)"
--8<-- "example_files/create_example_mesh.py:7:33"
```

## Step 3: Support files

The inflow hydrographs, time in s and discharge in m³/s. `Q001` reaches 0.1 m³/s, `Q002` 0.3 m³/s:

=== "Q001.txt"

    ```text
    --8<-- "example_files/support_files/Q001.txt"
    ```

=== "Q002.txt"

    ```text
    --8<-- "example_files/support_files/Q002.txt"
    ```

## Step 4: Input files

Four simulations: two scenarios (`SCENARIO`, `SCENARIO2`), each with the two discharges. The model files differ only in their discharge file.

=== "SCENARIO_Q001_model.json"

    ```json
    --8<-- "example_files/input/SCENARIO_Q001_model.json"
    ```

=== "SCENARIO_Q001_simulation.json"

    ```json
    --8<-- "example_files/input/SCENARIO_Q001_simulation.json"
    ```

=== "results.json"

    ```json
    --8<-- "example_files/input/results.json"
    ```

Copy them to `input/` in the project root (`input/` must not exist yet):

=== "Windows (PowerShell)"

    ```powershell
    Copy-Item -Recurse example_files\input input
    ```

=== "Linux and macOS"

    ```bash
    cp -r example_files/input input
    ```

More: [Input files](../user-guide/input-files.md).

## Step 5: Run

```bash
uv run python -m capiq
```

More: [Running capiQ](../user-guide/running.md).

## Step 6: Look at the outputs

Each simulation has its folder in `output/`. Open `output/SCENARIO_Q001/SCENARIO_Q001_results.xdmf` in ParaView. The log `capiQ_YYYY-MM-DD_HH-MM.log` in the project root gives each simulation's run time and speed.

More: [Outputs](../user-guide/outputs.md).

## Step 7: Start a scenario from another one

`example_files/initialization_example/input/` holds `BASE_Q001` (starts dry) and `CONTINUED_Q001`, which starts from the results of `BASE_Q001` at t = 1000 s:

```json title="CONTINUED_Q001_model.json (excerpt)"
--8<-- "example_files/initialization_example/input/CONTINUED_Q001_model.json:94:98"
```

Replace `input/` with these files and run again: capiQ runs `BASE_Q001` first, stores its results in `example_files/initialization/`, then runs `CONTINUED_Q001`.

=== "Windows (PowerShell)"

    ```powershell
    Remove-Item -Recurse input, output
    Copy-Item -Recurse example_files\initialization_example\input input
    uv run python -m capiq
    ```

=== "Linux and macOS"

    ```bash
    rm -r input output
    cp -r example_files/initialization_example/input input
    uv run python -m capiq
    ```

More: [Initialization simulations](../user-guide/initialization.md).

## Step 8: Interrupt and resume

Start a run, press ++ctrl+c++ while simulations are running, and start capiQ again. Finished simulations are skipped, interrupted ones continue from their last good output, and the log says what was decided for each one.

More: [Resuming a queue](../user-guide/resuming.md).
