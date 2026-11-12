# Instance 4 interruption: epoch-count correction

This note corrects the epoch-count wording in `instance4_interrupted.json`. That historical JSON is preserved unchanged (SHA-256: `406f3ba7fe15e0d0ca88d14983dadd47e438e3f64bf5a8458341cd7e984dcd32`). Its `completed_epochs: 106` field must be read as **106 epochs started**, not 106 epochs completed.

Artifact inspection found 106 `invocation_start.json` markers (00000–00105) and 105 `invocation_process_end.json` markers (00000–00104). Epoch 00105 was active at the last heartbeat and has no process-end marker. There is no final simulation result, reference record, or final supervisor JSON. Instance 4 is therefore INTERRUPTED and unaccepted; this is not evidence of a Java timeout or algorithm failure.

The supervisor creates a Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. After the interrupted session was stopped, a process inspection found zero `java.exe` processes. This supports that the Java child was terminated with the job cleanup. Since the supervisor did not write its final supervision JSON, this historical run does not satisfy the valid-supervision acceptance gate.

No verified end-to-end checkpoint/resume mechanism exists. A new instance 4 run must start from the beginning in a fresh output directory. Do not join the partial epoch logs to another rollout.