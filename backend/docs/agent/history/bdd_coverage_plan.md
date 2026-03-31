# Plan: Collect Coverage from BDD Subprocess Flask/Celery

## Context

BDD tests launch Flask and Celery as OS subprocesses via `subprocess.Popen`. pytest-cov only measures code in the pytest process itself, so all server-side code exercised by Playwright is invisible to coverage. We want to run those subprocesses under `coverage run` so we can combine the data afterward.

## Approach

Use `coverage run --parallel-mode -m flask/celery ...` to wrap the subprocess commands, gated behind a `BDD_COVERAGE` env var. After pytest finishes, combine all coverage files and check the threshold.

No separate config file needed — subprocesses read `pyproject.toml` automatically, and `--parallel-mode` is passed on the CLI.

## Files to Modify

### 1. `pyproject.toml` — coverage config changes

- Add `sigterm = true` to `[tool.coverage.run]` — ensures coverage data is saved when subprocesses receive SIGTERM
- Remove `fail_under = 90` from `[tool.coverage.report]` — because pytest-cov would check it *before* we combine with subprocess data; the check moves to the justfile
- Remove `omit = ["tests/bdd/*"]` — now that we're collecting BDD coverage, we want to measure the BDD test code too

```toml
[tool.coverage.run]
source = ["src", "tests"]
plugins = ["covdefaults"]
sigterm = true                    # <-- NEW

[tool.coverage.report]
skip_empty = true
# fail_under removed, checked explicitly in justfile after combining
```

### 2. `tests/bdd/conftest.py` — wrap subprocesses with coverage

Add a helper function and modify both fixtures:

```python
def _build_coverage_command(base_module_args: list[str]) -> list[str]:
    """Wrap a command with coverage run if BDD_COVERAGE is enabled."""
    if to_bool(os.environ.get("BDD_COVERAGE")):
        return ["uv", "run", "coverage", "run", "--parallel-mode", "-m"] + base_module_args
    return ["uv", "run"] + base_module_args
```

Uses `to_bool()` from `src/opendlp/config.py` (already handles "true"/"1"/"yes"/etc).

**test_server fixture** — change the Popen command:
```python
# Before:
["uv", "run", "flask", "run", f"--port={BDD_PORT}", "--host=127.0.0.1"]
# After:
_build_coverage_command(["flask", "run", f"--port={BDD_PORT}", "--host=127.0.0.1"])
```

**test_celery_worker fixture** — change the Popen command:
```python
# Before:
["uv", "run", "celery", "--app", "opendlp.entrypoints.celery.tasks", "worker", "--loglevel=info"]
# After:
_build_coverage_command(["celery", "--app", "opendlp.entrypoints.celery.tasks", "worker", "--loglevel=info"])
```

When `BDD_COVERAGE` is not set (manual debugging, `just test-bdd-not-headless`), commands are unchanged — no overhead.

### 3. `justfile` — orchestrate combine + threshold check

**Replace `test-html`:**
```just
test-html:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "🚀 Testing code: Running pytest with BDD coverage"
    BDD_COVERAGE=true CI=true uv run python -m pytest --tb=short --cov --cov-config=pyproject.toml; PYTEST_EXIT=$?
    echo "🚀 Combining coverage data from BDD subprocesses"
    uv run coverage combine --append 2>/dev/null || true
    uv run coverage html
    uv run coverage report --fail-under=90 || PYTEST_EXIT=2
    exit $PYTEST_EXIT
```

**Replace `test-xml`:**
```just
test-xml:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "🚀 Testing code: Running pytest with BDD coverage"
    BDD_COVERAGE=true CI=true uv run python -m pytest --tb=short --cov --cov-config=pyproject.toml; PYTEST_EXIT=$?
    echo "🚀 Combining coverage data from BDD subprocesses"
    uv run coverage combine --append 2>/dev/null || true
    uv run coverage xml
    uv run coverage report --fail-under=90 || PYTEST_EXIT=2
    exit $PYTEST_EXIT
```

**Update `test-nobdd`** — add explicit fail-under since it's no longer in pyproject.toml:
```just
test-nobdd:
    @echo "🚀 Testing code: Running pytest"
    uv run python -m pytest --tb=short --ignore=tests/bdd --cov --cov-config=pyproject.toml --cov-report=html --cov-fail-under=80 -n auto
```

**`test-bdd`** — unchanged (no coverage collection).

### 4. `.github/workflows/main.yml` — add `--cov-fail-under=80`

Line 104, add the flag with a lower threshold (80%) since non-BDD runs don't include the BDD-exercised code paths — the full 90% is only expected with BDD coverage combined:
```yaml
run: uv run python -m pytest tests --ignore tests/bdd --cov --cov-config=pyproject.toml --cov-report=xml --cov-fail-under=80
```

### 5. `.github/workflows/bdd.yml` — optionally add coverage

This is optional and can be done later. The BDD CI workflow could collect coverage and upload to Codecov, but it adds complexity (needs `--cov` flags, combine step, codecov upload). Recommend deferring this.

### 6. `.gitignore` — ensure coverage parallel files are ignored

Check that `.coverage.*` pattern is in .gitignore (parallel-mode files like `.coverage.hostname.pid.random`).

## How it works end-to-end

1. `just test` sets `BDD_COVERAGE=true` and runs pytest
2. pytest-cov measures the pytest process, writes `.coverage`
3. BDD fixtures detect `BDD_COVERAGE=true` and launch Flask/Celery under `coverage run --parallel-mode`
4. Subprocesses write `.coverage.<machine>.<pid>.<random>` files
5. When BDD fixtures call `process.terminate()`, `sigterm = true` ensures coverage data is flushed
6. After pytest finishes, `coverage combine --append` merges `.coverage.*` files into `.coverage`
7. `coverage html` / `coverage report --fail-under=90` runs on the combined data

## Risks and mitigations

- **SIGTERM not reaching coverage process through `uv run`**: If `uv run` doesn't forward SIGTERM properly, coverage data won't be saved. Mitigation: test manually first; fallback is switching `process.terminate()` to `process.send_signal(signal.SIGINT)` in the BDD fixtures.
- **No subprocess files to combine**: When reusing an already-running server or when `BDD_COVERAGE` is off, `coverage combine` finds nothing — the `|| true` handles this gracefully.
- **`--append` flag**: Critical — without it, `coverage combine` would replace `.coverage` (pytest's data) rather than merging into it.

## Verification

1. Run `just test-nobdd` — should work as before, checking coverage at 80% (lower threshold without BDD)
2. Run `just test` — should run all tests, combine coverage, and report combined percentage
3. Check that `.coverage.*` files appear in backend/ during the BDD run
4. Compare coverage percentage before/after to see the BDD contribution
5. Run `just test-bdd` — should work without coverage (no overhead for debugging)
