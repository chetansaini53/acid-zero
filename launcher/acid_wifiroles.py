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

# highest power / best range first - the default fill order for an unassigned
# (or currently-unplugged) role. Keys are KERNEL DRIVER names (readlink of
# .../device/driver), matching DRV2CHIP in acidzero.py - e.g. the MT7612U-based
# Alfa adapter loads as driver "mt76x2u", not "mt7612u".
PRIORITY = ['mt76x2u', 'rtl8812au', 'rtl8821au', 'rtl8xxxu', 'r8188eu', '8188eu', 'brcmfmac']
CHIP_LABEL = {'mt76x2u': 'MT7612U (Alfa, dual-band)', 'rtl8812au': 'RTL8812AU (dual-band)',
              'rtl8821au': 'RTL8821AU', 'rtl8xxxu': 'RTL8188EUS', 'r8188eu': 'RTL8188EUS',
              '8188eu': 'RTL8188EUS', 'brcmfmac': 'Onboard'}

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
    if role == 'ssh':
        a = roles.get('ssh')
        if a and a in present:
            return present[a], a
        for chip in PRIORITY:
            if chip in present:
                return present[chip], chip
        return None, None
    live_ssh = active_uplink_iface()
    a = roles.get(role)
    if a and a in present and present[a] != live_ssh:
        return present[a], a
    for chip in PRIORITY:
        if chip in present and present[chip] != live_ssh:
            return present[chip], chip
    return None, None   # only the live SSH adapter is left - refuse (never kill SSH)


def role_of(chipset, roles=None):
    """Which role(s) a chipset is ASSIGNED to (for display). '' if none."""
    roles = roles if roles is not None else load_roles()
    return '+'.join(ROLE_SHORT[r] for r in ROLES if roles.get(r) == chipset)


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
