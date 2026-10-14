# Live concurrency increase on 2026-10-12

At the user's request to accelerate the Qwen-only experiment, the running worker pool was increased from 24 to 32 workers (six to eight per replica) at 11:50:07 Hong Kong time. The remote execution configuration was replaced atomically; the existing worker supervisor discovers the added slots during its normal loop. The four services already permit eight active requests each.

Before the change, all 24 workers and four services were healthy, recent total generation throughput averaged 505.9 tokens/s, and no infrastructure failure was recorded. Existing workers and services were not restarted. The scientific source, case scope, token caps and SA reuse remain unchanged.

The original launch manifests are retained as records of the configuration at launch. The separate `scale_24_to_32.json` receipt records the live change and the original worker identities. Use `execution/status.json` for current worker counts; the pipeline's `running_workers` field is only its startup snapshot.

Configuration SHA256 changed from `408eb602972f867cf57239fbadab422da2b184eb32c2111d00a9c58c00d38e1f` to `95a1d1b946c056d0fdde500a4a23ba1981c0973ee2de38a097d75d123e52de6f`.

At 11:52:23 HKT, all 32 workers remained running, including the original 24. The recent one-minute total generation throughput was 619.82 tokens/s, versus 505.9 tokens/s before expansion (22.5% higher in this short observation). All four services had eight active requests and zero waiting requests; KV cache use ranged from 57.9% to 74.4%, with no logged error or preemption. There were 128 calls completed with valid usage accounting, no usage issues or infrastructure failures, and no fully completed arm yet. This observation is saved in `verification_stable.json`; it does not establish the whole-run speedup.
