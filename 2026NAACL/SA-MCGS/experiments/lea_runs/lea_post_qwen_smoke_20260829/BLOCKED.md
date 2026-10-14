# Blocked smoke run

This smoke was stopped on 2026-08-29 after the configured provider returned
`503 model_not_found` for the exact mapped model `qwen2.5-72b-instruct`.
No result artifact was accepted. The call log is retained as provider evidence;
`status.json` was refreshed with `--validate-only` to clear the interrupted
active marker. Do not resume this directory or substitute another Qwen model.
Use a fresh `smoke_v2` directory after the exact 72B channel is restored.
