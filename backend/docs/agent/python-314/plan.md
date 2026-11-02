# Moving OpenDLP to Python 3.14 — plan

Status: reviewed by Doctor Chewie 2026-10-16 (two rounds); all questions
answered, decisions recorded below. Nothing has been implemented yet.

## Decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Does the CI 3.14 leg really run 3.14? | **Yes** — last run logged `Using CPython 3.14.8 interpreter at: /opt/hostedtoolcache/Python/3.14.8/x64/bin/python3.14` |
| Q2 | Drop `libpcre3` and `libxml2` from the runtime image? | **Yes, after verifying** with an `ldd` check (step 4) |
| Q3 | Dockerfile approach | **Option A** — `ubuntu:resolute` with its system Python 3.14 |
| Q4 | `requires-python` | **Keep `>=3.12`** for now; raise in a follow-up once production has been on 3.14 for a while |
| Q5 | CI matrix | **(a) unchanged now** (`3.12`, `3.13`, `3.14`); (b) or (c) when we raise `requires-python` — see below |
| Q6 | ruff `TC001`–`TC003` when the target moves to py314 | **Deferred** — decide when we raise `requires-python` |
| Q7 | Follow-ups in scope? | **In:** bump CI `uv-version` to `0.12.24`; slim the build stage's apt installs (Doctor Chewie will test). **Out:** coverage `sysmon` |
| Q8 | Production host compatibility | Host is **Debian 13 (trixie)** — recent, broadly compatible with a 26.04 container userland. No concern |
| Q9 | Pin the Dockerfile uv image? | **Yes** — pin to `0.12.24` and add the Dependabot `docker` ecosystem in this change |
| Q10 | CI matrix after raising `requires-python` | Drop 3.12 and 3.13; add 3.15 if our dependencies are ready, otherwise 3.14 alone |
| Q11 | CI check of the image's Python version? | **No** — the Dockerfile's smoke test is enough |

## Where the version is set today

Found by grepping the monorepo (excluding `node_modules`, `.venv`, static
assets and historical docs):

| Place | Current value | Notes |
|---|---|---|
| `backend/.python-version` | `3.12` | Local dev pin. uv obeys it unless `UV_PYTHON` is set |
| `backend/pyproject.toml` `requires-python` | `>=3.12` | Already open-ended, so 3.14 is allowed. Stays as is (Q4) |
| `backend/pyproject.toml` `[tool.ruff] target-version` | `py312` | Stays as is while `requires-python` does — see "ruff target" below |
| `backend/uv.lock` | `requires-python = ">=3.12"`, forks at `3.14.*` and `>=3.15` | Already resolved for 3.14. **No re-lock needed** |
| `backend/Dockerfile` build stage | `ubuntu:noble`, `python3.12-dev`, `UV_PYTHON=python3.12` | |
| `backend/Dockerfile` runtime stage | `ubuntu:noble`, `python3.12`, `libpython3.12` | |
| `.github/actions/setup-env/action.yml` | `python-version` default `"3.12"`; `uv-version` default `"0.9.17"` | BDD (`bdd.yml`) has no matrix, so **BDD only ever runs on 3.12** |
| `.github/workflows/main.yml` | matrix `["3.12", "3.13", "3.14"]`; Codecov upload only on the `3.12` leg | Comment mentions "the local dev pin, 3.12" |

Places checked that do **not** need changing:

- `mypy` has no `python_version` setting — it checks against whatever
  interpreter runs it, so it follows `.python-version`.
- `.pre-commit-config.yaml` runs everything through `uv run --project backend`,
  so it follows `.python-version`.
- `compose*.yaml` build from the `Dockerfile`; no Python version of their own.
- `opendlp-infra`: its Python references are the host's `python3` for Ansible
  and its own `ansible-files/pyproject.toml`. The app runs in the image, so the
  infra repo needs no change for this.
- `README.md` and `docs/*.md` don't mention a Python version.
- Historical docs under `docs/agent/history/` mention 3.12 — leave them,
  they are history.

## Dependency readiness

