# Outputs

## Results: `output/`

By default every simulation gets its own folder in `output/`:

```text
output
├── capiQ_user_options.json            the options used for this run
├── SCENARIO_Q001
│   ├── SCENARIO_Q001_setup.h5
│   ├── SCENARIO_Q001_results.h5
│   ├── SCENARIO_Q001_results.xdmf     ← open this one in ParaView
│   ├── SCENARIO_Q001_results_aux.h5     (read by the .xdmf)
│   ├── SCENARIO_Q001_setup.log
│   ├── SCENARIO_Q001_run.log
│   ├── SCENARIO_Q001_model.json       the input, as BASEMENT read it (store_configs, on by default)
│   └── SCENARIO_Q001_simulation.json  copy of the input (store_configs, on by default)
└── SCENARIO_Q002
    └── ...
```

Each folder is self-contained: the `.xdmf` refers to its `.h5` files by name only, so a folder can be copied or moved elsewhere and still opened in ParaView.

`NAME_model.json` is the model file BASEMENT's setup read: the input file with the full paths of the mesh, support and initialization files, and `simulation_name` set to `NAME_model`. The file in `input/` itself is never changed.

Set `output_subfolders: false` in `user_options.yml` to write all files directly in `output/` instead.

## The capiQ log

A timestamped log file `capiQ_YYYY-MM-DD_HH-MM.log` is written in the project root (choose the name with [`--logger-filename`](running.md#command-line-options)). It records:

- the options used and the queue that was built (simulations, meshes, initialization files);
- what was decided for results of earlier runs (skip, continue, rerun);
- for each simulation, the elapsed time and BASEMENT's real-time speedup (RTS, overall and the range during the run);
- where each simulation ran on [multi-socket machines](multi-socket-gpu.md);
- errors, and the simulations skipped because their initialization failed;
- for a simulation that fails, the BASEMENT command that failed, its return code and BASEMENT's output;
- with `verbose: true`, BASEMENT's full output of every step.

```text title="Excerpt of a capiQ log (initialization example, default user_options.yml)"
INFO - 2 scenarios found
INFO - 1 mesh found
INFO - 1 initialization file(s) will be produced first: ['BASE_Q001_results.h5']
INFO - Running 2 simulations simultaneously
INFO - Using 0 GPU(s) and 2 CPU(s) for simulations
INFO - Simulation BASE_Q001 finished. Elapsed time: 0.99 seconds (00d 00h 00min 00s)
INFO - Simulation BASE_Q001 real-time speedup: RTS = 3470.9 (range 1689.3-15518.9)
```

The excerpts below come from real runs of the example queue; long paths are shortened to `…`.

### When a queue is restarted

When capiQ starts, it first logs what it found in `output/` for each simulation and what it will do. The queue below is the example with its end time raised to 40000 s and its output interval to 1000 s (41 outputs), so that it could be stopped halfway. It was stopped while `SCENARIO2_Q001` and `SCENARIO2_Q002` were running; `SCENARIO_Q001` and `SCENARIO_Q002` had not started yet. Starting capiQ again gives:

```text title="Restart after an interruption"
2026-11-26 18:05:05,815 - run_simulations - INFO - Simulation SCENARIO2_Q001: continued from t = 5000 s (output 5/40, 35 output(s) left)
2026-11-26 18:05:05,816 - run_simulations - INFO - Simulation SCENARIO2_Q002: continued from t = 4000 s (output 4/40, 36 output(s) left)
2026-11-26 18:05:05,824 - run_simulations - INFO - Running 4 simulations simultaneously
...
2026-11-26 18:05:45,601 - run_simulations - INFO - Simulation SCENARIO2_Q001 finished. Elapsed time: 39.17 seconds (00d 00h 00min 39s)
```

The two interrupted simulations continue from their last complete output; the two that had not started get no line and run from the start. Starting capiQ once more, after everything has finished, skips them all:

```text title="Restart of a finished queue"
2026-11-26 18:07:05,209 - run_simulations - INFO - Simulation SCENARIO2_Q001: complete (41 outputs), skipped
2026-11-26 18:07:05,209 - run_simulations - INFO - Simulation SCENARIO2_Q002: complete (41 outputs), skipped
2026-11-26 18:07:05,209 - run_simulations - INFO - Simulation SCENARIO_Q001: complete (41 outputs), skipped
2026-11-26 18:07:05,209 - run_simulations - INFO - Simulation SCENARIO_Q002: complete (41 outputs), skipped
2026-11-26 18:07:05,209 - run_simulations - INFO - Resuming: skipping 4 already completed simulation(s): ['SCENARIO2_Q001_model.json', ...]
2026-11-26 18:07:05,209 - run_simulations - INFO - Nothing to run: all simulations are already completed (set overwrite: true to run them again)
```

Other decisions read, for example, `rerun from scratch: …` (nothing usable to continue from) or `all 41 outputs present, but no .xdmf: only the results step runs`. [Resuming a queue](resuming.md) explains each case.

### When a simulation fails

A failed simulation does not stop the queue: the other simulations still run. capiQ logs the BASEMENT command that failed with its return code and output, then an `ERROR` line naming BASEMENT's log to look at, and lists all failed simulations at the end.

In this example, the outlet boundary of `SCENARIO_Q002_model.json` was given the type `uniform_outlet` instead of `uniform_out`:

```json title="input/SCENARIO_Q002_model.json (excerpt, with the mistake)"
{
    "name": "outlet",
    "string_name": "outlet",
    "type": "uniform_outlet",
    "slope": 0.0005
}
```

```text title="capiQ log (default user_options.yml)"
2026-11-26 19:09:04,735 - basement_tools - ERROR - 'BMv4_setup.exe' failed (return code 1). Command: C:\Program Files\BASEMENT 4.3.0\bin\BMv4_setup.exe …\output\SCENARIO_Q002\SCENARIO_Q002_model.json --output …\output\SCENARIO_Q002\SCENARIO_Q002_setup.h5
2026-11-26 19:09:04,739 - basement_tools - INFO - --- STDOUT (extra info) ---
2026-11-26 19:09:04,739 - basement_tools - INFO - BASEMENT v4.3.0 (5578d0e)
…
2026-11-26 19:09:04,767 - run_simulations - ERROR - Simulation SCENARIO_Q002 generated an exception: BMv4_setup.exe failed. Check the log and …\output\SCENARIO_Q002\SCENARIO_Q002_setup.log for details.
2026-11-26 19:09:05,310 - run_simulations - INFO - Simulation SCENARIO_Q001 finished. Elapsed time: 0.96 seconds (00d 00h 00min 00s)
2026-11-26 19:09:05,467 - run_simulations - ERROR - 1 simulation(s) failed: ['SCENARIO_Q002_model.json']
2026-11-26 19:09:05,468 - run_simulations - INFO - All simulations calculated in 3.05 seconds
```

The cause is in BASEMENT's output, in the capiQ log above and in BASEMENT's log of the step that failed, here the setup:

```text title="output/SCENARIO_Q002/SCENARIO_Q002_setup.log"
===== C:\Program Files\BASEMENT 4.3.0\bin\BMv4_setup.exe …\output\SCENARIO_Q002\SCENARIO_Q002_model.json --output …\output\SCENARIO_Q002\SCENARIO_Q002_setup.h5
BASEMENT v4.3.0 (5578d0e)
BASEHPC setup binary
/SETUP/BASEHPC/BASEPLANE_2D/GEOMETRY/_comment: Warning: The value of this item will not be used.
/SETUP/BASEHPC/BASEPLANE_2D/HYDRAULICS/BOUNDARY/STANDARD/0/_comment: Warning: The value of this item will not be used.
/SETUP/BASEHPC/BASEPLANE_2D/HYDRAULICS/BOUNDARY/STANDARD/1/slope: Warning: The value of this item will not be used.
/SETUP/BASEHPC/BASEPLANE_2D/HYDRAULICS/BOUNDARY/STANDARD/1/type: Error: This value must be equal to one of the following: 'froude_in', 'hqrelation_out', 'solitary_wave', 'uniform_in', 'uniform_out', 'weir_out_constant', 'weir_out_dynamic', 'zero_gradient_out', 'zhydrograph', 'zqhydrograph'.
 -> Terminating BASEMENT due to JSON validation errors.
 -> ... unfortunately BASEMENT is killed!
===== return code 1
```

capiQ then exits with code `2` (see [exit codes](running.md#exit-codes)). Fix the input file and start capiQ again: the finished simulations are skipped and only the failed one runs. When an [initialization simulation](initialization.md) fails, the simulations that start from it are skipped and logged as `Simulation … skipped: its initialization simulation failed or was skipped`.

## BASEMENT's own logs

BASEMENT's output for each simulation is written while BASEMENT runs:

- `NAME_setup.log`: the setup step;
- `NAME_run.log`: the simulation (with its progress lines) and the results step.

Each program's section starts with its command and ends with its return code, also when BASEMENT fails. Look here first when a simulation fails: the error is usually in the last lines before `===== return code`.
