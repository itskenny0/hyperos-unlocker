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
#  Palette  ·  "midnight launch console"  -  amber on ink, electric accents
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

FEED_TIME_MS = 1400.0                  # default single lead time (ms before reset)
FEED_TIME_S = FEED_TIME_MS / 1000.0

# --precise bracket: fire staggered waves at these lead times (ms) so one wave
# lands on the exact reset regardless of network latency. Overridden by
# timeshift.txt (one value per line) when that file exists.
OFFSETS_MS = [1400.0, 900.0, 400.0, 100.0]
TIMESHIFT_FILE = "timeshift.txt"

TOKEN_FILE = "token.txt"               # one new_bbs_serviceToken per line
REVALIDATE_INTERVAL_S = 600.0          # token liveness probe cadence during the hold

BURST_WORKERS = 8                      # parallel request threads per lane (--pressure)
BURST_JITTER_MS = (0, 100)             # per-request random stagger, milliseconds
POOL_MAXSIZE = 64                      # urllib3 connections kept warm for the burst
MAX_LANE_THREADS = 32                  # confirm before launching more than this many threads


# ──────────────────────────────────────────────────────────────────────────
#  Time + identity helpers
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
    """Spacing for the next liveness probe - the interval with a little variance."""
    return REVALIDATE_INTERVAL_S + random.uniform(-5.0, 5.0)


# ──────────────────────────────────────────────────────────────────────────
#  HTTP session
# ──────────────────────────────────────────────────────────────────────────
class HTTP11Session:
    def __init__(self, maxsize=POOL_MAXSIZE):
        self.http = urllib3.PoolManager(
            maxsize=maxsize,
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


# ──────────────────────────────────────────────────────────────────────────
#  Token acquisition / persistence
# ──────────────────────────────────────────────────────────────────────────
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
        f"{MUTED}For multiple accounts, put one token per line in "
        f"{AMBER}{TOKEN_FILE}{RESET}{MUTED}.{RESET}",
    ]))
    print()
    print(f"  {MUTED}↗ open this url{RESET}")
    print(f"  {CYAN}{MI_ACCOUNT_URL}{RESET}")
    print()


def load_tokens():
    """Return every non-empty line of the token file (one token per line)."""
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def save_token(value):
    """Persist a single freshly-entered token so the next run can reuse it."""
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(value)
    except OSError as e:
        warn(f"could not save token to {TOKEN_FILE} {MUTED}({e}){RESET}")


