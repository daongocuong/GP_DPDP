# Supplied Gold VNSME (ICAPS 2021) Java package

Imported from `C:/Users/Cuongdz/Documents/LA/VNSME` on 2026-11-08.
`original/` is a byte-for-byte copy of `source-code/src/` (10 Java files).
`lib/org/` is the supplied third-party class tree from `compiled files/org/`.
The supplied package has no README, Maven/Gradle build, JAR dependencies,
launcher, or license file. Its `metadata.json` refers to Python entry files
that are absent. Java execution uses `main_algorithm.main`, not that metadata.
The Gold/VNSME identity is the user's supplied identification; no upstream
release checksum was supplied. See `provenance.json` for byte checksums.

The IntelliJ configuration declares Java 8. `build_vnsme.py` requires a JDK
supporting `--release 8` (JDK 9+) and compiles unchanged source to `build/`.
The verified compiler/runtime is OpenJDK 26.0.1. The build manifest records
the exact compiler command, compiler/runtime versions and checksums.

From the dvrpsim repo root:

```powershell
.\.venv\Scripts\python.exe build_vnsme.py
```

Direct invocation, with a private working directory containing `benchmark/`
and `algorithm/data_interaction/`:

```powershell
java -cp 'C:\Users\Cuongdz\Documents\LA\dvrpsim\third_party\vnsme\build;C:\Users\Cuongdz\Documents\LA\dvrpsim\third_party\vnsme\lib' main_algorithm
```

Do not run Java from its source directory. Its paths are fixed relative to CWD:

| Path | Contract |
| --- | --- |
| `benchmark/factory_info.csv`, `benchmark/route_info.csv` | Original Huawei static network CSVs |
| `algorithm/data_interaction/vehicle_info.json` | Array of vehicle records |
| `algorithm/data_interaction/unallocated_order_items.json` | All released items not yet loaded, including planned ones |
| `algorithm/data_interaction/ongoing_order_items.json` | Items projected on board after current service |
| `algorithm/data_interaction/output_destination.json` | Object, one nullable destination per vehicle |
| `algorithm/data_interaction/output_route.json` | Object, one remaining published route list per vehicle |
| `algorithm/data_interaction/solution.json` | Java's persistent full internal plan; preserve across epochs |

Vehicles require `id`, `gps_id`, `operation_time`, `capacity`, `update_time`,
`cur_factory_id`, `arrive_time_at_current_factory`,
`leave_time_at_current_factory`, `carrying_items` (bottom to top), and nullable
`destination`. Nodes contain `factory_id`, `pickup_item_list`,
`delivery_item_list`, `arrive_time`, `leave_time` (output also has `lng`, `lat`).
Items require `id`, `order_id`, `type`, `demand`, `pickup_factory_id`,
`delivery_factory_id`, `creation_time`, `committed_completion_time`,
`load_time`, `unload_time`, `delivery_state`. Time fields are integer seconds;
request, deadline and GPS times use epoch timestamps. Status is 1 or 2.

The original implementation assumes vehicles `V_1` through `V_n` in order,
contiguous item suffixes `order_id-1`, `order_id-2`, etc., and a 600-second
dispatch interval. It checks the host's current midnight using `java.util.Date`.
The Python bridge adds a fixed host-midnight offset for each rollout. Java
stores times in signed 32-bit integers. Long-term execution beyond that range
requires a separate upstream compatibility change; source is unchanged here.

The original `isDelay=true` publishes only urgent route prefixes, after
extending them to retain carried loads. It preserves other work privately in
`solution.json`. Do not replace this policy with a full-plan dump. The local
adapter leaves unannounced items open and checks every published complete
remaining plan with the existing independent checker.

The Java search has internal checks at 540 seconds, with some operators
between checks. The adapter enforces a separate subprocess deadline (default
600 seconds) and caps it by the rollout's remaining wall budget.
