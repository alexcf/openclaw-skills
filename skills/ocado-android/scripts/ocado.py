#!/usr/bin/env python3
"""Ocado helper — unlock, search, quick-add, checkout via ADB + uiautomator2.

Usage:
    python3 ocado.py unlock          # wake + PIN + open Ocado
    python3 ocado.py search "butter" # search for a product
    python3 ocado.py add "butter" 2  # search + quick-add 2x first match
    python3 ocado.py checkout        # complete checkout if cart has items
    python3 ocado.py status          # show cart total + current screen
    python3 ocado.py login           # open account/login view
"""

import subprocess, sys, time, json, os

# Use uiautomator2 from the android-tools venv
VENV_PYTHON = "/tmp/android-tools/bin/python3"
sys.path.insert(0, "/tmp/android-tools/lib/python3.14/site-packages")

PIN = os.environ.get("OCADO_PIN", "").strip()
OCADO_ACTIVITY = "com.ocadoretail.mobile.android/com.ocado.mobile.android.feature.splash.SplashScreenActivity"

def _require_pin() -> str:
    if not PIN:
        raise RuntimeError("OCADO_PIN environment variable is required")
    return PIN

def adb(cmd: str, timeout: int = 10) -> str:
    """Run an adb shell command, return stdout."""
    r = subprocess.run(
        ["adb", "shell", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    return r.stdout.strip()

def tap(x: int, y: int):
    adb(f"input tap {x} {y}")

def swipe(x1, y1, x2, y2, ms=200):
    adb(f"input swipe {x1} {y1} {x2} {y2} {ms}")

def keyevent(code):
    adb(f"input keyevent {code}")

def screenshot(path="/sdcard/screen.png") -> str:
    """Take screenshot, pull to workspace, return local path."""
    adb(f"screencap -p {path}")
    local = "/tmp/ocado-android-screen.png"
    subprocess.run(["adb", "pull", path, local], capture_output=True, timeout=10)
    return local

def get_focus() -> str:
    """Get current window focus."""
    out = adb("dumpsys window | grep mCurrentFocus")
    return out

def is_locked() -> bool:
    focus = get_focus()
    return "NotificationShade" in focus or "Keyguard" in focus or "StatusBar" in focus

def is_screen_on() -> bool:
    out = adb("dumpsys power | grep mWakefulness")
    return "Awake" in out

def unlock():
    """Wake screen, enter PIN, get to home/app."""
    # Wake
    if not is_screen_on():
        keyevent("KEYCODE_WAKEUP")
        time.sleep(2)

    if not is_locked():
        print("Already unlocked")
        return True

    # Swipe up to PIN screen
    swipe(540, 2300, 540, 400, 200)
    time.sleep(1)

    # Enter PIN via input text (faster than individual keyevents)
    adb(f'input text "{_require_pin()}"')
    time.sleep(0.5)
    keyevent("66")  # ENTER
    time.sleep(2)

    if is_locked():
        # Retry with keyevents
        for digit in _require_pin():
            keyevent(str(7 + int(digit)))
            time.sleep(0.1)
        keyevent("66")
        time.sleep(2)

    ok = not is_locked()
    print(f"Unlock: {'OK' if ok else 'FAILED'}")
    return ok

def open_ocado():
    """Launch or bring Ocado to front."""
    adb(f"am start -n {OCADO_ACTIVITY}")
    time.sleep(4)
    focus = get_focus()
    ok = "ocado" in focus.lower()
    print(f"Ocado: {'open' if ok else 'not open'} ({focus})")
    return ok

def open_ocado_login():
    """Open Ocado and try to reach the login flow.

    This is a non-interactive helper: it will attempt to bring up the
    Sign In screen if it appears, otherwise it will capture and print current
    state for manual login continuation.
    """
    if is_locked():
        try:
            unlock()
        except Exception:
            pass

    if not open_ocado():
        print("WARN: couldn't verify app focus; continuing anyway")

    d = _get_device()

    # Quick path: account button/nav item to login area
    for target in ["Account", "Profile", "Sign in", "Sign In", "Menu", "My account", "Home"]:
        el = d(text=target)
        if el.exists(timeout=2):
            el.click()
            time.sleep(2)
            break
    else:
        # no obvious nav target found
        pass

    # If a sign-in control is visible, open it and stop.
    for target in ["Sign in", "Sign In", "Log in", "Log In"]:
        btn = d(text=target)
        if btn.exists(timeout=1):
            btn.click()
            time.sleep(2)
            print(f"Opened login target: {target}")
            path = screenshot()
            print(f"Screenshot: {path}")
            return

    # Already signed in indicators
    if any(d(text=t).exists(timeout=1) for t in ["Sign out", "Orders", "Basket", "Trolley"]):
        print("Already signed in or login already bypassed by existing session")
        path = screenshot()
        print(f"Screenshot: {path}")
        return

    print("Login controls were not auto-detected; opened Ocado and captured screenshot.")
    path = screenshot()
    print(f"Screenshot: {path}")
    print("Open the app and complete sign-in manually if required.")

def _get_device():
    """Get connected uiautomator2 device."""
    import uiautomator2 as u2
    return u2.connect()


def search_product(query: str, collect: bool = False, max_scroll: int = 3):
    """Search for a product in Ocado.

    Args:
        query: Search query string
        collect: If True, scroll through results and return descriptions (changes scroll state!)
        max_scroll: Max scrolls for collection

    Returns list of result descriptions found (empty list if collect=False but search succeeded).
    Returns None if search failed entirely.
    """
    d = _get_device()

    # Go to Home tab first to reset state
    home = d(text="Home")
    if home.exists(timeout=2):
        home.click()
        time.sleep(2)

    # Find and tap search field
    search_field = d(descriptionContains="Find a product")
    if not search_field.exists(timeout=3):
        search_field = d(descriptionContains="Search field")
    if not search_field.exists(timeout=3):
        search_field = d(descriptionContains="Search")

    if search_field.exists(timeout=3):
        search_field.click()
        time.sleep(2)
    else:
        print("ERROR: Could not find search field")
        return None

    # Clear any existing text and type query
    d.set_input_ime(True)
    time.sleep(0.3)
    d.clear_text()
    time.sleep(0.3)
    d.send_keys(query)
    time.sleep(0.5)
    d.press("enter")
    d.set_input_ime(False)

    # Wait for results to load — look for product cards or "No results"
    for _ in range(10):
        time.sleep(1)
        if d(descriptionContains="No results found").exists(timeout=0.5):
            print(f"No results for: {query}")
            return []
        if d(descriptionContains="Price £").exists(timeout=0.5):
            break
    else:
        print(f"Timeout waiting for search results: {query}")
        return None

    print(f"Searched: {query}")

    if collect:
        return _collect_results(d, max_scroll)
    return []


def _collect_results(d, max_scroll: int = 3):
    """Collect product results from current screen, optionally scrolling."""
    import xml.etree.ElementTree as ET
    seen = []

    for scroll in range(max_scroll + 1):
        xml_str = d.dump_hierarchy()
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            desc = elem.attrib.get('content-desc', '')
            if 'Price £' in desc and len(desc) > 30:
                if desc not in seen:
                    seen.append(desc)
        if scroll < max_scroll:
            d.swipe(540, 1800, 540, 600, 0.5)
            time.sleep(2)

    return seen


def find_and_add_product(query: str, quantity: int = 1, prefer_match: str = None):
    """Search, find the best matching product, and add it to trolley.

    Args:
        query: Search query string
        quantity: How many to add (default 1)
        prefer_match: Optional substring to prefer in results (e.g. "M&S")

    Returns:
        dict with 'success', 'product', 'price', 'screenshot' keys
    """
    import xml.etree.ElementTree as ET
    d = _get_device()

    # Search (don't collect — leave scroll state at top of results)
    result = search_product(query)
    if result is None:
        return {"success": False, "product": None, "error": "Search failed"}

    # Now scroll through results looking for the preferred match
    # or collect the first result if no preference
    target = None
    tap_name = None

    for scroll in range(6):
        xml_str = d.dump_hierarchy()
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            desc = elem.attrib.get('content-desc', '')
            if 'Price £' not in desc or len(desc) < 30:
                continue

            # Check if this matches our preference
            if prefer_match and prefer_match.lower() in desc.lower():
                target = desc
                break
            elif not prefer_match and target is None:
                target = desc

        if target:
            break
        d.swipe(540, 1800, 540, 600, 0.5)
        time.sleep(2)

    if not target:
        return {"success": False, "product": None, "error": f"No matching product found for '{query}'" +
                (f" with preference '{prefer_match}'" if prefer_match else "")}

    # Extract product info
    product_name = target.split(". Price")[0].strip() if ". Price" in target else target[:80]
    price = ""
    if "Price £" in target:
        price_part = target.split("Price £")[1]
        price = "£" + price_part.split(",")[0].split(".")[0] + "." + price_part.split(".")[1][:2]

    # Core name for element matching (before first comma)
    tap_name = product_name.split(",")[0].strip()

    print(f"Selected: {product_name} ({price})")

    # The product should be visible on screen right now (we just found it in hierarchy)
    product_elem = d(descriptionContains=tap_name)
    if not product_elem.exists(timeout=3):
        return {"success": False, "product": product_name, "error": "Product found in hierarchy but not tappable"}

    product_elem.click()
    time.sleep(4)

    # Find and tap Add button
    add_btn = d(descriptionContains="Add,")
    if not add_btn.exists(timeout=5):
        add_btn = d(descriptionContains="Add to trolley")
    if not add_btn.exists(timeout=3):
        # Product might already be in trolley — check for quantity controls
        if d(descriptionContains="in trolley").exists(timeout=2):
            print(f"Already in trolley — incrementing")
            # Increment button desc format: "N in trolley, Add<ProductName>" (no space after Add)
            inc = d(descriptionContains="in trolley, Add")
            if inc.exists(timeout=2):
                for _ in range(quantity):
                    inc.click()
                    time.sleep(1.5)
                path = screenshot()
                # Read new quantity
                trolley_info = d(descriptionContains="in trolley")
                qty_text = trolley_info.info.get("contentDescription", "") if trolley_info.exists(timeout=1) else ""
                return {"success": True, "product": product_name, "price": price,
                        "screenshot": path, "note": f"incremented existing ({qty_text})"}

        return {"success": False, "product": product_name, "error": "No Add button found"}

    add_btn.click()
    time.sleep(3)

    # For quantity > 1, find the increment button and tap it (quantity-1) times
    if quantity > 1:
        inc_btn = d(descriptionContains="Add" + product_name[:20])
        if not inc_btn.exists(timeout=2):
            inc_btn = d(descriptionContains="Increase quantity")
        if inc_btn.exists(timeout=2):
            for _ in range(quantity - 1):
                inc_btn.click()
                time.sleep(1)

    # Verify it's in trolley
    time.sleep(2)
    in_trolley = d(descriptionContains="in trolley").exists(timeout=3)

    path = screenshot()
    print(f"{'Added' if in_trolley else 'Add attempted'}: {product_name} x{quantity}")

    return {
        "success": in_trolley,
        "product": product_name,
        "price": price,
        "quantity": quantity,
        "screenshot": path,
    }


def quick_add(quantity: int = 1):
    """Legacy quick-add — wraps find_and_add_product for backwards compat.

    NOTE: This requires search_product() to have been called first.
    It re-reads the screen and adds the first visible product.
    Prefer find_and_add_product() for new code.
    """
    d = _get_device()

    # Find first product on screen
    import xml.etree.ElementTree as ET
    xml_str = d.dump_hierarchy()
    root = ET.fromstring(xml_str)
    first_product = None
    for elem in root.iter():
        desc = elem.attrib.get('content-desc', '')
        if 'Price £' in desc and len(desc) > 30:
            first_product = desc
            break

    if not first_product:
        print("No products found on screen")
        return screenshot()

    # Extract name for tapping
    product_name = first_product.split(". Price")[0].strip() if ". Price" in first_product else first_product[:60]
    print(f"Quick-adding first result: {product_name[:60]}")

    # Tap product
    product_elem = d(descriptionContains=product_name[:40])
    if product_elem.exists(timeout=3):
        product_elem.click()
        time.sleep(4)

        # Tap Add button
        add_btn = d(descriptionContains="Add,")
        if not add_btn.exists(timeout=3):
            add_btn = d(descriptionContains="Add to trolley")
        if add_btn.exists(timeout=3):
            add_btn.click()
            time.sleep(3)

            # Increment if quantity > 1
            if quantity > 1:
                for _ in range(quantity - 1):
                    inc = d(descriptionContains="Add" + product_name[:20])
                    if inc.exists(timeout=2):
                        inc.click()
                        time.sleep(1)

    path = screenshot()
    print(f"Quick-added x{quantity}")
    return path

def checkout():
    """Navigate to trolley and complete checkout if cart has items.
    
    Returns True if checkout was completed, False if cart empty or failed.
    """
    import uiautomator2 as u2
    d = u2.connect()

    # Go to Trolley tab
    if d(text="Trolley").exists(timeout=2):
        d(text="Trolley").click()
        time.sleep(3)

    # Check for "Checkout to save changes" (editing existing order)
    # or "Checkout" (new order)
    checkout_btn = None
    for label in ["Checkout to save changes", "Checkout"]:
        if d(text=label).exists(timeout=2):
            checkout_btn = label
            break

    if not checkout_btn:
        # Check if cart is empty
        if d(text="Empty").exists(timeout=1):
            print("Cart is empty — nothing to checkout")
            return False
        print("No checkout button found")
        screenshot()
        return False

    print(f"Found: {checkout_btn}")
    d(text=checkout_btn).click()
    time.sleep(5)

    # Handle upsell pages — keep scrolling and clicking Continue
    for attempt in range(10):
        if d(text="Place order").exists(timeout=2):
            d(text="Place order").click()
            print("Placed order!")
            time.sleep(5)
            # Verify
            if d(textContains="order has been placed").exists(timeout=5):
                print("Order confirmed!")
                screenshot()
                return True
            screenshot()
            return True

        if d(text="Amend order").exists(timeout=1):
            d(text="Amend order").click()
            print("Amended order!")
            time.sleep(5)
            screenshot()
            return True

        # Scroll past upsell pages
        if d(text="Continue checkout").exists(timeout=1):
            # Scroll to bottom first
            for _ in range(20):
                d.swipe(540, 2200, 540, 200, duration=0.15)
                time.sleep(0.2)
            time.sleep(1)
            if d(text="Continue checkout").exists(timeout=1):
                d(text="Continue checkout").click()
                print(f"Continue checkout (attempt {attempt+1})")
                time.sleep(4)
        else:
            # Try scrolling to find buttons
            for _ in range(5):
                d.swipe(540, 2000, 540, 400, duration=0.2)
                time.sleep(0.3)
            time.sleep(1)

    print("Checkout flow didn't complete after 10 attempts")
    screenshot()
    return False

def get_status():
    """Get current cart total and screen info."""
    focus = get_focus()
    path = screenshot()
    size = os.path.getsize(path)
    print(f"Focus: {focus}")
    print(f"Screenshot: {path} ({size} bytes)")
    if size < 20000:
        print("Screen appears off/black")
    return path

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "unlock":
        unlock()
        open_ocado()

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: ocado.py search <query>")
            return
        query = " ".join(sys.argv[2:])
        if is_locked():
            unlock()
        open_ocado()
        search_product(query)
        path = screenshot()
        print(f"Screenshot: {path}")

    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: ocado.py add <query> [quantity] [--prefer brand]")
            return
        query = sys.argv[2]
        qty = 1
        prefer = None
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--prefer" and i + 1 < len(sys.argv):
                prefer = sys.argv[i + 1]
                i += 2
            else:
                try:
                    qty = int(sys.argv[i])
                except ValueError:
                    pass
                i += 1
        if is_locked():
            unlock()
        open_ocado()
        result = find_and_add_product(query, quantity=qty, prefer_match=prefer)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "checkout":
        if is_locked():
            unlock()
        open_ocado()
        ok = checkout()
        print(f"Checkout: {'SUCCESS' if ok else 'SKIPPED/FAILED'}")

    elif cmd == "status":
        get_status()

    elif cmd == "login":
        open_ocado_login()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
