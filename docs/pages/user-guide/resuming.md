# Resuming a queue

Start capiQ again after a cancel (++ctrl+c++), a crash or a reboot, and it picks up where each simulation stopped. When the queue starts, capiQ reads every `NAME_results.h5` in `output/`, logs what it decided and why, and then does one of the following for each simulation.

| State found in `output/` | What capiQ does |
| --- | --- |
| Every output is there, and the `.xdmf` | [Skips it](#complete-simulations-are-skipped) |
| Some outputs after the start | [Continues it](#partial-simulations-are-continued) from the last good output |
| No output after the start, unreadable results, or no setup file | [Reruns it from scratch](#reruns-from-scratch) |
| Every output, but no `.xdmf` | [Runs only the results step](#results-step-only) |

[Outputs](outputs.md#when-a-queue-is-restarted) shows what these decisions look like in the log.

## Complete simulations are skipped

A simulation is complete when its results file holds every output it asks for, `round((end - start) / out) + 1` of them according to `SIMULATION.TIME` in `input/NAME_simulation.json`, and the `.xdmf` is there.

The input `.json` file counts, not the TIME stored in the results file, so the end time can be changed after a run started:

- **Shorter end**: a finished simulation stays complete and is skipped, its files untouched; only `overwrite: true` runs it again. An interrupted run that already got past the new end only gets the results step. Outputs computed after the new end are never deleted, so they stay in the file and the `.xdmf`.
- **Longer end**: a finished run is continued to it. The finished `NAME_results.h5` stores the original start and the new end.
- **Changed start or output interval**: the simulation runs from scratch.

## Partial simulations are continued

From their last output that reads back completely (if that output is damaged, from the one before it). capiQ uses BASEMENT's re-run (User Manual, *Re-Run Simulation*): the same `NAME_setup.h5`, and `SIMULATION.TIME.start` set to the time of that output. BASEMENT appends the remaining outputs to the same `NAME_results.h5`, so the finished file looks like an uninterrupted run, with one `.xdmf`.

While the continuation runs, the partial file is kept as `NAME_results_backup.h5`. The backup is removed once the results are complete. A continuation that is interrupted too is continued in the same way.

## Reruns from scratch

Simulations with nothing to continue from: no output after the start, an unreadable results file, or a missing setup file. An unusable results file is kept as `NAME_results_unusable.h5`.

## Results step only

When every output is there but the `.xdmf` is missing (BMv4_results was interrupted), only BASEMENT's results step runs.

## Things to know

- ++ctrl+c++ stops the queue together with the running BASEMENT processes. BASEMENT's own documentation warns that interrupting it can damage the results file, which is why capiQ checks every output before continuing. The last output may be lost.
- capiQ looks for results in the layout currently selected: after changing `output_subfolders`, move the existing files accordingly or they are run again.
- Set `overwrite: true` in `user_options.yml` to delete `output/` and run every simulation from the start.
- Only complete results are copied to the [initialization folder](initialization.md).
