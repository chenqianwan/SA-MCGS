# Recovery on 2026-10-12

The first pipeline (step 415747.39) stopped at 01:00:55 Hong Kong time because the shared Python runtime does not expose `os.pidfd_open`. No termination signal or scientific inference request had been sent. The failed pipeline receipts, retirement receipt, logs, previous retirement source and staging manifest are preserved in the corresponding remote recovery directory with SHA256 hashes.

The retirement helper now uses its existing pidfd path when available. Otherwise, it rechecks the exact prior supervisor's PID, owner, command, process start time, allocation and step immediately before sending SIGTERM. Completed-work checks, three idle metric samples and duplicate-signal protection remain in place. Eleven isolated checks passed without sending real signals.

At the user's request, worker concurrency was increased from four to six per replica: four TP2 Qwen2.5-72B services, eight H800 GPUs and 24 baseline arm workers. Service `max_num_seqs` remains eight. This overrides the initial four-worker setting described in the original run preparation README. Case scope, estimates, algorithms and scientific token accounting remain unchanged. SA is still reused without inference.

The restarted pipeline is step 415747.41; its model service step is 415747.42. The old supervisor was retired successfully and all old ports closed. Further runtime status is recorded under the experiment's `deployment/pipeline_status.json` and `execution/status.json` on the cluster.
