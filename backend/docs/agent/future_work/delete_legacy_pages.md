# Delete the legacy (pre-backoffice) project pages

Turned up while planning `1024-create-project`, which replaces the backoffice
create page, edit page, Data Source tab and Team Members tab. Each of those has
an older twin under `/assemblies/...` that the plan leaves alone. The legacy
pages have not been live for a while and can go. Written to be pasted into an
issue.

## What is there

Five blueprints registered in `entrypoints/flask_app.py`, with their templates:

| Blueprint | Routes | Templates |
| --- | --- | --- |
| `main` (`blueprints/main.py`) | 10 | `templates/main/` |
| `gsheets_legacy` | 21 | `templates/gsheets/` |
| `db_selection_legacy` | 12 | `templates/db_selection/` |
| `targets_legacy` | 11 | `templates/targets/` |
| `respondents_legacy` | 3 | `templates/respondents/` |

`main` holds `/assemblies/new`, `/assemblies/<id>`, `/assemblies/<id>/edit`,
`/assemblies/<id>/data`, `/assemblies/<id>/members` (view, add, remove) and
`/assemblies/<id>/search-users` — each duplicated by a `backoffice` route.

## Why it is not a plain delete

**`main` is not all legacy.** It also serves `/` (`main.index`) and
`/dashboard` (`main.dashboard`), and those endpoint names are used widely:
about 78 `url_for("main.dashboard")` calls and 7 of `main.index` across
`src/opendlp` and the live templates, including the backoffice footer
(`templates/backoffice/components/footer.html:24`, behind a feature flag —
see below). So the first step is to
decide what `/` and `/dashboard` should be — most likely redirects to the
backoffice dashboard — and where those two endpoints live.

**The Python still points into the legacy blueprints.** There are well over a
hundred `url_for` calls to legacy endpoints from `src/opendlp` — for example
32 to `targets_legacy.view_assembly_targets` and 12 to
`db_selection_legacy.view_db_selection`. Many will be inside the legacy
blueprints themselves, redirecting to each other; any that are in live code
(shared helpers, services building links, emails) need a backoffice
destination first. That audit is the bulk of the work.

**Tests.** The legacy routes have component, e2e and BDD coverage
(`tests/bdd/test_assembly_crud.py` and the `create-assembly`,
`update-assembly`, `view-assembly`, `view-assembly-list` features exercise
`main`). Each test is either deleted with its page or, where it is the only
cover for a service-layer behaviour, moved to the backoffice route.

**Feature flags.** Three flags exist only to steer between the old pages and
the new, and go with them:

| Flag | What it does | Where |
| --- | --- | --- |
| `FF_OLD_DEFAULT_DASHBOARD` | Makes the legacy dashboard the landing page after login | `feature_flags.default_dashboard_endpoint` |
| `FF_DASHBOARD_SWITCH_LINKS` | Shows the links that switch between the two dashboards | `templates/base.html:183`, `templates/backoffice/components/footer.html:23` |
| `FF_CSV_DB_ASSEMBLY_LINKS` | Shows the CSV/database links on the legacy project page | `templates/main/view_assembly_base.html:32` |

With them go `OLD_DASHBOARD_ENDPOINT`, `default_dashboard_endpoint` and
`old_dashboard_route_enabled` in `src/opendlp/feature_flags.py` (callers take
`backoffice.dashboard` directly), the flags' entries in `env.example`, and
any `FF_*` settings in the
deployment configuration. Check each environment has them off before the
release that removes them, so nobody's landing page changes by surprise.

## Suggested order

1. Audit every `url_for` into the five blueprints; sort into "legacy calling
   legacy" and "live code calling legacy".
2. Give the live callers backoffice destinations.
3. Settle `/` and `/dashboard`, and move or redirect `main.index` and
   `main.dashboard`.
4. Delete the legacy routes, their templates, and any JavaScript only they use
   (`src/js/components/team-selector.js` is one: only
   `templates/gsheets/create_config.html` and `edit_config.html` load it).
5. Old URLs: either let `/assemblies/...` 404, or redirect each to its
   backoffice equivalent, as `test_project_url_redirect.py` does for the
   assembly-to-project rename.
6. Remove the three feature flags and their helpers, docs and deployment
   settings.
7. Regenerate the translation catalogues — a good many msgids will fall out.

## What 1024 does in the meantime

It leaves the legacy pages working. The only change it makes to them is to
re-point their links to `backoffice.view_assembly_data`, which stops existing,
at the project details page.
