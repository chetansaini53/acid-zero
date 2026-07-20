#!/usr/bin/env python3
"""
Acid Zero - WiFi adapter role assignment.

wlanN names reshuffle across boots, so roles are stored by CHIPSET (the kernel
driver name), never by wlanN - the same principle the rest of Acid Zero uses
for the display/touch/radio binding layer. Three roles:

  ssh      - the always-on uplink (SSH + internet). Boot-time only: assigning
             a chipset here raises its NetworkManager autoconnect priority so
             it wins on the NEXT boot; it never live-migrates the active
             session (moving a live default route out from under an SSH
             session is the one mistake that can strand the operator).
  monitor  - pwnagotchi + Acid Zero's own recon (Radar / Wardrive / Live
             Packets) - applied live by writing pwnagotchi's main.iface and
             restarting the pwnagotchi service (does not touch the SSH iface).
  badusb   - the Bad USB Pico-AP worker link - applied live, read by
             acid_badusb.py at CONNECT time. No restart needed.

Unassigned (or currently-unplugged) roles fall back through PRIORITY - the
high-power dual-band adapter (MT7612U, "the Alfa") is first, so pulling it to
save power and plugging it back in later just works with no code change.
monitor/badusb additionally avoid double-booking whatever chipset SSH is
using, UNLESS nothing else is present - Chetan's own rule: "ek hi external
bacha to wahi share hoga" (radar/wardrive/badusb are used one at a time
anyway, so sharing the SSH adapter as a last resort is fine, never blocking).

Config: /home/ella3/.acid_wifi_roles.json  {"ssh": "rtl8821au", ...}
"""
import glob
import json
import os
import subprocess

CONF = '/home/ella3/.acid_wifi_roles.json'
ROLES = ('ssh', 'monitor', 'badusb')
ROLE_LABEL = {'ssh': 'SSH + Internet', 'monitor': 'Pwnagotchi / Radar / Wardrive', 'badusb': 'Bad USB (Pico link)'}
ROLE_SHORT = {'ssh': 'SSH', 'monitor': 'MON', 'badusb': 'DUCK'}

# Chipset keys are KERNEL DRIVER names (readlink of .../device/driver), matching
# DRV2CHIP in acidzero.py - the MT7612U Alfa loads as "mt76x2u", the RTL8188EUS
# as "rtl8xxxu".
ONBOARD = 'brcmfmac'        # Pi's built-in 2.4GHz radio
# AUTO fill order PER ROLE (preferred first). Every role falls through the whole
# list, so a rig with FEWER adapters still works (public repo / testing):
#   ssh     -> RTL8188EUS (dedicated), then onboard, then ANY - SSH must connect
#              somehow, even off a single adapter; SSH may legitimately BE the uplink.
#   monitor -> Archer (RTL8821AU), then Alfa/others, then onboard (2.4G).
#   badusb  -> onboard (the Pico AP is 2.4G), then any NON-SSH adapter (on Pico
#              CONNECT it takes whatever is free, but NEVER the live-SSH iface).
PREF = {
    'ssh':     ['rtl8xxxu', 'brcmfmac', 'rtl8821au', 'mt76x2u', 'rtl8812au', 'r8188eu', '8188eu'],
    'monitor': ['mt76x2u', 'rtl8821au', 'rtl8812au', 'rtl8xxxu', 'r8188eu', '8188eu', 'brcmfmac'],
    'badusb':  ['brcmfmac', 'mt76x2u', 'rtl8812au', 'rtl8821au', 'rtl8xxxu', 'r8188eu', '8188eu'],
}
PRIORITY = ['rtl8xxxu', 'rtl8821au', 'mt76x2u', 'rtl8812au', 'r8188eu', '8188eu', 'brcmfmac']  # roles-screen cycle
CHIP_LABEL = {'mt76x2u': 'MT7612U (Alfa, dual)', 'rtl8812au': 'RTL8812AU (dual)',
              'rtl8821au': 'RTL8821AU / Archer', 'rtl8xxxu': 'RTL8188EUS (2.4G)', 'r8188eu': 'RTL8188EUS',
              '8188eu': 'RTL8188EUS', 'brcmfmac': 'Onboard (2.4G)'}

PWN_CONF = '/etc/pwnagotchi/config.toml'


def _driver(iface):
    try:
        return os.path.basename(os.readlink('/sys/class/net/%s/device/driver' % iface)).lower()
    except Exception:
        return ''


