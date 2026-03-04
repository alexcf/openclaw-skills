#!/usr/bin/env python3
"""
Ocado Skill — CLI wrapper for the Ocado Android automation helper.

Wraps ../android/scripts/ocado.py (ADB + uiautomator2)
and an optional MCP server companion in the host repo.

Usage:
    ocado_skill.py search <query>          # Search for products
    ocado_skill.py add <query> [qty]       # Add item to basket
    ocado_skill.py view-basket             # View basket contents
    ocado_skill.py checkout                # Complete checkout
    ocado_skill.py unlock                  # Unlock phone + open Ocado
    ocado_skill.py status                  # Get current state + screenshot

Device: Android phone authenticated via `OCADO_ANDROID_SERIAL`
ADB path: /opt/homebrew/bin/adb
Python venv: /tmp/android-tools/

Architecture:
    - Text-based UI elements are detected via uiautomator2 (reliable)
    - Compose elements without text fall back to coordinate taps
    - The MCP server exposes these as tools for agent use
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
OCADO_SCRIPT = REPO_ROOT / "skills" / "ocado-android" / "scripts" / "ocado.py"
VENV_PYTHON = "/tmp/android-tools/bin/python3"
ADB_PATH = "/opt/homebrew/bin/adb"
DEVICE_SERIAL = os.environ.get("OCADO_ANDROID_SERIAL", "").strip()

# Ensure ADB uses the right device
os.environ["ANDROID_SERIAL"] = DEVICE_SERIAL

# Add ADB to PATH if needed
adb_dir = str(Path(ADB_PATH).parent)
if adb_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{adb_dir}:{os.environ.get('PATH', '')}"


# ─── Helpers ────────────────────────────────────────────────────────────────

def run_ocado(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """
    Run a command via the ocado.py helper using the venv Python.
    Returns (returncode, stdout, stderr).
    """
    # Try venv Python first (has uiautomator2), fall back to system
    python = VENV_PYTHON if Path(VENV_PYTHON).exists() else sys.executable

    cmd = [python, str(OCADO_SCRIPT)] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "ANDROID_SERIAL": DEVICE_SERIAL},
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return 1, "", f"Script not found: {e}"


def run_u2(script: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run an inline uiautomator2 Python script."""
    python = VENV_PYTHON if Path(VENV_PYTHON).exists() else sys.executable
    try:
        result = subprocess.run(
            [python, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "ANDROID_SERIAL": DEVICE_SERIAL},
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Script timed out after {timeout}s"


def adb(cmd: str, timeout: int = 10) -> str:
    """Run an adb shell command."""
    try:
        result = subprocess.run(
            [ADB_PATH, "-s", DEVICE_SERIAL, "shell", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ADB error: {e}"


def check_device():
    """Check if the device is connected and accessible."""
    if not DEVICE_SERIAL:
        print("Missing OCADO_ANDROID_SERIAL environment variable", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            [ADB_PATH, "devices"],
            capture_output=True, text=True, timeout=5,
        )
        if DEVICE_SERIAL in result.stdout:
            return True
        print(f"⚠️  Device {DEVICE_SERIAL} not found in adb devices", file=sys.stderr)
        print(f"   Connected devices: {result.stdout.strip()}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"❌ ADB not found at {ADB_PATH}", file=sys.stderr)
        return False


# ─── Commands ───────────────────────────────────────────────────────────────

def cmd_search(query: str):
    """Search for a product and display results."""
    print(f"🔍 Searching Ocado for: {query}")
    rc, out, err = run_ocado(["search", query], timeout=90)

    if out:
        print(out)
    if err:
        # stderr from the script has progress info
        for line in err.splitlines():
            if line.strip() and not line.startswith("Traceback"):
                print(f"  {line}", file=sys.stderr)

    if rc != 0 and not out:
        print(f"❌ Search failed (exit {rc})", file=sys.stderr)
        if err:
            print(err, file=sys.stderr)
        sys.exit(1)

    # Show screenshot path if in output
    screenshot_line = [l for l in out.splitlines() if "Screenshot:" in l]
    if screenshot_line:
        print(f"\n📸 {screenshot_line[-1]}")


def cmd_add(query: str, qty: int = 1):
    """Add a product to basket."""
    print(f"➕ Adding to basket: {query} x{qty}")
    rc, out, err = run_ocado(["add", query, str(qty)], timeout=120)

    if out:
        print(out)
    if err:
        for line in err.splitlines():
            if line.strip() and not line.startswith("Traceback"):
                print(f"  {line}", file=sys.stderr)

    if rc != 0:
        print(f"❌ Add to basket failed (exit {rc})", file=sys.stderr)
        sys.exit(1)

    screenshot_line = [l for l in out.splitlines() if "Screenshot:" in l]
    if screenshot_line:
        print(f"\n📸 {screenshot_line[-1]}")


def cmd_view_basket():
    """View current basket contents using uiautomator2."""
    print("🛒 Viewing basket...")

    # Use uiautomator2 to navigate to Trolley and read contents
    script = """
import uiautomator2 as u2
import time

d = u2.connect()

# Ensure Ocado is open and go to Trolley tab
if d(text="Trolley").exists(timeout=3):
    d(text="Trolley").click()
    time.sleep(3)
else:
    print("OCADO_NOT_OPEN")
    exit(1)

# Check for empty cart
if d(text="Empty").exists(timeout=2) or d(textContains="Your trolley is empty").exists(timeout=2):
    print("CART_EMPTY")
    exit(0)

# Collect visible text from trolley
import sys
els = d(textMatches=".+")
seen = set()
lines = []
for el in els:
    try:
        info = el.info
        t = info['text'].strip()
        bounds = info.get('bounds', {})
        y = bounds.get('top', 0) if bounds else 0
        if t and len(t) > 1 and t not in seen:
            seen.add(t)
            lines.append((y, t))
    except:
        pass

# Sort by vertical position
lines.sort(key=lambda x: x[0])
for _, text in lines:
    print(text)
"""

    rc, out, err = run_u2(script, timeout=30)

    if "OCADO_NOT_OPEN" in out:
        print("⚠️  Ocado is not open. Trying to unlock and open...", file=sys.stderr)
        run_ocado(["unlock"], timeout=30)
        rc, out, err = run_u2(script, timeout=30)

    if "CART_EMPTY" in out:
        print("🛒 Basket is empty")
        return

    if out.strip():
        print("\n🛒 Basket Contents:")
        print("-" * 40)
        for line in out.strip().splitlines():
            if line.strip():
                print(f"  {line}")
    else:
        print("⚠️  Could not read basket contents", file=sys.stderr)
        if err:
            print(err, file=sys.stderr)


def cmd_checkout():
    """Complete the checkout flow."""
    print("💳 Starting checkout...")
    rc, out, err = run_ocado(["checkout"], timeout=180)

    if out:
        print(out)
    if err:
        for line in err.splitlines():
            if line.strip() and not line.startswith("Traceback"):
                print(f"  {line}", file=sys.stderr)

    if "SUCCESS" in out:
        print("✅ Checkout completed!")
    elif "SKIPPED" in out or "FAILED" in out:
        print("⚠️  Checkout did not complete — check device", file=sys.stderr)
        sys.exit(1)


def cmd_unlock():
    """Unlock phone and open Ocado."""
    print("📱 Unlocking and opening Ocado...")
    rc, out, err = run_ocado(["unlock"], timeout=60)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)


def cmd_status():
    """Get current device state."""
    print("📊 Getting device status...")
    rc, out, err = run_ocado(["status"], timeout=30)
    if out:
        print(out)
    if err:
        for line in err.splitlines():
            if line.strip():
                print(f"  {line}", file=sys.stderr)


# ─── MCP Server Info ────────────────────────────────────────────────────────

def cmd_mcp_info():
    """Show info about the MCP server."""
    mcp_server = REPO_ROOT / "scripts" / "android" / "mcp-server" / "server.js"
    if not mcp_server.exists():
        print(f"❌ MCP server not found at {mcp_server}", file=sys.stderr)
        return

    print("🔌 Android MCP Server")
    print(f"   Location: {mcp_server}")
    print(f"   Runtime: node")
    print()
    print("   Available tools:")
    tools = [
        ("android_status", "Device state + visible elements"),
        ("android_unlock", "Wake + unlock PIN"),
        ("android_launch", "Launch app by package"),
        ("android_tap", "Tap by text/description/coords"),
        ("android_type", "Type text"),
        ("android_swipe", "Swipe gesture"),
        ("android_back", "Press back"),
        ("android_screenshot", "Screenshot (vision)"),
        ("android_elements", "List all visible text"),
        ("ocado_search", "Search Ocado product"),
        ("ocado_quick_add", "Quick-add search result"),
        ("ocado_checkout", "Complete checkout"),
        ("android_notifications", "Get notifications"),
        ("android_notification_log", "Read notification log"),
    ]
    for name, desc in tools:
        print(f"   - {name}: {desc}")

    print()
    print("   Start MCP server:")
    print(f"   cd {mcp_server.parent} && node server.js")


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ocado CLI — shop via Android automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    search_p = sub.add_parser("search", help="Search for products")
    search_p.add_argument("query", nargs="+", help="Search query")

    add_p = sub.add_parser("add", help="Add product to basket")
    add_p.add_argument("query", nargs="+", help="Product name/query")
    add_p.add_argument("qty", nargs="?", type=int, default=1, help="Quantity (default: 1)")

    sub.add_parser("view-basket", help="View basket contents")
    sub.add_parser("checkout", help="Complete checkout")
    sub.add_parser("unlock", help="Unlock phone and open Ocado")
    sub.add_parser("status", help="Get device status + screenshot")
    sub.add_parser("mcp-info", help="Show MCP server info")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Check device connectivity for device-dependent commands
    device_cmds = {"search", "add", "view-basket", "checkout", "unlock", "status"}
    if args.command in device_cmds:
        if not check_device():
            print("❌ Device not connected. Set OCADO_ANDROID_SERIAL and verify ADB connectivity.", file=sys.stderr)
            sys.exit(1)

    if args.command == "search":
        cmd_search(" ".join(args.query))

    elif args.command == "add":
        cmd_add(" ".join(args.query), args.qty)

    elif args.command == "view-basket":
        cmd_view_basket()

    elif args.command == "checkout":
        cmd_checkout()

    elif args.command == "unlock":
        cmd_unlock()

    elif args.command == "status":
        cmd_status()

    elif args.command == "mcp-info":
        cmd_mcp_info()


if __name__ == "__main__":
    main()