Every package in `uv.lock` with a compiled extension has a `cp314` (or `abi3`)
manylinux x86_64 wheel: cryptography, psycopg-binary, greenlet, highspy,
numpy, scipy, cvxpy and its solvers, pillow, markupsafe, msgspec, rpds-py,
cffi, time-machine. `ruff` and `playwright` ship `py3-none` platform wheels.
So nothing needs compiling from source on 3.14 — which is also what makes
slimming the build stage (below) plausible. (aarch64 not checked — we only
build amd64 images.)

The CI 3.14 leg is genuine (Q1): it ran CPython 3.14.8. Note that production
will run Ubuntu's **3.14.4** (with Canonical's security backports), so CI
tests a slightly newer patch release than we deploy. Patch releases don't
change behaviour we rely on, so I don't think this needs a matching CI leg —
the BDD run and the image checks in step 4 cover the deployed interpreter.

## The Dockerfile: Option A (chosen)

Facts checked by running the `ubuntu:resolute` image:

- `ubuntu:resolute` is **Ubuntu 26.04.1 LTS** (released 2026-04-23, standard
  support to 2031). In it, `python3` is `3.14.3-0ubuntu2` and `python3.14` /
  `libpython3.14` / `python3.14-dev` are `3.14.4-1ubuntu0.2`.
- **`libpcre3` does not exist in resolute** (PCRE1 is gone) and **`libxml2` has
  been renamed `libxml2-16`**. Our runtime stage installs both, so a straight
  `s/noble/resolute/` will fail to build.
- Nothing in `uv.lock` obviously needs either library (no lxml, uwsgi, xmlsec).
  Both have been in the Dockerfile since the first commit and look inherited
  from the Hynek "production-ready Python Docker containers with uv" article,
  whose example app used uWSGI (which links PCRE). We drop them, and verify
  with `ldd` (step 4).

The change: both stages `FROM ubuntu:resolute`; `python3.12*` → `python3.14*`;
`UV_PYTHON=python3.14` (and the comment above it); drop `libpcre3` and
`libxml2`; drop the dated `apt-get upgrade -qy libssl3t64 libcap2` line (a
noble-specific workaround from 2026-06-11).

Why A over the alternatives, kept for the record:

- **A** keeps the security-update channel we already rely on — Canonical
  patches the interpreter (and its OpenSSL) until 2031, delivered by the
  `unattended-upgrade` step we already run. Costs: Ubuntu holds Python at a
  patch version with security backports only, and the next Python move
  (3.15/3.16) either waits for Ubuntu 28.04 or needs a different approach.
- **B** (uv-managed python-build-standalone) decouples Python from the base
  image, but that build statically links its own OpenSSL, so
  `unattended-upgrade` would stop patching Python's `ssl` module; security
  fixes would come only from bumping uv and rebuilding. Dependabot pull
  requests could do that bumping (see "Pinning the uv image" below), which
  makes B more viable than I first gave it credit for. A good candidate when
  we want 3.15+ before Ubuntu 28.04.
- **C** (official `python:3.14-slim-trixie`) is well maintained but switches
  distro from Ubuntu to Debian — a bigger change for a similar outcome.
- **D** (noble + deadsnakes PPA) has no security-update guarantee. Rejected.

Risk to watch: 26.04 is a new distro release for Grype's vulnerability DB.
The `docker-security` workflow on the PR will show whether it is supported and
whether there's a new crop of "fixed upstream, not yet in Ubuntu" findings.

### Slimming the build stage (Q7 — in scope)

The build stage currently installs:

```
build-essential ca-certificates libffi-dev git python3-setuptools python3.12-dev
```

With every dependency available as a wheel, I think the build stage needs only
an interpreter for uv to use, plus CA certificates. Proposal:

| Package | Proposal | Reasoning |
|---|---|---|
| `python3.12-dev` | → **`python3.14`** | uv needs an interpreter to build the venv against. `-dev` only adds C headers for compiling extensions, which we no longer do |
| `build-essential` | **drop** | No C compilation if everything comes from wheels |
| `libffi-dev` | **drop** | Only needed to compile `cffi` from source; it ships a cp314 wheel |
| `python3-setuptools` | **drop** | Our build backend is `uv_build`; nothing in the lock builds with setuptools from source |
| `git` | **drop, but check** | The only git source in `uv.lock` is `gettext-auto`, a *dev* dependency, and the image syncs with `--no-dev`. Need to confirm `uv sync --locked --no-dev` doesn't try to fetch it anyway |
| `ca-certificates` | **keep** | Cheap, and HTTPS from `apt`/`npm`/`uv` is not worth gambling on bundled roots |

