# ocado-cli

A command-oriented wrapper around the Ocado Android automation flows.

## Quick start

- Set required environment:
  - `OCADO_PIN`
  - `OCADO_ANDROID_SERIAL`
- Run from within this directory:

```bash
cd skills/ocado-cli
python3 scripts/ocado_skill.py unlock
python3 scripts/ocado_skill.py login
python3 scripts/ocado_skill.py search "baked beans"
python3 scripts/ocado_skill.py add "whole milk" 2 --prefer "M&S"
python3 scripts/ocado_skill.py view-basket
python3 scripts/ocado_skill.py status
python3 scripts/ocado_skill.py checkout
```

## Notes

- `login` opens the account/login flow if a recognized login control is visible; otherwise it will capture the current Ocado screen for manual continuation.
- `view-basket` attempts to read visible trolley text and may require a readable UI state.
- Keep credentials and pins in environment, not committed to source.
- No third-party API calls are made by this skill.

## Included tools

- `scripts/ocado_skill.py`: CLI orchestrator
- `../ocado-android/scripts/ocado.py`: shared command implementation