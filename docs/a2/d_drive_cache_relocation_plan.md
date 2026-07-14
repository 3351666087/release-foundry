# Reversible D-drive cache and model relocation proposal

This proposal changes only caches and model storage. It never moves credential files, `Ashr_key.txt`, user profiles, or private evidence.

## Preconditions

- Keep at least 10 GB free on D: after relocation.
- Record current environment variables and directory junctions before changing anything.
- Stop Ollama and all Python processes that write the selected caches.
- Copy first, verify counts and hashes, then switch configuration. Do not delete the source during the validation window.

## Candidate destinations

```text
D:\Ashr\cache\pip
D:\Ashr\cache\huggingface
D:\Ashr\cache\ollama-models
D:\Ashr\cache\temp
```

## Environment variables

```powershell
$env:PIP_CACHE_DIR = 'D:\Ashr\cache\pip'
$env:HF_HOME = 'D:\Ashr\cache\huggingface'
$env:OLLAMA_MODELS = 'D:\Ashr\cache\ollama-models'
```

Persist these only after a one-process smoke test succeeds. `TEMP`/`TMP` should not be changed globally until application compatibility is verified.

## Verification and rollback

1. Verify the copied file count, total byte count, and representative SHA-256 hashes.
2. Start one Ollama instance using `OLLAMA_MODELS` and confirm model listing plus one non-release smoke request.
3. Run the A2 offline suite and CL hygiene gate.
4. Keep the old cache directories untouched for one validation round.
5. Roll back by stopping writers, restoring the recorded environment variables, and restarting Ollama. The copied D: caches may then remain inert; credentials are unaffected.

No relocation was executed in Round 28 because C: has only about 0.24 GB free and an interrupted copy could worsen system stability. This document is a reversible plan, not proof that migration occurred.
