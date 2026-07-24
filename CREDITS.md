# CREDITS, THIRD-PARTY ATTRIBUTION & SOURCE OFFER
## Acid Zero OS — Release `v1.0.0`

> **Values are pre-filled** for the first release: image `v1.0.0`, pwnagotchi
> `v2.9.5.4`, bettercap `v2.41.5`, Debian 13 (trixie), nexmon firmware `7.45.206`
> (BCM4345/6), source hosted on the GitHub release, contact
> `chetansaini53@gmail.com`. **Two things to confirm before you publish:**
> (1) the image's **login user** — the build doc uses your card's `ella3`; for a
> public image consider a neutral default (e.g. `pi`) so you don't ship your private
> persona name; (2) optionally mirror the source at `chetansaini.com` too (not
> required — the GitHub release already satisfies GPL §6(d)). Bump the version
> strings on every future release so the source pointer keeps matching the image.

Acid Zero OS is a customized SD-card image for the Raspberry Pi 3B+. It is an
**aggregate** of independently licensed programs distributed together on one
storage medium (GPLv3 §5). It is **not** a single combined work: our own code is
licensed MIT and each bundled component retains its own upstream license.

> IMPORTANT: This image is built on the **jayofelony pwnagotchi** base, which is
> licensed **GPL-3.0**. Because we redistribute GPL binaries inside this image, the
> GPL-3.0 source-availability obligations in Section 4 below apply to the whole
> GPL/LGPL contents of the image — see "Written Offer for Corresponding Source".

---

## 1. Primary credits

This project would not exist without the following. We gratefully credit:

- **pwnagotchi** — the Wi-Fi-handshake capture agent and UI framework this image is
  built on. Originally created by **@evilsocket** and the pwnagotchi dev team;
  the base image here is the actively-maintained fork by **jayofelony**.
  License: **GPL-3.0-only**.
  - Upstream (fork / base image): https://github.com/jayofelony/pwnagotchi
  - Original project: https://github.com/evilsocket/pwnagotchi
- **bettercap** — the network attack/monitoring framework pwnagotchi drives to
  perform capture. By the bettercap authors. License: **GPL-3.0-only**.
  - Upstream: https://github.com/bettercap/bettercap

Acid Zero is an independent hobby project. It is **not** affiliated with,
sponsored by, or endorsed by the pwnagotchi project, @evilsocket, jayofelony, the
bettercap project, Raspberry Pi Ltd, or Debian. We credit these projects — we do
not brand ourselves as them.

---

## 2. Our own code

- **Acid Zero additions** (launcher, UI, plugins, helper scripts, build scripts) —
  © 2026 Chetan Saini. `SPDX-License-Identifier: MIT`.
  - Source: https://github.com/chetansaini53/acid-zero

Acid Zero runs as its **own separate process** (the `acidzero.service` systemd
unit, under the system `python3`) and talks to pwnagotchi/bettercap only at
**arm's length** over their local HTTP APIs (`http://127.0.0.1:8081/api/session`
for bettercap, `http://127.0.0.1:8080/ui` for the pwnagotchi web UI). It does
**not** import pwnagotchi internals and is **not** a pwnagotchi plugin. It is
therefore *mere aggregation* under GPLv3 §5 and remains MIT in the shipped image.

> NOTE ON PLUGINS / IN-PROCESS CODE: were any Acid Zero component ever run **inside**
> the pwnagotchi process (a Python plugin importing pwnagotchi internals), that
> component would, as distributed, be a derivative work of GPL-3.0 pwnagotchi and its
> corresponding source would have to be offered under GPL-3.0 — even if the pristine
> file also carries an MIT header. Acid Zero deliberately stays arm's-length to avoid
> this. Re-verify (`grep -rn "import pwnagotchi"`) before any future release.

---

## 3. Redistributed component inventory

| Component | SPDX license | Upstream |
|---|---|---|
| pwnagotchi (jayofelony fork) | GPL-3.0-only | https://github.com/jayofelony/pwnagotchi |
| bettercap | GPL-3.0-only | https://github.com/bettercap/bettercap |
| Linux kernel (RPi, patched) | GPL-2.0-only | https://github.com/raspberrypi/linux |
| Broadcom/Cypress Wi-Fi firmware — BCM4345/6, nexmon-patched `7.45.206` (nexmon `2.2.2-552`), for monitor mode | LicenseRef-Broadcom-Cypress (binary blob) + nexmon terms | https://github.com/seemoo-lab/nexmon |
| RPi bootloader / GPU firmware (`start*.elf`, `fixup*.dat`, `bootcode.bin`) | LicenseRef-Broadcom-RPi (binary, unmodified, RPi-hardware only) | https://github.com/raspberrypi/firmware |
| aircrack-ng | GPL-2.0-or-later WITH OpenSSL-exception | https://github.com/aircrack-ng/aircrack-ng |
| hostapd / wpa_supplicant | BSD-3-Clause | https://w1.fi/hostapd/ |
| dnsmasq | GPL-2.0-only OR GPL-3.0-only | https://thekelleys.org.uk/dnsmasq/ |
| BlueZ tools/daemon | GPL-2.0-or-later | https://github.com/bluez/bluez |
| libbluetooth (BlueZ lib) | LGPL-2.1-or-later | https://github.com/bluez/bluez |
| hcxtools | MIT | https://github.com/ZerBea/hcxtools |
| CircuitPython + adafruit_hid (co-processor firmware bundled in repo) | MIT | see [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) |
| Base OS: Raspberry Pi OS (Debian port) | Aggregate — each package under its own license (GPL/LGPL/BSD/MIT/Apache) | https://www.raspberrypi.com/software/ · https://www.debian.org/ |

