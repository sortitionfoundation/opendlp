# Monitor selection fixtures

Source-of-truth CSV exports used to seed the monitor selection sheet
in each deployed environment. Used by the end-to-end monitoring
feature (issue #582).

- `respondents.csv` — people tab content (registrants).
- `categories.csv` — targets tab content (quota categories).

When provisioning a new environment, copy these into the monitor
Google Sheet's people / targets tabs. See
[`../../monitoring.md`](../../monitoring.md) for the full
provisioning sequence.

As for the assembly settings:

- The number of people to select with these targets is: **30**.
- The id column is **unique_id**.
- Turn off "check same address"