def validate_token(session, cookie_value, device_id):
    """Lightweight liveness probe - a single state GET, never an unlock request.

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
            warn("no token entered - try again")
            continue
        save_token(cookie_value)
        state = validate_token(session, cookie_value, device_id)
        if state == "expired":
            err("that token is already expired - paste a fresh one")
            continue
        # 'valid', or 'error' (network blip) → accept and let later steps surface issues
        return cookie_value


def resolve_tokens(session):
    """Return the list of tokens to run. Uses token.txt if it has any, else
    prompts for one and saves it."""
    tokens = load_tokens()
    if tokens:
        plural = "s" if len(tokens) > 1 else ""
        ok(f"loaded {AMBER}{len(tokens)}{RESET} token{plural} from {AMBER}{TOKEN_FILE}{RESET}")
        return tokens
    show_auth_panel()
    return [acquire_token(session, generate_device_id())]


# ──────────────────────────────────────────────────────────────────────────
#  Account status
# ──────────────────────────────────────────────────────────────────────────
def check_unlock_status(session, cookie_value, device_id):
    """Interactive single-account status check (used for the lone-token path and
    to verify a win). May prompt and may sys.exit on a terminal state."""
    try:
        response = session.make_request("GET", STATE_URL,
                                        headers=cookie_header(cookie_value, device_id))
        if response is None:
            err("could not retrieve unlock status")
            return False

        response_data = json.loads(response.data.decode("utf-8"))
        response.release_conn()

        if response_data.get("code") == 100004:
            err("session token expired - grab a fresh cookie and retry")
            sys.exit(1)

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")
        deadline = data.get("deadline_format", "")

        if is_pass == 4:
            if button_state == 1:
                ok("account eligible - requests will be sent")
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


def survey_token(session, cookie_value, device_id):
    """Non-interactive status probe. Returns one of: eligible, approved, expired,
    blocked, young, unknown, error - plus a deadline string when relevant."""
    response = session.make_request("GET", STATE_URL,
                                    headers=cookie_header(cookie_value, device_id))
    if response is None:
        return {"state": "error", "deadline": ""}
    try:
        rd = json.loads(response.data.decode("utf-8"))
        response.release_conn()
    except Exception:
        return {"state": "error", "deadline": ""}

    if rd.get("code") == 100004:
        return {"state": "expired", "deadline": ""}
    data = rd.get("data", {})
    is_pass = data.get("is_pass")
    button_state = data.get("button_state")
    deadline = data.get("deadline_format", "")
    if is_pass == 1:
        return {"state": "approved", "deadline": deadline}
    if is_pass == 4:
        if button_state == 1:
            return {"state": "eligible", "deadline": ""}
        if button_state == 2:
            return {"state": "blocked", "deadline": deadline}
        if button_state == 3:
            return {"state": "young", "deadline": ""}
    return {"state": "unknown", "deadline": ""}


def survey(session, tokens):
    """Decide which accounts will fire. Returns a list of (token, device_id).

    One token → the interactive check (preserves the original UX). Multiple
    tokens → a non-interactive roster that keeps only eligible accounts."""
    if len(tokens) == 1:
        device_id = generate_device_id()
        step("checking account eligibility…")
        if not check_unlock_status(session, tokens[0], device_id):
            err("status check failed - aborting")
            sys.exit(1)
        return [(tokens[0], device_id)]

    step(f"surveying {len(tokens)} accounts…")
    eligible = []
    for i, tok in enumerate(tokens):
        device_id = generate_device_id()
        label = f"lane {AMBER}{_lane_letter(i)}{RESET}"
        tail = f"{MUTED}…{tok[-6:]}{RESET}"
        st = survey_token(session, tok, device_id)
        state, deadline = st["state"], st["deadline"]
        if state == "eligible":
            ok(f"{label}  eligible {tail}")
            eligible.append((tok, device_id))
        elif state == "approved":
            ok(f"{label}  already approved {tail} - skipping")
        elif state == "expired":
            warn(f"{label}  token expired {tail} - skipping")
        elif state == "blocked":
            warn(f"{label}  blocked until {AMBER}{deadline}{RESET} {tail} - skipping")
        elif state == "young":
            warn(f"{label}  account under 30 days {tail} - skipping")
        elif state == "error":
            warn(f"{label}  status probe failed {tail} - skipping")
        else:
            warn(f"{label}  unknown state {tail} - skipping")

    if not eligible:
        err("no eligible accounts - aborting")
        sys.exit(1)
    ok(f"{AMBER}{len(eligible)}{RESET} of {len(tokens)} accounts armed")
    return eligible


# ──────────────────────────────────────────────────────────────────────────
#  Countdown (the long hold before the reset)
# ──────────────────────────────────────────────────────────────────────────
def _revalidate(session, tokens_devs, warned):
    """Probe every token once. Single-token: re-acquire on expiry. Multi-token:
    drop expired accounts with a one-time warning. Returns the surviving list."""
    single = len(tokens_devs) == 1
    survivors = []
    for tok, dev in tokens_devs:
        state = validate_token(session, tok, dev)
        if state == "expired":
            if single:
                clear_live()
                warn("token expired during the wait - refresh it to stay armed")
                show_auth_panel()
                survivors.append((acquire_token(session, dev), dev))
                ok("token refreshed - resuming countdown")
            elif tok not in warned:
                clear_live()
                warn(f"a token expired during the hold {MUTED}(…{tok[-6:]}){RESET} - dropped")
                warned.add(tok)
            # multi-token expired tokens are simply not carried forward
        else:
            survivors.append((tok, dev))
    return survivors


def hold_until(target_time, session, tokens_devs, start_beijing_time, start_timestamp):
    """Render the live countdown to the first firing wave, revalidating tokens
    during the long hold. Returns the (possibly refreshed/pruned) token list."""
    total = (target_time - start_beijing_time).total_seconds()
    plural = "s" if len(tokens_devs) > 1 else ""
    info(f"first wave fires {AMBER}{target_time.strftime('%Y-%m-%d %H:%M:%S')}{RESET} (UTC+8)")
    info(f"token{plural} revalidated every {AMBER}~{REVALIDATE_INTERVAL_S:.0f}s{RESET} while holding")
    print(f"  {MUTED}do not exit - holding for the reset…{RESET}\n")

    frame = 0
    last_render = 0.0
    last_revalidate = time.time()
    revalidate_delay = _next_revalidate_delay()
    warned = set()
    while True:
        current_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        time_diff = (target_time - current_time).total_seconds()
        now = time.time()

        # Periodic liveness probe during the hold; never in the final seconds so
        # we don't add latency right before the burst.
        if time_diff > 5 and now - last_revalidate >= revalidate_delay:
            last_revalidate = now
            revalidate_delay = _next_revalidate_delay()
            tokens_devs = _revalidate(session, tokens_devs, warned)
            if not tokens_devs:
                return []
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
            ok(f"first wave at {AMBER}{BOLD}{fired}{RESET} - launching lanes")
            return tokens_devs
        else:
            time.sleep(0.0001)


# ──────────────────────────────────────────────────────────────────────────
#  The burst: lanes, workers, and coordination
# ──────────────────────────────────────────────────────────────────────────
def _lane_letter(i):
    return chr(65 + i) if i < 26 else f"#{i + 1}"


class BurstController:
    """Shared state for every worker thread: an attempt counter, a stop signal,
    the first terminal outcome (first writer wins), and an output lock so the
    threads don't garble the single-line status."""

    def __init__(self):
        self._lock = threading.Lock()
        self.out_lock = threading.Lock()
        self.stop = threading.Event()
        self._attempt = 0
        self.outcome = None

    def next_attempt(self):
        with self._lock:
            self._attempt += 1
            return self._attempt

    def set_outcome(self, kind, data=None):
        with self._lock:
            if self.outcome is None:
                self.outcome = (kind, data or {})
                self.stop.set()