This also keeps "everything comes from wheels" true over time: if a
dependency ever needs compiling, the slimmed build stage will **fail loudly**
(no compiler) rather than quietly building from source. That's the signal we
want, so no extra guard is needed.

Doctor Chewie will do some testing of this; my verification is that
`docker build` succeeds and the step 4 checks pass.

### Pinning the uv image

Decided (Q9): pin it, and let Dependabot keep it current. Today the
Dockerfile copies uv from `ghcr.io/astral-sh/uv:latest`, so the image build
uses whatever uv is newest on the day. Pin it to `0.12.24`, the same version
CI moves to, so CI and the image agree.

Dependabot's `docker` ecosystem updates the image in `FROM` lines. I'm not
confident it updates `COPY --from=<image>` references, so the robust shape is a
named stage:

```dockerfile
FROM ghcr.io/astral-sh/uv:0.12.24 AS uv
...
COPY --from=uv /uv /usr/local/bin/uv
```

Then add a `docker` entry to `.github/dependabot.yml`, matching the style
of the existing entries (weekly, 7-day cooldown). Unlike the other
ecosystems, `docker` does not support `semver-major-days`:

```yaml
  - package-ecosystem: "docker"
    cooldown:
      default-days: 7
    directory: "/backend"
    schedule:
      interval: "weekly"
    ignore:
      # Node is pinned to an LTS line on purpose; moving to the next LTS is a
      # deliberate change, not a weekly bump.
      - dependency-name: "node"
        update-types: ["version-update:semver-major"]
```

What that entry will see in the Dockerfile:

- `ghcr.io/astral-sh/uv:0.12.24` — the point of the exercise.
- `ubuntu:resolute` — a codename tag with no version to compare, so I expect
  Dependabot to leave it alone (it may offer digest pinning; we can decline).
- `node:24-bookworm-slim` — minor/patch bumps within 24 are fine; majors are
  ignored by the config above. Whether you want that ignore is a small call —
  drop it if you'd rather see the PRs.

The CI `uv-version` input in `setup-env/action.yml` is **not** something
Dependabot will bump — it's a plain string input — so that one stays manual.
When a Dependabot PR bumps the Dockerfile's uv, bump `uv-version` by hand to
match. I'll add a comment next to each pointing at the other, so the pairing
is discoverable.

Verification for this part: after merging, the Dependabot "docker" job appears
under Insights → Dependency graph → Dependabot, and its first run raises
no error for `/backend/Dockerfile`.

## Other decisions

### CI matrix (Q5)

Now: matrix unchanged at `["3.12", "3.13", "3.14"]`, but make 3.14 the
primary leg — change the `setup-env` default to `"3.14"` (this also moves
**BDD onto 3.14**, which it has never run on), and move the Codecov upload
condition from `'3.12'` to `'3.14'`.

Later, when we raise `requires-python` and drop 3.12 and 3.13: either
`["3.14", "3.15"]` or `["3.14"]` alone. Python 3.15 has a stable release, but
not all our dependencies support it yet — in particular the numeric libraries
`sortition-algorithms` depends on (numpy, scipy, cvxpy and its solvers,
highspy). So the 3.15 leg waits until those publish 3.15 wheels, and even then
probably starts as `continue-on-error`.

Confirmed (Q10): when we drop 3.12 and 3.13, add 3.15 if the dependencies
are ready, otherwise run 3.14 alone.

### ruff `target-version` (Q6 — deferred)

Stays `py312` while `requires-python` does. When it moves to `py314`, expect
churn. I tried it (and reverted): 461 findings —

- 89 auto-fixes: `Generator[X, None, None]` → `Generator[X]` (UP043), and
  removing quotes from annotations (UP037), because 3.14 evaluates
  annotations lazily (PEP 649).
