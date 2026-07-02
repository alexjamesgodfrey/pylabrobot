# Bulk dispensing

Bulk dispensers deliver reagent into microplates at high throughput. They are used for filling plates with media, adding assay reagents, wash steps, and any operation where many wells need the same (or similar) volumes.

PLR supports three dispensing mechanisms, each with its own capability:

| Capability | Mechanism | Addressing | Typical use |
|---|---|---|---|
| **[Peristaltic dispensing](peristaltic)** | Peristaltic pump | Per column | Media, wash buffer, large-volume reagents |
| **[Syringe dispensing](syringe)** | Syringe pump | Per column | Detection reagents, substrates, low-volume precision |
| **[Valve dispensing](../../thermo_fisher/multidrop_combi/hello-world-nl)** | Pressurized reservoir + solenoid valves | **Per well** | Low-volume (nL–µL) assay reagents into individual wells |

The peristaltic and syringe capabilities share a per-column `volumes` interface: a dict mapping **1-indexed column numbers** to volumes in uL. The valve capability is **per-well**: a single volume for the whole plate, or a dict keyed by well name (`"A1"`) or 1-indexed `(row, col)`. Device-specific settings (pump speed, cassette type, drop height, pressure, etc.) are passed as `backend_params`.

Some devices (like the BioTek EL406) have both systems on a single instrument. Use the one that matches your volume and accuracy requirements.

## Peristaltic vs syringe

| | Peristaltic | Syringe |
|---|---|---|
| **Volume range** | Medium--high | Low--medium |
| **Accuracy** | Good | High |
| **Throughput** | High | Lower |
| **Purge needed** | Yes | No |

Peristaltic dispensers push fluid through flexible tubing using a rotating pump head. They are fast and handle large volumes well, but require priming before use and purging after to clear the lines. Syringe dispensers aspirate a fixed volume into a barrel and dispense it with high precision. They are slower but more accurate at low volumes.

## Tips and gotchas

- **Always prime before dispensing** (peristaltic). Air in the tubing causes inaccurate volumes.
- **Purge after dispensing** to prevent reagent from drying in the lines.
- **Columns are 1-indexed.** `{1: 50.0}` sets column 1, not column 0.
- **Only columns in the dict are set.** Columns not in `volumes` retain their previous setting on the instrument. If in doubt, explicitly set all columns.

## Supported hardware

| Device | Manufacturer | Peristaltic | Syringe | Valve (per-well) |
|--------|-------------|:-----------:|:-------:|:----------------:|
| [Multidrop Combi](../../thermo_fisher/multidrop_combi/hello-world) | Thermo Fisher | yes | -- | -- |
| [Multidrop Combi nL](../../thermo_fisher/multidrop_combi/hello-world-nl) | Thermo Fisher | -- | -- | yes |
| [EL406](../../agilent/biotek/el406/hello-world) | BioTek (Agilent) | yes | yes | -- |

```{toctree}
:maxdepth: 1
:hidden:

peristaltic
syringe
```

## API reference

- {class}`~pylabrobot.capabilities.bulk_dispensers.peristaltic.peristaltic8.PeristalticDispensing8` / {class}`~pylabrobot.capabilities.bulk_dispensers.peristaltic.backend8.PeristalticDispensingBackend8`
- {class}`~pylabrobot.capabilities.bulk_dispensers.syringe.syringe8.SyringeDispensing8` / {class}`~pylabrobot.capabilities.bulk_dispensers.syringe.backend8.SyringeDispensingBackend8`
- {class}`~pylabrobot.capabilities.bulk_dispensers.valve.valve8.ValveDispensing8` / {class}`~pylabrobot.capabilities.bulk_dispensers.valve.backend8.ValveDispensingBackend8`