def present_adapters():
    """{chipset: iface} for every wlan* currently enumerated (skips *mon vifs)."""
    out = {}
    for path in sorted(glob.glob('/sys/class/net/wlan*')):
        iface = os.path.basename(path)
        if iface.endswith('mon'):
            continue
        drv = _driver(iface)
        if drv:
            out.setdefault(drv, iface)
    return out


def load_roles():
    try:
        with open(CONF) as f:
            d = json.load(f)
        return {r: d.get(r) for r in ROLES}
    except Exception:
        return {r: None for r in ROLES}


def save_roles(roles):
    try:
        with open(CONF, 'w') as f:
            json.dump({r: roles.get(r) for r in ROLES}, f)
        return True
    except Exception:
        return False


def active_uplink_iface():
    """The iface CURRENTLY carrying the default route - i.e. whatever SSH is
    actually riding right now, live, regardless of role assignment. Used so
    monitor/badusb never guess wrong and grab the live uplink out from under
    an open SSH session (a priority-order guess is not good enough here)."""
    try:
        out = subprocess.run(['ip', 'route', 'get', '1.1.1.1'], capture_output=True,
                             text=True, timeout=3).stdout.split()
        return out[out.index('dev') + 1] if 'dev' in out else None
    except Exception:
        return None


def resolve(role, roles=None, present=None):
    """-> (iface, chipset) for a role, live.

    ssh: assigned chipset if plugged in, else highest-PRIORITY present.

    monitor / badusb: the iface CURRENTLY carrying the default route (the live
    SSH session) is SACRED and is never handed out - using it would kill SSH.
    This overrides even an explicit assignment: assigning the SSH adapter to
    monitor/badusb only takes effect once SSH has actually moved off it (a
    reboot). Otherwise: assigned chipset (if safe), else highest-PRIORITY
    non-SSH chipset. Everything left over (one external only) is shared, since
    monitor/radar/wardrive/badusb run one at a time - but the LIVE uplink is
    never in that pool. Returns (None, None) if only the SSH adapter exists."""
    present = present if present is not None else present_adapters()
    roles = roles if roles is not None else load_roles()
    live = active_uplink_iface()
    a = roles.get(role)
    order = ([a] if a else []) + PREF.get(role, PRIORITY)
    if role == 'ssh':
        # SSH must connect SOMEHOW - it may legitimately BE the live uplink, so
        # the live iface is NOT excluded here. Preferred chipset first, then fall
        # through the whole list; if nothing matched, keep whatever carries SSH now.
        for chip in order:
            if chip and chip in present:
                return present[chip], chip
        for chip, iface in present.items():
            if iface == live:
                return iface, chip
        return None, None
    # monitor / badusb - the live-SSH iface is SACRED and is skipped in every
    # case (using it would kill SSH). Preferred chipset first, then fall through.
    for chip in order:
        if chip and chip in present and present[chip] != live:
            return present[chip], chip
    return None, None   # only the live SSH adapter is left - refuse (never kill SSH)


def role_of(chipset, roles=None):
    """Which role(s) a chipset is explicitly PINNED to (for the conflict note).
    '' if none."""
    roles = roles if roles is not None else load_roles()
    return '+'.join(ROLE_SHORT[r] for r in ROLES if roles.get(r) == chipset)


def serving(iface, present=None, roles=None):
    """Which role(s) this iface currently SERVES (pinned OR auto-resolved), for
    display - so the Alfa reads 'MON*' when monitor is on AUTO. '*' = auto (not
    pinned). '' if it serves nothing right now."""
    present = present if present is not None else present_adapters()
    roles = roles if roles is not None else load_roles()
    out = []
    for r in ROLES:
        ri, _ = resolve(r, roles, present)
        if ri == iface:
            out.append(ROLE_SHORT[r] + ('' if roles.get(r) else '*'))
    return '+'.join(out)


# ---------------- apply: monitor (live, safe - never touches SSH) ----------------
def apply_monitor(chipset):
    """Point pwnagotchi at `chipset` and restart it. REFUSES if that chipset is
    the live SSH adapter (would kill SSH) - move SSH off it first. Never touches
    the SSH uplink otherwise. Best-effort - always returns (ok, msg)."""
    present = present_adapters()
    iface = present.get(chipset)
    if not iface:
        return False, 'chipset not plugged in'
    if iface == active_uplink_iface():
        return False, 'that IS your live SSH (%s) - would drop SSH; move SSH first' % iface
    chip = chipset
    try:
        with open(PWN_CONF) as f:
            lines = f.readlines()
        out, hit = [], False
        for ln in lines:
            if ln.strip().startswith('main.iface'):
                out.append('main.iface = "%s"\n' % iface); hit = True
            else:
                out.append(ln)
        if not hit:
            out.append('main.iface = "%s"\n' % iface)
        with open(PWN_CONF, 'w') as f:
            f.writelines(out)
        subprocess.run(['systemctl', 'restart', 'pwnagotchi'], timeout=10, capture_output=True)
        return True, 'pwnagotchi -> %s (%s)' % (iface, CHIP_LABEL.get(chip, chip))
    except Exception as e:
        return False, str(e)[:40]