- 372 `TC001`–`TC003`: "move this import into an `if TYPE_CHECKING:` block".
  With lazy annotations ruff thinks many imports are typing-only. Some are
  not — Flask-WTF, SQLAlchemy and anything that introspects annotations at
  runtime — so blindly applying these can break things at runtime in ways the
  type checker won't see.

My lean, for when we revisit: ignore `TC001`–`TC003`. Decision deferred.

Warning for whoever does that bump: `[tool.ruff]` has `fix = true`, so even a
"just looking" `ruff check --target-version py314` rewrites files.

### `from __future__ import annotations`

45 files use it. On 3.14 it still works but is redundant (PEP 649/749).
Leave it until `requires-python >= 3.14`; then removing it is optional churn.

## Out of scope

- **`COVERAGE_CORE=sysmon`** (Q7): `faster-tests-round-3/research.md` found
  that branch coverage via `sys.monitoring` needs 3.14 and that coverage is
  ~70% of the test-run time. Worth measuring after this lands, as its own
  piece of work.
- Raising `requires-python`, the ruff target, and shrinking the CI matrix —
  all one later follow-up.
- Option B, if we want 3.15+ before Ubuntu 28.04.

## Sequence

Each step is a separate commit on the `python-314` branch.

1. ✅ **CI** (done; all GitHub Actions green on the PR, including BDD on 3.14 and the image scan) — in `setup-env/action.yml`: `python-version` default `"3.14"`,
   `uv-version` default `"0.12.24"`. In `main.yml`: Codecov leg `'3.14'`;
   update the "local dev pin, 3.12" comments. Push and confirm all legs plus
   BDD are green. (BDD on 3.14 is the one genuinely new signal here.)
2. ✅ **Local dev** (done: `just test` on CPython 3.14.8 — 7200 passed,
   5 skipped, 819 JS tests passed; `just check` clean. The 4 pytest warnings
   also appear on 3.12, so they predate this change) — `.python-version` → `3.14`. uv recreates `.venv` on next
   `uv sync`/`uv run`. Run `just test` (serial, full, includes BDD) and
   `just check`. Note: every worktree's `.venv` gets recreated too. Also:
   local uv is 0.11.7, older than the 0.12.24 CI will use — worth upgrading
   locally so the lockfile handling matches.
3. ✅ **Dockerfile** (done — see the notes after the sequence) — `noble` → `resolute`; Python packages to 3.14;
   `UV_PYTHON=python3.14` (and the comment above it); remove `libpcre3`,
   `libxml2`, and the dated `apt-get upgrade` line; slim the build stage's
   apt installs as above; pin the uv image to `0.12.24` via a named `uv`
   stage, with a comment pairing it with the CI `uv-version`. The Node copy
   stays — it pins Node independently of whatever resolute's apt offers.
   Separate commit: the `docker` entry in `.github/dependabot.yml` ✅ (done;
   validated against the Dependabot JSON schema — the first Dependabot run
   after merge is the real check).
