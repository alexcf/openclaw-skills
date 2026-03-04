# Ocado Procedures

## Script entrypoint

- Script: `scripts/ocado.py`
- Command: `python3 scripts/ocado.py <command> ...`
- Device automation: ADB + uiautomator2

## Supported commands

- `unlock`: wake + PIN + open Ocado
- `login`: attempt to open account/sign-in route and capture a state screenshot
- `search "<query>"`: search product catalog
- `add "<query>" [quantity] [--prefer <brand>]`: search + add best-matched product
- `checkout`: navigate trolley and complete checkout flow
- `status`: capture screenshot and report current screen focus

## Checkout rules

1. Slot priority: next Sunday -> 7:00am -> 7:30am -> 6:30am. Error if no slot available.
2. Minimum basket threshold: £40.
3. If under threshold: add Nyetimber Classic Cuvée as fallback product to reach minimum.
4. Checkout means **place order** (reserves the delivery slot).

## Product handling preferences

- Never replace frozen-only products with chilled/fresh alternatives.
- Use `--prefer <brand>` when a specific brand is requested.
- For out-of-stock handling, detect `Unavailable` in descriptions, report alternatives,
  and do not substitute automatically.

## Access policy

- Family-level access can include search/add/stock checks.
- Slot booking and final checkout should be approval-gated.