<!-- Thanks for the PR. Keep it focused: one logical change per PR. -->

## What & why

<!-- What does this change, and what problem does it solve? -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature (integration, metric, endpoint, setting)
- [ ] Docs / comments only
- [ ] Refactor / internal (no behavior change)

## How tested

<!-- Commands run, plus any manual checks against /pixel, /embed, /badge, or /stats. -->

- [ ] `uv run pytest -q`
- [ ] `uv run ruff check collector tests`
- [ ] Manually verified the affected endpoint

## Screenshots / samples

<!-- For embed, badge, or /stats output changes: before/after. Delete if not applicable. -->

## Checklist

- [ ] All commits signed off with `git commit -s` (Developer Certificate of Origin) — see [CONTRIBUTING.md](CONTRIBUTING.md)
- [ ] Tests added or updated for behavior changes
- [ ] No secrets, tokens, or raw IPs added
- [ ] No cookies, client-side storage, fingerprinting, or third-party scripts introduced
- [ ] README / [doc/COMPLIANCE.md](doc/COMPLIANCE.md) updated if config, endpoints, or privacy behavior changed
- [ ] New env vars or settings added to the README configuration table