def _wait_until(target_time, ctrl, start_beijing_time, start_timestamp):
    """Block until the synchronized Beijing clock reaches ``target_time`` or the
    stop signal is raised. Tightens to a busy-wait in the final 50 ms so a lane
    fires on its precise offset."""
    while not ctrl.stop.is_set():
        now_bt = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        diff = (target_time - now_bt).total_seconds()
        if diff <= 0:
            return
        if diff > 0.05:
            ctrl.stop.wait(min(0.05, diff - 0.02))
        else:
            time.sleep(0.0001)


def _burst_worker(label, token, device_id, headers, session, ctrl,
                  start_beijing_time, start_timestamp, jitter):
    """Fire POSTs in a loop until a terminal outcome is recorded (by any worker)
    or the stop signal is raised. Non-terminal responses just update the live
    status line."""
    while not ctrl.stop.is_set():
        attempt = ctrl.next_attempt()
        request_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        response = session.make_request("POST", APPLY_URL, headers=headers)
        if response is None:
            with ctrl.out_lock:
                live(f"{CORAL}✗{RESET}  {MUTED}{label} #{attempt:03d}{RESET} network error  "
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
            tag = (f"{AMBER}{label}{RESET}  {MUTED}#{attempt:03d}{RESET}  "
                   f"{TEXT}{stamp}{RESET}  {MUTED}{latency:6.1f}ms{RESET}")

            if code == 0:
                apply_result = data.get("apply_result")
                if apply_result == 1:
                    ctrl.set_outcome("verify", {"tag": tag, "approved": True,
                                                "label": label, "token": token,
                                                "device_id": device_id})
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
                # High-frequency rejection - update in place rather than flood.
                with ctrl.out_lock:
                    live(f"{CORAL}✗{RESET}  {tag}  rejected  {DIM}retrying…{RESET}")
            elif code == 100003:
                ctrl.set_outcome("verify", {"tag": tag, "approved": False,
                                            "label": label, "token": token,
                                            "device_id": device_id})
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
                err(f"{AMBER}{label}{RESET} #{attempt:03d}  invalid JSON from server")
        except Exception as e:
            with ctrl.out_lock:
                clear_live()
                err(f"{AMBER}{label}{RESET} #{attempt:03d}  {e}")

        ctrl.stop.wait(random.uniform(*jitter) / 1000.0)


def _stream(lane, headers, session, ctrl, start_beijing_time, start_timestamp, jitter):
    """One worker thread for a lane: wait for the lane's offset, then burst."""
    label, token, device_id, _offset_s, lane_target = lane
    _wait_until(lane_target, ctrl, start_beijing_time, start_timestamp)
    if ctrl.stop.is_set():
        return
    _burst_worker(label, token, device_id, headers, session, ctrl,
                  start_beijing_time, start_timestamp, jitter)


def _build_lanes(tokens_devs, offsets, target_midnight):
    """Cross product: every account fires the full wave of offsets. Each lane is
    (label, token, device_id, offset_seconds, lane_target)."""
    lanes = []
    for i, (token, device_id) in enumerate(tokens_devs):
        letter = _lane_letter(i)
        for offset_ms in offsets:
            offset_s = offset_ms / 1000.0
            lane_target = target_midnight - timedelta(seconds=offset_s)
            label = f"{letter}@{int(offset_ms)}"
            lanes.append((label, token, device_id, offset_s, lane_target))
    return lanes


def run_lanes(session, tokens_devs, offsets, target_midnight,
              start_beijing_time, start_timestamp, pressure):
    workers_per_lane = BURST_WORKERS if pressure else 1
    jitter = BURST_JITTER_MS if pressure else (0, 0)
    lanes = _build_lanes(tokens_devs, offsets, target_midnight)
    total_threads = len(lanes) * workers_per_lane

    info(f"{AMBER}{len(tokens_devs)}{RESET} account(s) × {AMBER}{len(offsets)}{RESET} "
         f"offset(s) = {AMBER}{len(lanes)}{RESET} lanes × {AMBER}{workers_per_lane}{RESET} "
         f"worker(s) → {AMBER}{BOLD}{total_threads}{RESET} threads")
    if total_threads > MAX_LANE_THREADS:
        warn(f"{total_threads} threads is a lot - the API may rate-limit or flag this")
        if not confirm("proceed anyway?"):
            sys.exit(0)
    for label, _t, _d, _o, lane_target in lanes:
        info(f"lane {AMBER}{label}{RESET} armed → fires "
             f"{MUTED}{lane_target.strftime('%H:%M:%S.%f')[:-3]} UTC+8{RESET}")
    print()

    while True:
        ctrl = BurstController()
        threads = []
        for lane in lanes:
            headers = cookie_header(lane[1], lane[2])
            for _ in range(workers_per_lane):
                threads.append(threading.Thread(
                    target=_stream,
                    args=(lane, headers, session, ctrl,
                          start_beijing_time, start_timestamp, jitter),
                    daemon=True,
                ))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        kind, payload = ctrl.outcome
        if kind == "verify":
            clear_live()
            if payload["approved"]:
                ok(f"{payload['tag']}  request {MINT}{BOLD}APPROVED{RESET} - verifying")
            else:
                warn(f"{payload['tag']}  possibly approved - verifying")
            # May sys.exit on a confirmed unlock; otherwise resume firing. After
            # midnight every lane_target is in the past, so lanes re-fire at once.
            check_unlock_status(session, payload["token"], payload["device_id"])
            continue
        elif kind == "quota":
            clear_live()
            deadline = payload["data"].get("deadline_format", "-")
            result("QUOTA REACHED", [
                f"{TEXT}Today's unlock slots are gone.{RESET}",
                f"{MUTED}Retry at {AMBER}{deadline}{RESET}"
                f"{MUTED} (MM/DD), 00:00 Beijing.{RESET}",
            ], AMBER_HI)
            sys.exit(0)
        elif kind == "blocked":
            clear_live()
            deadline = payload["data"].get("deadline_format", "-")
            result("ACCOUNT BLOCKED", [
                f"{TEXT}This account is temporarily blocked.{RESET}",
                f"{MUTED}Blocked until {AMBER}{deadline}{RESET}"
                f"{MUTED} (MM/DD).{RESET}",
            ], CORAL)
            sys.exit(0)


# ──────────────────────────────────────────────────────────────────────────
#  Offsets + orchestration
# ──────────────────────────────────────────────────────────────────────────
def load_offsets(precise):
    """Single default offset normally; the staggered bracket when --precise.
    timeshift.txt (one value per line) overrides the built-in bracket."""
    if not precise:
        return [FEED_TIME_MS]
    try:
        with open(TIMESHIFT_FILE, "r", encoding="utf-8") as f:
            vals = [float(ln.strip()) for ln in f if ln.strip()]
        if vals:
            info(f"using {AMBER}{len(vals)}{RESET} offset(s) from {AMBER}{TIMESHIFT_FILE}{RESET}")
            return vals
    except (OSError, ValueError):
        pass
    return list(OFFSETS_MS)


def main(precise=False, pressure=False):
    banner()

    # ── Step 1 · Authenticate ────────────────────────────────────────────
    section("01", "AUTHENTICATE")
    session = HTTP11Session()
    tokens = resolve_tokens(session)

    # ── Step 2 · Account status ──────────────────────────────────────────
    section("02", "ACCOUNT STATUS")
    tokens_devs = survey(session, tokens)

    # ── Step 3 · Time sync ───────────────────────────────────────────────
    section("03", "TIME SYNC")
    start_beijing_time = get_initial_beijing_time()
    if start_beijing_time is None:
        err("unable to retrieve Beijing time - aborting")
        sys.exit(1)
    start_timestamp = time.time()

    # ── Step 4 · Countdown ───────────────────────────────────────────────
    section("04", "COUNTDOWN TO RESET")
    offsets = load_offsets(precise)
    target_midnight = (start_beijing_time + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    earliest_target = target_midnight - timedelta(seconds=max(offsets) / 1000.0)
    tokens_devs = hold_until(earliest_target, session, tokens_devs,
                             start_beijing_time, start_timestamp)
    if not tokens_devs:
        err("no live tokens left - aborting")
        sys.exit(1)

    # ── Step 5 · Burst ───────────────────────────────────────────────────
    section("05", "REQUEST BURST" + (f" {MUTED}·{RESET} {AMBER}PRECISE{RESET}" if precise else ""))
    try:
        run_lanes(session, tokens_devs, offsets, target_midnight,
                  start_beijing_time, start_timestamp, pressure)
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
        "--precise", action="store_true",
        help="fire staggered waves at multiple lead-time offsets "
             f"({'/'.join(str(int(o)) for o in OFFSETS_MS)} ms, or timeshift.txt) "
             "so one wave lands on the exact reset (default: single offset)")
    parser.add_argument(
        "--pressure", action="store_true",
        help=f"run {BURST_WORKERS} jittered parallel workers per lane "
             "instead of one request stream (default: off)")
    cli_args = parser.parse_args()

    try:
        main(precise=cli_args.precise, pressure=cli_args.pressure)
    except KeyboardInterrupt:
        print(f"\n  {MUTED}interrupted - exiting{RESET}")
        sys.exit(130)
