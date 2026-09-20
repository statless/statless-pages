# Contributing

Thanks for your interest in `statless-pages`. The project is deliberately
small; for anything larger than a bug fix or a focused docs change, please open
an issue first so we can agree on the approach before you write code.

## Developer Certificate of Origin (DCO)

Every commit you submit **must be signed off**. The sign-off is your
certification of the [Developer Certificate of Origin 1.1](https://developercertificate.org/),
reproduced in full below. It is how this project keeps a clean chain of
authorship while all contributions are held under a single copyright holder,
and it is what lets the project be relied on by downstream users.

Add the trailer with `git commit -s`:

```bash
git commit -s -m "fix: correct dwell bucket boundary"
```

which appends:

```text
Signed-off-by: Your Name <you@example.com>
```

The name and email must be your real identity and must match the commit author.
To sign off commits you already made:

```bash
git commit --amend -s                  # just the last commit
git rebase --signoff origin/main       # every commit on your branch
```

CI runs a `dco` check that fails any pull request containing a non-merge commit
without the trailer. Merge commits and automated dependency-update PRs are
exempt.

### Developer Certificate of Origin

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
1 Letterman Drive
Suite D4700
San Francisco, CA, 94129

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## License grant

The sign-off above certifies the origin of your contribution. It is not, by
itself, a license to relicense. Because all code in this repository is held
under a single copyright holder so the project stays able to change its
licensing later, you also agree to the following by submitting a contribution:

You retain copyright in your contribution, but you grant **Dimitrios Xynos** a
perpetual, worldwide, non-exclusive, royalty-free, irrevocable copyright
license to reproduce, prepare derivative works of, publicly display, publicly
perform, sublicense, and distribute your contribution and such derivative
works, under the project's current license **and under any future license**,
including proprietary terms. To the extent any moral or similar rights cannot
be granted, you waive and agree not to assert them.

If you contribute on behalf of an employer, you confirm you are authorised to
make this grant.

## Development setup

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run ruff check collector tests
uv run ruff format --check collector tests
uv run pyright
uv run pytest -q
```

CI runs exactly these steps (see `.github/workflows/ci.yml`); a pull request is
only mergeable when they pass.

## Pull requests

- Keep the change focused; one logical change per PR.
- Match the existing style. Do not reformat unrelated code.
- Add or update tests for behavior changes.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for the
  subject line (e.g. `feat:`, `fix:`, `docs:`), signed off as above.

## License

`statless-pages` is licensed under the [AGPLv3](LICENSE). Contributions are
accepted under the same license (inbound = outbound). By submitting a pull
request you confirm you have the right to do so and agree to the DCO above.
