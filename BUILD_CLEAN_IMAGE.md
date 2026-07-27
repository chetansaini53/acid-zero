# Acid Zero OS — Clean-Image Build & Data-Scrub Checklist

> ## ⚠️ WORK ON A COPY — NEVER YOUR DAILY DRIVER
> This scrub is **destructive** (it wipes SSH keys, Wi-Fi creds, device identity,
> history) and the rename changes the login user. **Do NOT run any of it on your
> working device.** First **clone your working card to a spare**, boot the *spare*,
> and do everything here on the spare. Your production card stays untouched.
>
> **Clone first (on your PC — Pi powered off, working card in a reader):**
> ```
> # Linux/WSL — sdX is the CARD (whole disk). Windows: use Win32DiskImager to Read.
> sudo dd if=/dev/sdX of=acidzero-master.img bs=4M status=progress
> ```
> Flash `acidzero-master.img` to a **SPARE** card (Raspberry Pi Imager → Use custom),
> boot the SPARE in the Pi, set the working card aside, and do every step below on the
> SPARE only.

Turn the SPARE (a clone of your working card) into a SAFE, redistributable image.
Run every step below on the SPARE (over SSH or a keyboard) BEFORE you power it off
and image it. Order matters: scrub first, set defaults, then image, shrink, compress.

> **RULE:** This pass removes PRIVATE artifacts only. NEVER delete any LICENSE /
> copyright / `/usr/share/doc/*/copyright` / `/usr/share/common-licenses/*` file —
> those are legally required to ship (see [CREDITS.md](CREDITS.md) §5).

Work as root: `sudo -i`

---

## 1. Stop services that hold secrets or write logs

```
systemctl stop pwnagotchi bettercap 2>/dev/null
systemctl stop acidzero.service 2>/dev/null
systemctl stop wpa_supplicant 2>/dev/null
```

## 2. Remove pwnagotchi / pwngrid identity keys

These are your device's cryptographic identity — regenerated on first boot by
pwnagotchi if absent.

```
rm -f /etc/pwnagotchi/*.pem
rm -f /root/.api-enrollment.json /root/.api-report.json
rm -f /root/.pwngrid-peer 2>/dev/null
rm -f /etc/pwnagotchi/id.pem /etc/pwnagotchi/id.pub.pem 2>/dev/null
```

## 3. Remove captured handshakes, wardrive data, and pcaps

```
rm -f /root/handshakes/* /home/*/handshakes/* 2>/dev/null
rm -f /root/*.pcap /root/*.pcapng 2>/dev/null
find / -xdev \( -name '*.pcap' -o -name '*.pcapng' \) 2>/dev/null   # review, then delete
rm -f /root/*.gps.json /root/*.geo.json 2>/dev/null                  # wardrive/GPS
find / -xdev -iname '*wardrive*.csv' -delete 2>/dev/null
find / -xdev \( -iname '*.22000' -o -iname '*.hccapx' \) -delete 2>/dev/null  # cracked hashes
rm -rf /home/*/acid_wardrive/* /home/*/acid_ir_saved/* 2>/dev/null   # Acid Zero captures
```

## 4. Wipe all Wi-Fi credentials

```
# wpa_supplicant (all variants)
rm -f /etc/wpa_supplicant/wpa_supplicant*.conf

# NetworkManager saved connections (PSKs live here in plaintext)
rm -f /etc/NetworkManager/system-connections/*
rm -f /var/lib/NetworkManager/*.lease /var/lib/NetworkManager/seen-bssids 2>/dev/null

# dhcpcd / hostapd leftovers
rm -f /var/lib/dhcpcd/*.lease /var/lib/dhcp/*.leases 2>/dev/null
```

## 5. Remove Acid Zero private artifacts & tokens

```
rm -f /home/*/.acid_ap.json /root/.acid_ap.json           # shared Pico AP creds
rm -f /home/*/.acid_wifi_roles.json 2>/dev/null
rm -f /root/.git-credentials /home/*/.git-credentials 2>/dev/null
rm -rf /root/.config/gh /home/*/.config/gh 2>/dev/null     # gh auth
find / -xdev \( -iname '.env' -o -iname '*token*' -o -iname '*secret*' \) 2>/dev/null  # review each
```

## 6. SSH: remove host keys (regenerate on first boot) and authorized_keys

```
rm -f /etc/ssh/ssh_host_*                                  # host keys regenerated on first boot (Step 8)
rm -f /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys
rm -f /root/.ssh/known_hosts /home/*/.ssh/known_hosts
rm -f /root/.ssh/id_* /home/*/.ssh/id_* 2>/dev/null
```

## 7. Shell history, logs, machine-id, caches

```
rm -f /root/.bash_history /home/*/.bash_history
rm -f /root/.python_history /home/*/.python_history 2>/dev/null

journalctl --rotate; journalctl --vacuum-time=1s 2>/dev/null
find /var/log -type f -exec truncate -s 0 {} \;
: > /var/log/wtmp 2>/dev/null; : > /var/log/btmp 2>/dev/null

# machine-id regenerates on boot — keeps each flashed card unique
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id && ln -s /etc/machine-id /var/lib/dbus/machine-id

apt-get clean
rm -rf /root/.cache/* /home/*/.cache/* /tmp/* /var/tmp/* 2>/dev/null
```