Per-package license and copyright text is preserved **on the image** at
`/usr/share/doc/<package>/copyright`. The full GPL text ships at
`/usr/share/common-licenses/GPL-3` and `/usr/share/common-licenses/GPL-2`.

There is **no license conflict** in this image: the GPL-2.0-only kernel and the
GPL-3.0 tools are separate processes (aggregation), never linked together, so the
GPL-2/GPL-3 incompatibility never arises.

---

## 4. Written Offer for Corresponding Source (GPL-3.0 §6 / GPL-2.0 §3)

For every GPL- and LGPL-licensed binary redistributed in this image, the complete
corresponding source — the exact versions that built the shipped binaries, plus
the scripts used to build and install them — is available:

1. **Our own build scripts and any GPL components we modified:**
   https://github.com/chetansaini53/acid-zero (tag `v1.0.0`), hosted in
   the same place as the released image (§6(d)).
2. **Unmodified upstream GPL/LGPL binaries** (pwnagotchi, bettercap, and each stock
   Debian/RPi-OS package): the exact source is mirrored at
   `https://github.com/chetansaini53/acid-zero/releases/tag/v1.0.0`, pinned to:
   - pwnagotchi `v2.9.5.4`, bettercap `v2.41.5`
   - Debian packages: exact versions at https://snapshot.debian.org/ and mirrored
     tarballs at `https://github.com/chetansaini53/acid-zero/releases/tag/v1.0.0` (we do not rely on generic apt archives,
     which drop superseded versions).
3. **Modified GPL components in the base** (the patched RPi Linux kernel; the
   nexmon-modified Wi-Fi firmware where GPL/mixed): the corresponding source is the
   **jayofelony base image** build we ship on top of — see
   https://github.com/jayofelony/pwnagotchi release `v2.9.5.4` (which
   carries the kernel/firmware/nexmon build), mirrored at `https://github.com/chetansaini53/acid-zero/releases/tag/v1.0.0`.
   Pristine-pristine upstream pointers are NOT used for these, because they would not
   match the shipped (patched) binaries.

**Written offer:** For at least three (3) years from the date you received this
image, and for as long as we distribute it, we will provide — to any third party,
on request — the complete machine-readable corresponding source for any GPL/LGPL
component in this image, on a physical medium at no more than our cost of
distribution, or free of charge by network download. Contact: `chetansaini53@gmail.com`.

Source is kept as easy to obtain as the image itself. We host the exact matching
tarballs ourselves so availability does not depend on any upstream tag remaining
in place.

The **LGPL-2.1 libbluetooth** obligation (permit relinking/replacement, provide
library source) is satisfied by the same source availability above.

---

## 5. License & warranty preservation

All upstream LICENSE files, per-file copyright headers, and warranty disclaimers
are preserved intact on the image. Each recipient receives a copy of the GNU GPL
(shipped on-card, not merely linked). Redistributors of this image must keep these
notices intact; the data-scrub step in our build process (see
[BUILD_CLEAN_IMAGE.md](BUILD_CLEAN_IMAGE.md)) removes only private keys, captures,
and history — never any license or notice file.

**NO WARRANTY.** This image is distributed WITHOUT ANY WARRANTY, without even the
implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE, to the
extent permitted by applicable law (GPL-3.0 §§15–16). It is provided for
**authorized, lawful, defensive and educational security research on hardware and
networks you own or are explicitly permitted to test only** (see [ETHICS.md](ETHICS.md)).

---

## 6. Trademark & no-endorsement

- **Raspberry Pi is a trademark of Raspberry Pi Ltd.** Acid Zero OS merely *runs
  on* / is *based on* Raspberry Pi OS. "Raspberry Pi" is not part of our product
  name, and this image is **not** Raspberry Pi OS and is not endorsed by, sponsored
  by, or affiliated with Raspberry Pi Ltd. The Broadcom/RPi bootloader firmware is
  redistributed in binary, unmodified form for use on Raspberry Pi hardware only.
- **Debian is a trademark of Software in the Public Interest, Inc.**
- **"pwnagotchi", "bettercap"** and their logos belong to their respective
  authors. Used here referentially to credit the upstream software; no endorsement
  of Acid Zero by those projects is implied.

Acid Zero OS is an independent project by Chetan Saini. Any names above are used
for attribution and compatibility identification only.
