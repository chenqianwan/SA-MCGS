# Qwen72 checkpoint restoration

The new model location is `/aifs4su/hansirui_3rd/chenlong/q72awq_20261012/model`.
This preparation only downloads and verifies public model files. It launches no inference
and does not stop any existing service. It leaves the old 2026-09-24 model directory and
receipts unchanged.

The pinned repository is `Qwen/Qwen2.5-72B-Instruct-AWQ`, revision
`698703eae6604af048a3d2f509995dc302088217`. The original official metadata is frozen at
SHA256 `8b97f046d6a87d6807c86e1b3ab62ffbc5421e2694e83ad58c118cad222e2a58`.
There are 21 model files totaling 41,607,438,677 bytes. Each file must match its recorded
size and official LFS SHA256 or Git blob hash; SHA256 is recorded for every verified file.

`stage_model_restore.py --launch` stages checksummed scripts and calls the durable,
locked `start_model_restore_once.py`. That launcher uses the existing allocation 415747
on dgx-061, 4 CPUs, `--gres=none`, with a two-hour step limit. A persistent launch receipt
prevents duplicate dispatch; the download itself also holds a lock. Do not delete a
receipt or relaunch after an ambiguous outcome. Inspect the remote files first.

The observed step is **415747.35**, started **2026-10-12 00:30:42 HKT**. Live status is
`model_restore_status.json` in the remote deployment directory. Completion requires
`state=complete`, `verified=true`, and all 21 files in `model_download_complete.json`.
The completion receipt is also written to `/aifs4su/hansirui_3rd/chenlong/q72awq_20261012/model_download_complete.json`.
The model must not be started merely because an old receipt or `config.json` exists.

The shared filesystem reported approximately 3.88 TB free before staging. Both the
launcher and worker require at least 64 GiB free before starting the restoration.
