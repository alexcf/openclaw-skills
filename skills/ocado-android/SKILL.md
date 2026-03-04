# ocado-android

Automate Ocado product search/add/checkout on an Android phone via ADB and uiautomator2.

## Quick start

- Ensure the target Android device is connected and trusted.
- Set `OCADO_PIN` in the environment for device unlock.
- Optionally set `OCADO_ANDROID_DEVICE` / `ANDROID_SERIAL`.

```bash
cd skills/ocado-android
python3 scripts/ocado.py unlock
python3 scripts/ocado.py search "butter"
python3 scripts/ocado.py add "whole milk" 2 --prefer "M&S"
python3 scripts/ocado.py status
python3 scripts/ocado.py checkout
```

## Runtime expectations

- Device automation uses local ADB + uiautomator2.
- No remote services are called by these scripts.
- Configure runtime paths as needed for your environment.

## Commands

- `unlock`: wake and unlock phone, then open Ocado
- `search <query>`: locate search results for a product
- `add <query> [quantity] [--prefer <brand>]`: add best matching item
- `checkout`: navigate to trolley and attempt checkout
- `status`: capture current focus and screenshot

## Notes

- `checkout` handles typical upsell and place/amend flows.
- Snapshot output includes a screenshot path and text summary.
