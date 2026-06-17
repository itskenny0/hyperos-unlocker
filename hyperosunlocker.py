import hashlib
import json
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

import ntplib
import pytz
import urllib3

# Enable ANSI/VT processing on modern Windows consoles; harmless elsewhere.
try:
    from colorama import just_fix_windows_console
    just_fix_windows_console()
except Exception:
    pass


# ──────────────────────────────────────────────────────────────────────────
#  Palette  ·  "midnight launch console"  —  amber on ink, electric accents
# ──────────────────────────────────────────────────────────────────────────
def _fg(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"


def _bg(r, g, b):
    return f"\x1b[48;2;{r};{g};{b}m"


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

AMBER = _fg(245, 166, 35)      # Xiaomi-orange primary
AMBER_HI = _fg(255, 184, 84)   # bright accent
CORAL = _fg(255, 92, 87)       # errors
MINT = _fg(90, 247, 142)       # success
CYAN = _fg(87, 199, 255)       # info / links
TEXT = _fg(228, 228, 231)      # body
MUTED = _fg(108, 112, 134)     # secondary
LINE = _fg(58, 61, 77)         # borders / rails
INK = _fg(16, 17, 24)          # badge foreground on light bg

W = 64                          # interior width of panels / rules
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _vlen(s):
    """Visible length, ignoring ANSI escapes (for alignment)."""
    return len(_ANSI.sub("", s))


# ── UI primitives ──────────────────────────────────────────────────────────
def banner():
    sys.stdout.write("\x1b[2J\x1b[H")  # clear screen, home cursor
    title = "H Y P E R O S   U N L O C K E R"
    print()
    print(f"  {AMBER}{BOLD}⬢{RESET}  {AMBER_HI}{BOLD}{title}{RESET}")
    print(f"     {MUTED}midnight bootloader sniper · beijing time (UTC+8){RESET}")
    print(f"  {LINE}{'─' * W}{RESET}")


def panel(title, lines, accent=AMBER):
    t = f"{accent}{BOLD}{title}{RESET}"
    head = f"{LINE}╭─ {t} {LINE}{'─' * (W - 3 - _vlen(t))}╮{RESET}"
    body = [
        f"{LINE}│{RESET} {ln}{' ' * max(0, W - 2 - _vlen(ln))} {LINE}│{RESET}"
        for ln in lines
    ]
    foot = f"{LINE}╰{'─' * W}╯{RESET}"
    return "\n".join([head, *body, foot])


def section(tag, title):
    print()
    print(f"  {AMBER}{BOLD}{tag}{RESET}  {TEXT}{BOLD}{title}{RESET}")
    print(f"  {LINE}{'─' * W}{RESET}")


def _line(glyph, color, text):
    print(f"  {color}{glyph}{RESET}  {text}")


def step(t):
    _line("›", AMBER, t)


def ok(t):
    _line("✓", MINT, t)


def warn(t):
    _line("▲", AMBER_HI, t)


def err(t):
    _line("✗", CORAL, t)


def info(t):
    _line("•", CYAN, t)


def live(text):
    """Render an updating, single-line status (no newline)."""
    sys.stdout.write("\r\x1b[K  " + text)
    sys.stdout.flush()


def clear_live():
    sys.stdout.write("\r\x1b[K")
    sys.stdout.flush()


def confirm(question):
    print(f"  {CYAN}?{RESET}  {TEXT}{question}{RESET} {MUTED}[y/N]{RESET} ", end="")
    return input().strip().lower() in ("y", "yes")


def result(title, lines, accent):
    print()
    print(panel(title, lines, accent))
    print()


# ──────────────────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────────────────
NTP_SERVERS = [
    "ntp0.ntp-servers.net", "ntp1.ntp-servers.net", "ntp2.ntp-servers.net",
    "ntp3.ntp-servers.net", "ntp4.ntp-servers.net", "ntp5.ntp-servers.net",
    "ntp6.ntp-servers.net",
]

MI_ACCOUNT_URL = "https://account.xiaomi.com/fe/service/login/password?_locale=en_IN&checkSafePhone=false&sid=18n_bbs_global&qs=%253Fcallback%253Dhttps%25253A%25252F%25252Fsgp-api.buy.mi.com%25252Fbbs%25252Fapi%25252Fglobal%25252Fuser%25252Flogin-back%25253Ffollowup%25253Dhttps%2525253A%2525252F%2525252Fnew-ams.c.mi.com%2525252Fglobal%2525252F%252526sign%25253DM2UyYmIxZjc0MGQxODhkYjg3NWVlNDI4ZGQxNzk3ZmY3MThhYTVmNA%25252C%25252C%2526sid%253D18n_bbs_global%2526_locale%253Den_IN%2526checkSafePhone%253Dfalse&callback=https%3A%2F%2Fsgp-api.buy.mi.com%2Fbbs%2Fapi%2Fglobal%2Fuser%2Flogin-back%3Ffollowup%3Dhttps%253A%252F%252Fnew-ams.c.mi.com%252Fglobal%252F%26sign%3DM2UyYmIxZjc0MGQxODhkYjg3NWVlNDI4ZGQxNzk3ZmY3MThhYTVmNA%2C%2C&_sign=%2BnjnarFZlvmk2A9UJro3U%2BS0lbc%3D&serviceParam=%7B%22checkSafePhone%22%3Afalse%2C%22checkSafeAddress%22%3Afalse%2C%22lsrp_score%22%3A0.0%7D&showActiveX=false&theme=&needTheme=false&bizDeviceType="

STATE_URL = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
APPLY_URL = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"

FEED_TIME_MS = 1400.0                  # lead time so requests land at the reset
FEED_TIME_S = FEED_TIME_MS / 1000.0

TOKEN_FILE = "token.txt"               # persisted new_bbs_serviceToken
REVALIDATE_INTERVAL_S = 30.0           # token liveness probe cadence during the hold

BURST_WORKERS = 8                      # parallel request threads during the burst
BURST_JITTER_MS = (0, 100)             # per-request random stagger, milliseconds


# ──────────────────────────────────────────────────────────────────────────
#  Core logic
# ──────────────────────────────────────────────────────────────────────────
def generate_device_id():
    random_data = f"{random.random()}-{time.time()}"
    return hashlib.sha1(random_data.encode("utf-8")).hexdigest().upper()


def cookie_header(cookie_value, device_id):
    return {
        "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;"
                  f"versionName=5.4.11;deviceId={device_id};"
    }


def get_initial_beijing_time():
    client = ntplib.NTPClient()
    beijing_tz = pytz.timezone("Asia/Shanghai")
    step("syncing clock to beijing time…")
    for server in NTP_SERVERS:
        try:
            live(f"{MUTED}querying {server}…{RESET}")
            response = client.request(server, version=3)
            clear_live()
            ntp_time = datetime.fromtimestamp(response.tx_time, timezone.utc)
            beijing_time = ntp_time.astimezone(beijing_tz)
            stamp = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
            ms = beijing_time.strftime("%f")[:3]
            ok(f"beijing time  {AMBER}{BOLD}{stamp}{RESET}{DIM}.{ms}{RESET}"
               f"  {MUTED}via {server}{RESET}")
            return beijing_time
        except Exception as e:
            clear_live()
            warn(f"{server} unreachable {MUTED}({e}){RESET}")
    err("no NTP server reachable")
    return None


def get_synchronized_beijing_time(start_beijing_time, start_timestamp):
    elapsed = time.time() - start_timestamp
    return start_beijing_time + timedelta(seconds=elapsed)


def render_countdown(frame, remaining, target_time, frac):
    rs = max(0.0, remaining)
    hh = int(rs // 3600)
    mm = int((rs % 3600) // 60)
    ss = int(rs % 60)
    ms = int((rs - int(rs)) * 1000)
    sp = SPIN[frame % len(SPIN)]
    barw = 24
    fill = int(barw * min(1.0, max(0.0, frac)))
    bar = f"{AMBER}{'█' * fill}{LINE}{'░' * (barw - fill)}{RESET}"
    txt = (f"{AMBER}{sp}{RESET}  {TEXT}{BOLD}T- {hh:02d}:{mm:02d}:{ss:02d}"
           f"{DIM}.{ms:03d}{RESET}  {bar}  "
           f"{MUTED}→ {target_time.strftime('%H:%M:%S')} UTC+8{RESET}")
    live(txt)


def _next_revalidate_delay():
    """Spacing for the next liveness probe — ~30s with a little natural variance."""
    return REVALIDATE_INTERVAL_S + random.uniform(-5.0, 5.0)


def wait_until_target_time(session, cookie_value, device_id,
                           start_beijing_time, start_timestamp):
    next_day = start_beijing_time + timedelta(days=1)
    target_time = (next_day.replace(hour=0, minute=0, second=0, microsecond=0)
                   - timedelta(seconds=FEED_TIME_S))
    total = (target_time - start_beijing_time).total_seconds()

    info(f"phase shift locked at {AMBER}{FEED_TIME_MS:.0f} ms{RESET}")
    info(f"firing window {AMBER}{target_time.strftime('%Y-%m-%d %H:%M:%S')}{RESET} (UTC+8)")
    info(f"token revalidated every {AMBER}~{REVALIDATE_INTERVAL_S:.0f}s{RESET} while holding")
    print(f"  {MUTED}do not exit — holding for the reset…{RESET}\n")

    frame = 0
    last_render = 0.0
    last_revalidate = time.time()
    revalidate_delay = _next_revalidate_delay()
    while True:
        current_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        time_diff = (target_time - current_time).total_seconds()
        now = time.time()

        # Periodic liveness probe during the long hold (skip the final seconds so
        # we never add latency right before the burst).
        if time_diff > 5 and now - last_revalidate >= revalidate_delay:
            last_revalidate = now
            revalidate_delay = _next_revalidate_delay()
            if validate_token(session, cookie_value, device_id) == "expired":
                clear_live()
                warn("token expired during the wait — refresh it to stay armed")
                show_auth_panel()
                cookie_value = acquire_token(session, device_id)
                ok("token refreshed — resuming countdown")
                now = time.time()
                last_revalidate = now
            last_render = 0.0  # force an immediate redraw

        if now - last_render >= 0.08:
            frac = 1.0 - (time_diff / total) if total > 0 else 1.0
            render_countdown(frame, time_diff, target_time, frac)
            frame += 1
            last_render = now

        if time_diff > 1:
            time.sleep(min(0.08, time_diff - 1))
        elif current_time >= target_time:
            clear_live()
            fired = current_time.strftime("%H:%M:%S.%f")[:-3]
            ok(f"reset reached at {AMBER}{BOLD}{fired}{RESET} — firing")
            break
        else:
            time.sleep(0.0001)

    return cookie_value


def check_unlock_status(session, cookie_value, device_id):
    try:
        response = session.make_request("GET", STATE_URL,
                                        headers=cookie_header(cookie_value, device_id))
        if response is None:
            err("could not retrieve unlock status")
            return False

        response_data = json.loads(response.data.decode("utf-8"))
        response.release_conn()

        if response_data.get("code") == 100004:
            err("session token expired — grab a fresh cookie and retry")
            sys.exit(1)

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")
        deadline = data.get("deadline_format", "")

        if is_pass == 4:
            if button_state == 1:
                ok("account eligible — requests will be sent")
                return True
            if button_state == 2:
                warn(f"requests blocked until {AMBER}{deadline}{RESET} {MUTED}(MM/DD){RESET}")
                if confirm("continue anyway?"):
                    return True
                sys.exit(0)
            if button_state == 3:
                warn("account age is under 30 days")
                if confirm("continue anyway?"):
                    return True
                sys.exit(0)
            warn(f"unhandled button_state={button_state}")
            sys.exit(0)
        elif is_pass == 1:
            result("UNLOCK APPROVED", [
                f"{TEXT}This account is already approved.{RESET}",
                f"{MUTED}Window open until {AMBER}{deadline}{RESET}{MUTED}.{RESET}",
            ], MINT)
            print(f"  {MUTED}press enter to close…{RESET} ", end="")
            input()
            sys.exit(0)
        else:
            warn(f"unknown account state (is_pass={is_pass})")
            sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        err(f"status check failed: {e}")
        return False


class HTTP11Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=max(10, BURST_WORKERS),
            retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=15.0),
            headers={},
        )

    def make_request(self, method, url, headers=None, body=None):
        try:
            request_headers = {}
            if headers:
                request_headers.update(headers)
                request_headers["Content-Type"] = "application/json; charset=utf-8"

            if method == "POST":
                if body is None:
                    body = '{"is_retry":true}'.encode("utf-8")
                request_headers["Content-Length"] = str(len(body))
                request_headers["Accept-Encoding"] = "gzip, deflate, br"
                request_headers["User-Agent"] = "okhttp/4.12.0"
                request_headers["Connection"] = "keep-alive"

            return self.http.request(
                method, url, headers=request_headers, body=body,
                preload_content=False,
            )
        except Exception as e:
            err(f"network error: {e}")
            return None


def prompt_token():
    print(f"  {AMBER}›{RESET}  {TEXT}paste {BOLD}new_bbs_serviceToken{RESET}"
          f"{TEXT} and press enter{RESET}")
    print(f"  {MUTED}↳{RESET} ", end="")
    return input().strip()


def show_auth_panel():
    """Render the login instructions and the Xiaomi sign-in URL."""
    print()
    print(panel("AUTHENTICATE", [
        f"{TEXT}Open the Xiaomi login URL below in your browser and sign in.{RESET}",
        f"{TEXT}Then open DevTools → Application → Cookies and copy the{RESET}",
        f"{TEXT}value of {AMBER}{BOLD}new_bbs_serviceToken{RESET}{TEXT}.{RESET}",
    ]))
    print()
    print(f"  {MUTED}↗ open this url{RESET}")
    print(f"  {CYAN}{MI_ACCOUNT_URL}{RESET}")
    print()


def load_token():
    """Return the persisted token, or None if there isn't a usable one."""
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip()
        return value or None
    except OSError:
        return None


def save_token(value):
    """Persist the token so the next run can reuse it."""
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(value)
    except OSError as e:
        warn(f"could not save token to {TOKEN_FILE} {MUTED}({e}){RESET}")


def validate_token(session, cookie_value, device_id):
    """Lightweight liveness probe — a single state GET, never an unlock request.

    Returns 'valid', 'expired', or 'error' (transient/network)."""
    response = session.make_request("GET", STATE_URL,
                                    headers=cookie_header(cookie_value, device_id))
    if response is None:
        return "error"
    try:
        response_data = json.loads(response.data.decode("utf-8"))
        response.release_conn()
    except Exception:
        return "error"
    return "expired" if response_data.get("code") == 100004 else "valid"


def acquire_token(session, device_id):
    """Prompt for a token, persist it, and confirm it is live. Loops until valid."""
    while True:
        cookie_value = prompt_token()
        if not cookie_value:
            warn("no token entered — try again")
            continue
        save_token(cookie_value)
        state = validate_token(session, cookie_value, device_id)
        if state == "expired":
            err("that token is already expired — paste a fresh one")
            continue
        # 'valid', or 'error' (network blip) → accept and let later steps surface issues
        return cookie_value


def resolve_token(session, device_id):
    """Reuse a saved token when it's still live, otherwise prompt for a new one."""
    saved = load_token()
    if saved:
        info(f"found a saved token in {AMBER}{TOKEN_FILE}{RESET} — checking it…")
        state = validate_token(session, saved, device_id)
        if state == "valid":
            ok("saved token is live — reusing it")
            return saved
        if state == "expired":
            warn("saved token has expired — a fresh one is needed")
        else:
            warn("couldn't verify the saved token (network) — reusing it for now")
            return saved
    show_auth_panel()
    return acquire_token(session, device_id)


class BurstController:
    """Coordinates the worker pool: shared attempt counter, a stop signal, the
    first terminal outcome, and a lock so concurrent threads don't garble the
    single-line status output."""

    def __init__(self):
        self._lock = threading.Lock()
        self.out_lock = threading.Lock()
        self.stop = threading.Event()
        self._attempt = 0
        self.outcome = None  # set once; first writer wins

    def next_attempt(self):
        with self._lock:
            self._attempt += 1
            return self._attempt

    def set_outcome(self, kind, data=None):
        """Record the first terminal outcome and signal every worker to halt."""
        with self._lock:
            if self.outcome is None:
                self.outcome = (kind, data or {})
                self.stop.set()


def _burst_worker(session, headers, ctrl, start_beijing_time, start_timestamp, jitter):
    """One pool thread: fire POSTs in a loop until a terminal outcome is hit
    (by any worker) or the stop signal is raised. Non-terminal responses just
    update the live status line and the worker keeps going.

    ``jitter`` is a (min, max) millisecond range for the per-request stagger;
    (0, 0) means fire back-to-back with no delay (sequential mode)."""
    while not ctrl.stop.is_set():
        attempt = ctrl.next_attempt()
        request_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        response = session.make_request("POST", APPLY_URL, headers=headers)
        if response is None:
            with ctrl.out_lock:
                live(f"{CORAL}✗{RESET}  {MUTED}#{attempt:03d}{RESET} network error  "
                     f"{DIM}retrying…{RESET}")
            ctrl.stop.wait(random.uniform(*jitter) / 1000.0)
            continue

        response_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        latency = (response_time - request_time).total_seconds() * 1000

        try:
            response_data = response.data
            response.release_conn()
            jr = json.loads(response_data.decode("utf-8"))
            code = jr.get("code")
            data = jr.get("data", {})

            stamp = request_time.strftime("%H:%M:%S.%f")[:-3]
            tag = (f"{MUTED}#{attempt:03d}{RESET}  {TEXT}{stamp}{RESET}  "
                   f"{MUTED}{latency:6.1f}ms{RESET}")

            if code == 0:
                apply_result = data.get("apply_result")
                if apply_result == 1:
                    ctrl.set_outcome("verify", {"tag": tag, "approved": True})
                    return
                elif apply_result == 3:
                    ctrl.set_outcome("quota", {"data": data})
                    return
                elif apply_result == 4:
                    ctrl.set_outcome("blocked", {"data": data})
                    return
                else:
                    with ctrl.out_lock:
                        live(f"{CYAN}•{RESET}  {tag}  apply_result={apply_result}")
            elif code == 100001:
                # High-frequency rejection — update in place rather than flood.
                with ctrl.out_lock:
                    live(f"{CORAL}✗{RESET}  {tag}  rejected  {DIM}retrying…{RESET}")
            elif code == 100003:
                ctrl.set_outcome("verify", {"tag": tag, "approved": False})
                return
            elif code is not None:
                with ctrl.out_lock:
                    clear_live()
                    info(f"{tag}  unknown code {code}  {MUTED}{jr}{RESET}")
            else:
                with ctrl.out_lock:
                    clear_live()
                    err(f"{tag}  response missing status code  {MUTED}{jr}{RESET}")

        except json.JSONDecodeError:
            with ctrl.out_lock:
                clear_live()
                err(f"#{attempt:03d}  invalid JSON from server")
        except Exception as e:
            with ctrl.out_lock:
                clear_live()
                err(f"#{attempt:03d}  {e}")

        ctrl.stop.wait(random.uniform(*jitter) / 1000.0)


def _run_burst(session, headers, start_beijing_time, start_timestamp, worker_count, jitter):
    """Launch ``worker_count`` request threads and block until a terminal
    outcome is recorded. Returns the BurstController carrying that outcome.

    With ``worker_count=1`` and ``jitter=(0, 0)`` this is the original
    single-stream sequential burst."""
    ctrl = BurstController()
    workers = [
        threading.Thread(
            target=_burst_worker,
            args=(session, headers, ctrl, start_beijing_time, start_timestamp, jitter),
            daemon=True,
        )
        for _ in range(worker_count)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return ctrl


def fire_requests(session, cookie_value, device_id, start_beijing_time, start_timestamp,
                  pressure=False):
    headers = cookie_header(cookie_value, device_id)
    worker_count = BURST_WORKERS if pressure else 1
    jitter = BURST_JITTER_MS if pressure else (0, 0)
    if pressure:
        info(f"pressure mode — {AMBER}{worker_count}{RESET} parallel workers")
    else:
        info("sequential mode — single request stream "
             f"{MUTED}(use --pressure for parallel){RESET}")
    while True:
        ctrl = _run_burst(session, headers, start_beijing_time, start_timestamp,
                          worker_count, jitter)
        kind, payload = ctrl.outcome

        if kind == "verify":
            clear_live()
            tag = payload["tag"]
            if payload["approved"]:
                ok(f"{tag}  request {MINT}{BOLD}APPROVED{RESET} — verifying")
            else:
                warn(f"{tag}  possibly approved — verifying")
            # May sys.exit on a confirmed unlock; otherwise resume the burst.
            check_unlock_status(session, cookie_value, device_id)
            continue
        elif kind == "quota":
            clear_live()
            deadline = payload["data"].get("deadline_format", "—")
            result("QUOTA REACHED", [
                f"{TEXT}Today's unlock slots are gone.{RESET}",
                f"{MUTED}Retry at {AMBER}{deadline}{RESET}"
                f"{MUTED} (MM/DD), 00:00 Beijing.{RESET}",
            ], AMBER_HI)
            sys.exit(0)
        elif kind == "blocked":
            clear_live()
            deadline = payload["data"].get("deadline_format", "—")
            result("ACCOUNT BLOCKED", [
                f"{TEXT}This account is temporarily blocked.{RESET}",
                f"{MUTED}Blocked until {AMBER}{deadline}{RESET}"
                f"{MUTED} (MM/DD).{RESET}",
            ], CORAL)
            sys.exit(0)


def main(pressure=False):
    banner()

    # ── Step 1 · Authenticate ────────────────────────────────────────────
    section("01", "AUTHENTICATE")
    device_id = generate_device_id()
    session = HTTP11Session()
    cookie_value = resolve_token(session, device_id)

    # ── Step 2 · Account status ──────────────────────────────────────────
    section("02", "ACCOUNT STATUS")
    step("checking account eligibility…")
    if not check_unlock_status(session, cookie_value, device_id):
        err("status check failed — aborting")
        sys.exit(1)

    # ── Step 3 · Time sync ───────────────────────────────────────────────
    section("03", "TIME SYNC")
    start_beijing_time = get_initial_beijing_time()
    if start_beijing_time is None:
        err("unable to retrieve Beijing time — aborting")
        sys.exit(1)
    start_timestamp = time.time()

    # ── Step 4 · Countdown ───────────────────────────────────────────────
    section("04", "COUNTDOWN TO RESET")
    cookie_value = wait_until_target_time(session, cookie_value, device_id,
                                          start_beijing_time, start_timestamp)

    # ── Step 5 · Burst ───────────────────────────────────────────────────
    section("05", "REQUEST BURST")
    try:
        fire_requests(session, cookie_value, device_id,
                      start_beijing_time, start_timestamp, pressure=pressure)
    except SystemExit:
        raise
    except Exception as e:
        err(f"request loop error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="HyperOS bootloader unlock sniper.")
    parser.add_argument(
        "--pressure", action="store_true",
        help=f"fire the burst with {BURST_WORKERS} jittered parallel workers "
             "instead of a single sequential stream (default: off)")
    cli_args = parser.parse_args()

    try:
        main(pressure=cli_args.pressure)
    except KeyboardInterrupt:
        print(f"\n  {MUTED}interrupted — exiting{RESET}")
        sys.exit(130)