## 8. Set safe DEFAULTS + first-boot SSH-key regeneration

```
# Default hostname
echo "acidzero" > /etc/hostname
sed -i 's/127.0.1.1.*/127.0.1.1\tacidzero/' /etc/hosts

# Default login — set a documented password (state it in the release notes) and
# force a change at first login. Your card's login user is `ella3`; for a PUBLIC
# image consider renaming to a neutral default (e.g. `pi`) so you don't ship your
# private persona name — safe now that the launcher runs under /usr/bin/python3
# (no venv-in-home dependency), but keep pwnagotchi's own runtime paths intact.
echo 'ella3:acidzero' | chpasswd
passwd --expire ella3
```

Create a first-boot oneshot to regenerate the SSH host keys deleted in Step 6:

```
cat > /etc/systemd/system/regen-ssh-hostkeys.service <<'EOF'
[Unit]
Description=Regenerate SSH host keys on first boot
Before=ssh.service
ConditionPathExistsGlob=!/etc/ssh/ssh_host_*_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
ExecStartPost=/bin/systemctl disable regen-ssh-hostkeys.service
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl enable regen-ssh-hostkeys.service
```

(The `ConditionPathExistsGlob=!...` guard self-disables the unit once keys exist, so
it fires only on the first boot of a freshly-flashed card.)

## 9. Final review before imaging

```
# Sanity: confirm nothing private remains (each should be empty/gone)
ls /etc/ssh/ssh_host_* 2>/dev/null
ls /etc/NetworkManager/system-connections/ 2>/dev/null
cat /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null
ls /etc/pwnagotchi/*.pem 2>/dev/null
find / -xdev -name '*.pcap*' 2>/dev/null

# Confirm license files are STILL present (must NOT be removed)
ls /usr/share/common-licenses/GPL-3
ls /usr/share/doc/bettercap/copyright 2>/dev/null

# Zero free space so the compressed image is small and old data isn't recoverable
dd if=/dev/zero of=/zero.fill bs=4M 2>/dev/null; sync; rm -f /zero.fill
history -c
poweroff
```

## 10. Image the card (on your host)

Insert the card into a reader. Identify the whole-disk device (Linux/WSL: `lsblk`;
Windows: Win32DiskImager). Read the full card to a file:

```
# Linux/WSL — replace sdX with the CARD device (whole disk, not a partition)
sudo dd if=/dev/sdX of=acidzero-v1.0.0.img bs=4M status=progress conv=fsync
```

## 11. Shrink with PiShrink, then compress

PiShrink trims the root partition to used-size and auto-expands it on first boot;
xz compresses hard for the release upload.

```
# One-off: get PiShrink
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh

# Shrink + xz-compress in one pass (-Z uses xz; -a auto-expands rootfs on first boot)
sudo ./pishrink.sh -Z -a acidzero-v1.0.0.img
# Output: acidzero-v1.0.0.img.xz  (target: 1.5-1.8 GB, like the pwnagotchi base)

# Checksum for the release page
sha256sum acidzero-v1.0.0.img.xz > acidzero-v1.0.0.img.xz.sha256
```

## 12. Attach to a GitHub Release

```
# Tag the source repo at the EXACT version that produced this image (GPL §6 match)
git tag v1.0.0 && git push origin v1.0.0

gh release create v1.0.0 \
  acidzero-v1.0.0.img.xz \
  acidzero-v1.0.0.img.xz.sha256 \
  CREDITS.md \
  --title "Acid Zero OS v1.0.0" \
  --notes "Flashable Pi 3B+ image. Verify with the .sha256. Source & GPL offer: see CREDITS.md. Default login documented in the notes; SSH host keys regenerate on first boot."
```

Because the buildable source lives in the **same GitHub repo/release** as the
image, this satisfies GPL-3.0 §6(d) — as long as the pinned source (and the
mirrored exact-version upstream tarballs referenced in [CREDITS.md](CREDITS.md) §4)
stays available for as long as you distribute the image.

---

## Quick reference — must-remove vs must-keep

| REMOVE (private) | KEEP (legally required) |
|---|---|
| `/etc/ssh/ssh_host_*` | All `LICENSE` / `COPYING` files |
| `~/.ssh/authorized_keys`, `id_*`, `known_hosts` | `/usr/share/common-licenses/GPL-2`, `GPL-3` |
| `wpa_supplicant*.conf`, NM `system-connections/*` | `/usr/share/doc/<pkg>/copyright` |
| `/etc/pwnagotchi/*.pem`, `/root/.api-*`, pwngrid keys | Per-file copyright headers |
| handshakes, `*.pcap*`, wardrive CSV, `*.22000`/`*.hccapx` | `CREDITS.md`, `THIRD-PARTY-LICENSES.md`, disclaimers |
| `~/.acid_ap.json` (Pico AP creds), tokens, `.env`, `gh` auth | |
| bash/python history, logs, `machine-id` | |
