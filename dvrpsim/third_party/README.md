# Local third-party components

`vnsme/` contains the supplied Java sources and dependency classes, separated
from the Python adapter in `src/baselines/vnsme.py`. See its README and build
manifest for the build and fixed Huawei JSON protocol.

`huawei-xingtian/` is a separate, unmodified sparse Git checkout used only to
obtain the official simulator. It is pinned to
`e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04`, matching the existing dataset and
scoring provenance. Recreate it from the repository root if absent:

```powershell
git clone --filter=blob:none --no-checkout https://github.com/huawei-noah/xingtian.git third_party/huawei-xingtian
git -C third_party/huawei-xingtian sparse-checkout set simulator/dpdp_competition
git -C third_party/huawei-xingtian checkout e4ef3a1c92d19d1d08c3ef0e2156b6fecefdbe04
```

`run_vnsme_huawei.py` copies the upstream `src/` to the requested run directory
before importing it, so import-time folder creation and logging remain isolated.
It uses only the already-pinned instance-2 input data. The simulator's dispatch
checker, vehicle simulation and evaluator are not modified. Its subprocess
transport is replaced by `JavaSession` for argument-list invocation, timeouts,
fresh-output validation and archives. Every upstream dispatch check still runs.

Huawei additionally requires pandas. The installed versions for the attempted
verification are recorded in `vnsme_evidence/environment.json`. Windows
Application Control currently rejects the pandas interval extension; the
Huawei simulation therefore has no completed rollout or score on this machine.
