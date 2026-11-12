# VNSME v3 references 3–6 — status

Run root: `vnsme_runs/v3_references_3_6_20261109_r1/`

- Instance 3: completed and accepted. 160 routing decisions; 78 of 78 items delivered; independent replay PASS; D=487.2 km; T=0 seconds; J=97.44. The single-instance v3 summary passed `load_reference`.
- Instance 4: INTERRUPTED during epoch 00105. There were 106 epoch starts and 105 epoch end markers. The last heartbeat recorded 863.65 seconds rollout elapsed and 300.23 Java CPU seconds. No final record or final supervisor JSON exists, so this run is not accepted. See `instance4_epoch_count_correction.md`.
- Instances 5 and 6: not started in this historical run.
- No combined reference summary for 2–6 was produced. The accepted instance 2 artifacts were left untouched.

The instance 4 partial logs remain intact for diagnosis. No GP training or final-test instance was run.