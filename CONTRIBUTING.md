# Contributing to Acid Zero

Thanks for your interest in Acid Zero — a Flipper-Zero-class handheld for
**authorized** wireless-security research and education. Contributions are
welcome: new plugins, protocol decoders, hardware ports, docs, and bug fixes.

Before anything else, read **[ETHICS.md](ETHICS.md)** and the
[Code of Conduct](CODE_OF_CONDUCT.md). They are not boilerplate — they define
the line this project will not cross.

## The one rule that scopes everything

Acid Zero exists to **build, understand, and defend against** wireless-security
techniques — on hardware and networks you **own** or are **explicitly authorized
in writing** to test. Every offensive capability in this repo ships paired with
its own **detection & defense** lesson.

**Contributions are accepted only if they stay inside that scope.**

### ✅ Welcome
- New UI plugins (`apps/*.py`) or native plugins (`app.json` + binary) — see the
  contract in [`apps/hello-native/`](apps/hello-native/)
- Protocol decoders/encoders (Sub-GHz, IR, etc.) **with round-trip tests**
- Hardware ports / new co-processor support, wiring diagrams, docs
- Bug fixes, refactors, test coverage, accessibility/perf improvements
- Improvements to the in-app **Learn** (attack ↔ defense) content

### ❌ Not accepted (PRs will be closed)
- Destructive or denial-of-service payloads
- Features whose **only** purpose is unauthorized attack, mass-targeting, or
  evading detection for malicious use
- Removing or weakening the first-run consent gate, the per-attack Learn layer,
  or the authorized-use guardrails
- An offensive technique added **without** its paired detection/defense note
- Real credentials, private keys, or `settings.toml` with live secrets in commits

## Development setup

Full build/flash/deploy steps are in **[INSTALL.md](INSTALL.md)** (base OS,
display overlay, dependencies, service install, and the ESP32 / Pico
co-processor firmware).

## Code style

- Match the surrounding code — read a similar file before writing a new one.
- Python: terse, standard-library-first, no heavy deps; guard I/O with
  try/except; never `print` from library code (the launcher has a guard).
- Plugins follow the documented contract (`META`, `draw(d, ctx)`,
  `handle_touch(tx, ty, ctx)`; native = `app.json` + an executable that owns the
  framebuffer + touch and exits cleanly).
- Bind hardware by **name / chipset**, never by `wlanN` / `fb#` / `event#`
  (those reshuffle across boots).
- Keep commits focused; write a clear message explaining the *why*.

## Submitting a change

1. **Fork** the repo and create a branch: `git checkout -b feat/short-name`.
2. Make the change; add/adjust tests where it matters (protocol codecs, parsers,
   security boundaries).
3. Open a **pull request** with:
   - what it does and **why**,
   - a short **test plan** (how you verified it — real hardware or the codec
     unit tests),
   - for any offensive capability, the **detection/defense** it pairs with.
4. Be ready for review — challenges on architecture and scope are expected.

## Reporting bugs & requesting features

Use the **issue templates** (New issue → pick a template). For anything security
sensitive, **do not open a public issue** — email
**chetansaini53@gmail.com** privately (responsible disclosure; the author has
filed a CVE through proper channels and takes this seriously).

## License

By contributing, you agree that your contributions are licensed under the
repository's [MIT License](LICENSE), and that you have the right to submit them.
