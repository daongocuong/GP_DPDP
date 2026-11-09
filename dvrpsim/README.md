# A Python package for dynamic vehicle routing

`dvrpsim` is a Python package for simulating dynamic vehicle routing problems (DVRPs).
This package provides a flexible and modular simulation environment that allows users to model a wide range of dynamic vehicle routing scenarios, with the ability to connect external routing algorithms implemented in any programming language.

For more details, check out the introduction, tutorial, and case studies!

## GP-DPDP workflow

The current workflow uses **VNSME** as the evaluation baseline and the fitness
normalization reference. Reference results for **all instances 2–6 are complete
and accepted by the loader** at
`migration_runs/vnsme_reference_ready/summary.json`. Training reuses these stored
results; rebuilding Java or rerunning VNSME is not required for each GP run.
See the [reference completion report](reference_completion_evidence/20261108_retry_01/REFERENCE_COMPLETION_REPORT.md)
for run logs, provenance and verification.

The fitness version is **`gp-fitness-vnsme-v2`**:
`F_train = mean(J_GP(i) / J_VNSME(i))` for `i in {2, 3, 4, 5}`. Lower is better.
All four training instances are required; a failed rollout invalidates the tree
and receives the fixed penalty. Validation uses **instance 6** after evolution
to select among valid training candidates by `J_GP(6) / J_VNSME(6)`, then train
fitness, tree size and canonical representation. Validation is excluded from
evolutionary fitness. Final evaluation instances **7–8 and 15–16 remain sealed**.

Run Windows PowerShell from the repository root (the directory containing
`pyproject.toml`), using the project virtual environment and fresh output paths:

```powershell
.\.venv\Scripts\python.exe train_dpdp_gp_multinstance.py --baseline-summary migration_runs\vnsme_reference_ready\summary.json --output gp_runs\vnsme_v2_new_training_20261108_r1 --seed 20261106 --population 6 --generations 2 --timeout-seconds 30
```

This is the current **development pilot** configuration: population 6, two
evolutionary steps (generations 0–2), GP seed `20261106`, environment seed `0`,
tournament 3, crossover 0.8, mutation 0.3, elitism 1 and a 30-second hard deadline
per GP rollout. Tree hard caps are depth 4 and 31 nodes. It is a regression
checkpoint for development, not an official final evaluation. Choose another
unused output directory when repeating the example; existing results are not
overwritten. The trainer records configuration, source hashes, reference hash,
generation history, rollout logs, candidate selection and `selected_tree.json`.

`compare_dpdp_baselines.py` checks GP–VNSME integration on **instance 2, which is
part of the training set**. It runs both policies with matching simulator/scorer
settings and independently checks their completed logs. This comparison is not
held-out validation or final-test evidence. Pass `--tree` explicitly to compare
the newly trained model; without it the script uses the historical selected tree:

```powershell
.\.venv\Scripts\python.exe compare_dpdp_baselines.py --tree gp_runs\vnsme_v2_new_training_20261108_r1\selected_tree.json --output migration_runs\vnsme_v2_r1_instance2_comparison
```

The runner supports `gp`, `vnsme` and the upstream `demo`. The retired `greedy`,
`baseline` and `insertion` policy names are rejected. Pair insertion remains GP
machinery and requires an explicit candidate ranker. Reference loading checks
policy/version, provenance, positive J values, input/configuration hashes and
independent scores; legacy Greedy summaries are rejected. Reference generation
and adoption are available in `dpdp_vnsme_reference.py`; use a new directory when
regenerating references and pass its summary through `--baseline-summary`.

Historical results and selected GP models remain unchanged. Their normalized
fitness must be interpreted using their recorded definition; newly normalized
VNSME fitness has version `gp-fitness-vnsme-v2`. The legacy single-instance
pilot script keeps its historical raw-J objective. Use the multi-instance
trainer above for the current normalized workflow.
The [migration report](docs/reports/dpdp/VNSME_FITNESS_MIGRATION.md) describes
the earlier interrupted attempts. The reference completion report above records
the successful retries and the ready reference summary now used by training.

## Installation

The package `dvrpsim` requires Python 3.8 or newer.
Since the package is included in the Python Package Index, once you have a Python installation, installing it is as simple as typing it at the command prompt:

```
python -m pip install dvrpsim
```

## References, citation

If you use `dvrpsim` for your research, please consider citing our paper:

Horváth, M., & Tamási, T. (2025). A general modeling and simulation framework for dynamic vehicle routing. <a href="https://doi.org/10.1016/j.ejtl.2025.100159" target="_blank">EURO Journal on Transportation and Logistics, 14, 100159</a>.

```
@article{horvath2025general,
  title={A general modeling and simulation framework for dynamic vehicle routing},
  author={Horv{\'a}th, Mark{\'o} and Tam{\'a}si, T{\'\i}mea},
  journal={EURO Journal on Transportation and Logistics},
  pages={100159},
  year={2025},
  publisher={Elsevier}
}
```
