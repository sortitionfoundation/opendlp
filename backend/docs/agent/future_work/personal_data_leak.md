# A respondent's external ID can be personal data, and it survives erasure

## The problem

When someone asks to be forgotten, `Respondent.delete_personal_data()` blanks
their email, consent flags and every attribute, and sets their status to
`DELETED`. It deliberately keeps the row and its `external_id`. That is the
"blank the details, keep the row" strategy in
[docs/personal-data.md](../../personal-data.md#gdpr-and-the-right-to-be-forgotten):
anything that refers to the respondent keeps a valid reference.

The strategy assumes the ID is not itself personal data. Nothing enforces that.
If the ID is an email address, a phone number or a name, erasure leaves it in
place and keeps showing it.

## Where the external ID comes from

| Source | How the ID is chosen | Risk |
| --- | --- | --- |
| Registration page | Generated: `reg-` plus 12 random hex characters (`registration_submission_service._generate_external_id`) | None |
| CSV upload | The column the organiser picks, or **the first column** when they don't pick one (`import_respondents_from_csv`) | High: an email or name column first in the file becomes the ID silently |
| Manual entry | Typed by the organiser (`create_respondent`) | Medium: depends on what they type |

The CSV default is the likeliest leak. Spreadsheets often start with a name or
an email column.

## Where the ID shows up after erasure

- **Respondents list:** the "ID" column, under the "Deleted" filter.
- **Single respondent page.**
- **Export, CSV and Google Sheets:** the "Deleted" filter exports one row per
  deleted respondent, carrying the ID. It exists so organisers can erase people
  from copies held outside OpenDLP, which only works if the ID means something
  to them.
- **`selection_run_records`:** `selected_ids` and `remaining_ids` are JSON lists
  of external IDs, captured at selection time and never touched by erasure.
- **Selection output:** `sortition.py` inserts blanked rows for deleted external
  IDs so historical selection CSVs still reference known IDs.
- **To check:** the `selection_run_records` columns `run_report` and
  `log_messages`. `selection_report.py` builds messages such as
  "Respondent {external_id} has value ...", and it is not yet established
  whether those are stored.

## Options

**A. Stop personal data becoming the ID (prevention).**
At upload, check the chosen ID column. If its values look like email addresses
or phone numbers, warn, or refuse unless the organiser confirms. Consider
generating IDs instead of defaulting to the first column when no ID column is
chosen. This is cheap and covers the likeliest case, but it can't catch names
and does nothing for data already uploaded.

**B. Replace the ID on erasure.**
`delete_personal_data()` swaps `external_id` for a surrogate such as
`deleted-<uuid>`. That removes the leak completely, but:

- the "Deleted" export can no longer tell an organiser who to erase elsewhere,
  so it would need to run *before* the swap, or the swap would need to keep the
  old ID somewhere, which brings the leak back;
- the JSON in `selection_run_records` would need rewriting to match, or
  historical selections lose their link to the row.

**C. Replace the ID on erasure only when it looks like personal data.**
B, applied only where A's check fails. This limits the damage to the risky cases.

## Suggested direction

Do A now: it is small and stops new cases. Then decide between B and C once we
know how many existing assemblies have personal data in their IDs. A one-off
query over `respondents.external_id` for `@` or long digit runs would show that.

## Open questions

- Should the respondent-ID column chosen at upload be shown back to the organiser
  with a sentence about why it should not be personal data?
- Do `run_report` / `log_messages` store external IDs? If so, they need covering
  by whichever option we choose.
- Google Sheets loading: are external IDs from a sheet ever persisted? If so,
  they belong in the table above.