# ---------------- apply: ssh (boot-time priority only - never live-migrates) ----------------
def apply_ssh_priority(chipset):
    """Raise the SSH role's chipset's NM autoconnect priority so it wins on
    the NEXT boot. Does NOT touch the currently-active connection - a live
    default-route swap under an active SSH session is exactly the mistake
    this avoids. Best-effort - always returns (ok, msg)."""
    present = present_adapters()
    iface = present.get(chipset)
    if not iface:
        return False, 'chipset not present (will apply once plugged in + boots)'
    try:
        out = subprocess.run(['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show'],
                             capture_output=True, text=True, timeout=6).stdout
        name = next((ln.split(':', 1)[0] for ln in out.splitlines() if ln.endswith(':' + iface)), None)
        if not name:
            return False, 'no saved connection for %s yet' % iface
        subprocess.run(['nmcli', 'connection', 'modify', name, 'connection.autoconnect-priority', '100'],
                       timeout=6, capture_output=True)
        for other in present.values():
            if other == iface:
                continue
            onm = next((ln.split(':', 1)[0] for ln in out.splitlines() if ln.endswith(':' + other)), None)
            if onm:
                subprocess.run(['nmcli', 'connection', 'modify', onm, 'connection.autoconnect-priority', '0'],
                               timeout=6, capture_output=True)
        return True, 'takes effect on next boot'
    except Exception as e:
        return False, str(e)[:40]


# ---------------- SSH live START / STOP (operator control, on-device) ----------------
def _home_wifi_conn():
    """(name, iface) of the currently-active home-WiFi connection (the live SSH),
    or (name, None) for the highest-priority saved WiFi profile if none active."""
    try:
        out = subprocess.run(['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE', 'connection', 'show', '--active'],
                             capture_output=True, text=True, timeout=6).stdout
        for ln in out.splitlines():
            p = ln.split(':')
            if len(p) >= 3 and p[2] == '802-11-wireless':
                return p[0], p[1]
        out = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
                             capture_output=True, text=True, timeout=6).stdout
        for ln in out.splitlines():
            p = ln.split(':')
            if len(p) >= 2 and p[1] == '802-11-wireless':
                return p[0], None
    except Exception:
        pass
    return None, None


def apply_ssh_start():
    """Bring SSH/internet UP on the highest-priority present adapter, so SSH
    connects even if the preferred adapter is unplugged (falls through PREF).
    If SSH is already up, no-op. Best-effort - always returns (ok, msg)."""
    iface, chip = resolve('ssh')
    if not iface:
        return False, 'no WiFi adapter present'
    if iface == active_uplink_iface():
        return True, 'SSH already up on %s' % iface
    try:
        subprocess.run(['nmcli', 'dev', 'set', iface, 'managed', 'yes'], timeout=6, capture_output=True)
        r = subprocess.run(['nmcli', 'dev', 'connect', iface], timeout=30, capture_output=True, text=True)
        if r.returncode == 0:
            return True, 'SSH up on %s (%s)' % (iface, CHIP_LABEL.get(chip, chip))
        # fall back: bring the saved home-WiFi profile up (adapter may be bound to it)
        name, _ = _home_wifi_conn()
        if name:
            r2 = subprocess.run(['nmcli', 'connection', 'up', name], timeout=30, capture_output=True, text=True)
            if r2.returncode == 0:
                return True, 'SSH up (%s)' % name
        return False, 'connect failed: %s' % ((r.stderr or r.stdout).strip()[:38])
    except Exception as e:
        return False, str(e)[:40]


def apply_ssh_stop():
    """Disconnect the live SSH adapter (frees it for another use). Obviously
    ends the SSH session - meant to be tapped ON THE DEVICE. (ok, msg)."""
    iface = active_uplink_iface()
    name, cur = _home_wifi_conn()
    tgt = iface or cur
    if not tgt:
        return False, 'no active WiFi uplink to stop'
    try:
        subprocess.run(['nmcli', 'dev', 'disconnect', tgt], timeout=10, capture_output=True)
        return True, 'SSH stopped on %s (freed)' % tgt
    except Exception as e:
        return False, str(e)[:40]
