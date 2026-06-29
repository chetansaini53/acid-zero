# Ethics, Authorized Use & Legal Notice

**Project:** Acid Zero
**Author / Maintainer:** Chetan Saini ([@chetansaini53](https://github.com/chetansaini53))
**Contact for security & abuse concerns:** chetansaini53@gmail.com
**Last updated:** 2026-06-27

---

## 1. What this project is

Acid Zero is an **offensive-security research and education toolkit** for the
802.11 (Wi-Fi) and Bluetooth Low Energy (BLE) radio environment. It includes capabilities
that are intentionally disruptive or deceptive when pointed at a real target:

- **Deauthentication / disassociation** frame transmission (denial of service against Wi-Fi clients).
- **Rogue access point + captive-portal credential-harvesting *simulation*** (a fake login
  page demonstrating phishing/evil-twin technique).
- **BLE advertising spam** (flooding nearby devices with crafted BLE advertisements).
- **WPA/WPA2 handshake capture** (passive collection of material usable for offline cracking).

These are the same techniques used by attackers. They are published here so that
**defenders, students, and researchers** can understand, detect, and defend against them.

## 2. The one rule

> **Only run these tools against networks, radios, and devices that you personally own,
> or for which you hold prior, explicit, written authorization from the owner.**

"I was just testing" / "it was open anyway" / "I didn't save the password" are **not**
authorization and are **not** legal defenses. There is no exception for curiosity,
neighbors, public/cafe Wi-Fi, conferences, airports, schools, or workplaces.

## 3. Authorized use — what "good" looks like

- ✅ Your own home lab, your own router, your own phones and BLE devices.
- ✅ A dedicated, **air-gapped or RF-isolated** test bench (Faraday bag/box where practical).
- ✅ A paid/contracted penetration test where you hold a **signed scope-of-work / rules of
  engagement / authorization-to-test letter** naming the targets and the time window.
- ✅ A CTF or training range where the organizers have authorized the activity.
- ✅ Defensive research: building and validating detection/IDS for these attacks.

## 4. Prohibited use — non-exhaustive

- 🚫 Any network, AP, client, or BLE device you do not own and are not authorized to test.
- 🚫 Harvesting, storing, or using **real third-party credentials** captured via the captive
  portal. The portal is a **simulation/demo** — never deploy it to collect real victims' data.
- 🚫 Denial of service (deauth/jam/BLE-spam) against production, public, emergency, medical,
  industrial, aviation, or any safety-relevant system. **Ever.**
- 🚫 Anything that violates local **radio/spectrum law** (intentional jamming is illegal in
  most countries even on your "own" airspace).
- 🚫 Stalking, harassment, surveillance of individuals, or any activity targeting a person.

## 5. Legal context (informational, not legal advice)

Depending on where you are, unauthorized use of these techniques may constitute crimes
including but not limited to:

| Region | Representative statutes |
|---|---|
| USA | Computer Fraud and Abuse Act (18 U.S.C. §1030); Wiretap Act (18 U.S.C. §2511); FCC rules on jamming (47 U.S.C. §333) |
| UK | Computer Misuse Act 1990; Wireless Telegraphy Act 2006; Investigatory Powers Act 2016 |
| EU | Directive 2013/40/EU + national implementations; GDPR (for captured personal data) |
| India | Information Technology Act 2000 §43, §66, §66C/D; Indian Telegraph Act / WPC spectrum rules; DPDP Act 2023 |
| UAE | Federal Decree-Law No. 34 of 2021 (Cybercrimes); TDRA spectrum regulations |

**Penalties can include fines and imprisonment.** Capturing handshakes or portal input may
also be **interception of communications** and a **data-protection** violation independent
of any "hacking" charge. This table is illustrative and not exhaustive — **you are
responsible for knowing and obeying the law in your jurisdiction.**

## 6. Responsible disclosure

If you use this tool and discover a vulnerability in a third party's product or network,
**do not exploit it.** Report it privately to the vendor/owner and allow reasonable time to
fix it. If you find a security issue **in this project**, email **chetansaini53@gmail.com** —
please do not open a public issue for vulnerabilities.

## 7. Data handling

- The captive-portal component MUST be treated as a **non-production demo.** Do not point it
  at real users. Do not retain captured input. Default builds should log nothing sensitive.
- Captured handshakes are cryptographic material tied to a real network — **delete them when
  your authorized test is done.** Do not redistribute capture files containing others' traffic.
- This repository's `.gitignore` excludes `*.pcap`, `*.cap`, `*.22000`, portal logs, and
  device config — **never commit captured data or secrets.**

## 8. No warranty, no liability

This software is provided **"AS IS", without warranty of any kind.** The author,
**Chetan Saini**, accepts **no liability** for any damage, loss, legal consequence, or harm
arising from use or misuse of this software. **You — the user — bear sole and full
responsibility for ensuring your use is lawful and authorized.** If you do not accept this,
do not download, build, or run the software.

## 9. Acceptance

Downloading, cloning, building, or running this software constitutes your acknowledgement
that you have read and agree to this document and the project [LICENSE](./LICENSE).