4. ✅ **Verify the image locally** (done, except the hand-over — results below):
   - `docker build` succeeds (with the slimmed build stage, this also proves
     nothing compiled from source); the existing smoke test prints
     `Python 3.14.x` and `import opendlp` works.
   - `ldd` every `.so` under `/app` in the runtime image — nothing
     "not found". This is the check that justifies dropping `libpcre3` and
     `libxml2`.
   - `docker compose up` (app + celery worker), log in, run a selection
     end to end, export to CSV.
   - Run Grype locally (or let `docker-security` on the PR do it) and compare
     the findings with a noble build.
   - Hand over to Doctor Chewie for testing of the slimmed build stage.

   **Step 3 notes — two changes the plan didn't anticipate:**

   - **`uv run --no-sync pybabel compile`.** Dropping `git` from the build
     stage failed the build: a plain `uv run` syncs the default groups first,
     so the build was installing every *dev* dependency into `/app` (including
     `gettext-auto` from git) just to compile catalogues, and the final
     `uv sync --no-dev` then removed them again. Babel is a production
     dependency (via flask-babel), so `--no-sync` is all that's needed. The
     final sync now installs exactly 1 package (the project). With that, `git`
     is dropped as planned.
   - **`rm -f /usr/bin/pebble` in the runtime stage.** The `ubuntu:resolute`
     base image ships Canonical's Pebble service manager as a bare binary
     outside dpkg (noble does not), so `unattended-upgrade` can never patch it.
     Grype found its Go 1.26.7 standard library carries 1 Critical and 8 High
     vulnerabilities with fixes available — exactly what makes the
     `docker-security` job fail. Nothing uses it: the base image's entrypoint
     is null and ours is gunicorn or celery.

   **Step 4 results:**

   - Red first: the minimal `noble` → `resolute` change failed with
     `Unable to locate package libpcre3` and `Package 'libxml2' has no
     installation candidate`, as predicted.
   - `docker build` succeeds with the slimmed build stage (only
     `ca-certificates` and `python3.14`). Smoke test: `Python 3.14.4`,
     `import opendlp` OK.
   - `ldd` over 257 shared objects: the only "not found" lines are inside
     `sparsediffpy.libs` (vendored gfortran/quadmath that resolve through the
     loading module's `$ORIGIN` RPATH, not standalone). Importing every native
     module in the image (numpy, scipy, cvxpy and solvers, highspy,
     sparsediffpy, psycopg, cryptography, Pillow, msgspec, markupsafe, ssl,
     sqlite3, lzma…) succeeds, and a cvxpy solve returns `optimal`. Nothing
     needed `libpcre3` or `libxml2`. Interpreter `ssl` is OpenSSL 3.5.5.
   - Production-like stack (scratch compose, gunicorn with production's flags,
     Celery worker, `FLASK_ENV=production`): `alembic upgrade head` from an
     empty database, `opendlp database seed`, home page 200, `/health`
     reports `database_ok` and `celery_worker_running`, static CSS served,
     Hungarian pages render (`lang="hu"`, so the `.mo` files compiled). Login
     over HTTP as the seeded admin reaches the dashboard (password hashing
     goes through `hashlib`/OpenSSL). A real database selection, started with
     `start_db_select_task`, ran in the containerised worker (pickle
     serializer round trip) and completed — 5 selected from 40 — and
     `generate_selection_csvs` exported 5 + 35 rows. No errors or warnings in
     the app or worker logs.
   - Grype (local, latest DB): **0 Critical, 0 High**; 219 Medium and 6 Low,
     of which only 1 Medium and 1 Low have a fix available — below the CI
     cutoff (`only-fixed`, `high`). The comparison with the noble production
     image could not run: this VM's 19 GB disk can't hold that image and a
     freshly hydrated Grype database at once. The `docker-security` job on the
     PR is the authoritative scan anyway.
   - The selection and CSV export were driven through the service layer in
     the container rather than by clicking through the UI; the BDD suite
     (step 2, now on 3.14) covers the UI path.
5. **Preview** — `just hdpreview` deploys the image to the preview server; poke
   at it, including a Google Sheets selection (gspread/SSL path) and
   sending an email (SMTP/SSL path), since those are where the base image's
   OpenSSL changes would show.
6. **Staging, then production** via `opendlp-infra` as usual. The host is
   Debian 13, so a 26.04 container userland is fine (Q8). Rollback is
   redeploying the previous image tag — no DB migration is involved. Celery
   uses the **pickle** serializer (`entrypoints/celery/app.py`), so a task
   queued by a 3.12 process may be run by a 3.14 worker, or the other way
   round on rollback. Pickle's default protocol is 5 on both versions and the
   pickled classes are our own unchanged code, so I expect this to be fine,
   but the safest deploy is still to let the queue drain before switching.

## Testing

This change adds no application code, so there's no new behaviour to unit
test. The evidence that it works is:

- unit/integration/e2e: the full non-BDD suite on 3.14 (CI matrix + `just test`);
- BDD: the full BDD suite on 3.14 (newly, via the `setup-env` default);
- the image: the Dockerfile's smoke test, the `ldd` check, a manual end-to-end
  run in compose, the Grype scan, and Doctor Chewie's testing of the slimmed
  build stage.

No separate CI check of the image's Python version (Q11): the Dockerfile's
smoke test already prints it and imports the app.

## Open questions

None — all answered. Ready to implement on your go-ahead.
