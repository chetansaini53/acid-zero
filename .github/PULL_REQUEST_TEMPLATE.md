<!--
  Thanks for contributing to Acid Zero! Please read CONTRIBUTING.md and ETHICS.md
  first. Acid Zero is for AUTHORIZED / educational / defensive use only.
-->

## Summary
<!-- What does this change do, and WHY? -->


## Type of change
- [ ] Bug fix
- [ ] New feature / plugin (UI `.py` or native `app.json` + binary)
- [ ] Protocol decoder / encoder (Sub-GHz / IR / …)
- [ ] Hardware port / co-processor firmware
- [ ] Docs / diagrams
- [ ] Refactor / tests / perf / accessibility

## Test plan
<!-- How did you verify this? Be concrete. -->
- [ ] Tested on real hardware (which board / co-processor):
- [ ] Codec / parser unit tests pass (e.g. `apps/test_*_proto.py`)
- [ ] Manual UI check on the device


## Detection & defense pairing
<!-- REQUIRED for any offensive capability: how is the technique detected and
     defended against? This is what keeps Acid Zero educational, not just a tool. -->


## Scope & safety checklist
- [ ] Stays within **authorized / own-lab / educational** use ([ETHICS.md](../ETHICS.md))
- [ ] Does **not** add a destructive / DoS payload
- [ ] Does **not** remove or weaken the first-run consent gate or the Learn layer
- [ ] No real credentials, private keys, or live `settings.toml` in the diff
- [ ] Follows existing code style; binds hardware by **name/chipset**, not `wlanN`/`fb#`
- [ ] Commit messages explain the **why**
