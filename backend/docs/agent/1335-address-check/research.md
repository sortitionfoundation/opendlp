# Address Check — Research

**Status:** Draft for team discussion — nothing decided, nothing implemented
**Date:** 2026-11-27
**Issue:** 1335
**Scope:** How OpenDLP could check that a respondent registered from an address an invitation was posted to: where the invited addresses live, how matching works, where the result is stored, how a human reviews it, and how it keeps people out of selection. Options and a recommendation for each; the questions the team needs to answer are in [§12](#12-questions-for-the-team).

All addresses in this document are made up.

---

## 1. Summary

An address check has four parts, and they can be decided fairly independently:

1. **The invited addresses** — a per-project list, uploaded as a CSV.
2. **The matcher** — code that compares what a respondent typed with that list and says `OK` or `CHECK`.
3. **The review** — a person turns each `CHECK` into `OK` or `BAD`.
4. **The gate** — only `OK` respondents reach the selection algorithm.

What I would recommend, with the reasoning in the sections below:

| Question                             | Recommendation                                                                                                                                                         | Section |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Is the address check a target?       | **No.** Keep it out of the targets table and filter before selection, next to `eligible` and `can_attend`.                                                               | §6      |
| Is it a derived (computed) question? | **No**, though it borrows the pattern. A human decision has to survive a recompute, and derivation is built so that it never does.                                       | §5      |
| Where do invited addresses live?     | A new table, one row per address, keyed by project and normalised postcode. The uploaded file is parsed in memory and not kept.                                          | §4      |
| How do we match?                     | Our own code, in the domain layer: narrow by postcode, compare the numbers in the address **exactly**, compare the words fuzzily. No new library needed for a first cut. | §3      |
| Which questions are the address?     | An explicit setting: one postcode question plus an ordered list of address-line questions. Not CSV-header matching.                                                      | §7      |
| What about `CHECK` at selection?     | Excluded, with the count shown on the Selection tab and a link to the review queue. Selection is not blocked.                                                           | §6      |
| Can the matcher ever say `BAD`?      | **No.** It says `OK` or `CHECK`. Only a person says `BAD`.                                                                                                               | §3      |

Two things I would put to the team before any of that is planned in detail:

- **Measure first.** The past "our working version" spreadsheets are a labelled data set: every row has the address typed, the formula's verdict, and the human's final verdict. Running candidate matchers over a few of them tells us how big the review queue really is and whether the matcher beats the formula. Without that we are tuning thresholds on invented addresses (§10).
- **A printed code on each letter** would do most of this job without fuzzy matching at all. It has real operational costs, so it may well be a "no", but it should be a deliberate no (§9).

---

## 2. What exists today

### In the spreadsheet

The current check lives in spreadsheet formulas. From the Gemini write-up of one "our working version" sheet (treat the detail as approximate — see the note below):

1. Take the first token of `address_line_1` (`42b`), or `FLAT <id>` if the line starts with "Flat".
2. Normalise the postcode to standard UK spacing.
3. Look up every invited address at that postcode on the `UK Delivery Addresses` tab — up to six of them (columns `DF:DK`).
4. `ok` if the token appears at the start of one of those addresses, otherwise `CHECK`.
5. A person reviews each `CHECK` and overwrites it with `ok` or `BAD`.
6. An `address_check` target with `BAD` at `min = max = 0` keeps the `BAD` rows out.

What that does well: it is strict about the house number (`42` never matches `42B`), it only compares within a postcode, and it never says `BAD` by itself.

Where it falls short:

- **Only the first token of the first line is read.** "Rose Cottage, 12 High Street" and "The Old Bakery 3 Mill Lane" go to `CHECK` even when number 12 or 3 was invited. Anything after the first token is ignored, so a street typo is never noticed either way.
- **A mistyped postcode gives `CHECK` with nothing to compare against**, so the reviewer has to go hunting.
- **"42 b" is read as "42"**, which is a false `ok` if 42 was invited and 42B was not.
- **Six addresses per postcode is a hard limit** of the column layout.
- **It assumes the number comes first**, which is a UK and Australian habit. "Fő utca 12." and "Hauptstraße 5" would always be `CHECK`.

A note on the source: the Gemini write-up is a description of formulas, not the formulas. Its example table has shifted columns and its Python differs from its own prose in small ways (it tests "contains FLAT" where the prose says "starts with"). Before we claim parity with the spreadsheet we should read the actual formulas in a real sheet.

The explainer `docs/explainers/fields-and-targets.html` describes the check as a two-value result (`OK` / `BAD`) enforced by a zero target. It leaves out `CHECK` and the human step. It will need updating once we decide the design; I have not touched it.

### In OpenDLP

Nothing does address checking today. The pieces that matter:

- **There is no "address" concept.** Address questions are ordinary text questions (`RespondentFieldDefinition`, `FieldType.TEXT`), and their answers are keys in `Respondent.attributes`. Nothing marks a question as "address line 1" or "postcode".
- **`check_same_address` is a different feature.** It stops two people from one household both being selected. `SelectionSettings.check_same_address_cols` names the columns, and the sortition library compares them by lower-cased string equality (`people.py::_address_tuple`). It knows nothing about an invite list. It is, though, a second place where a project says "these columns are the address" — see §7.
- **Selection already has a gate.** `OpenDLPDataAdapter.read_people_data` loads respondents with `status=POOL, eligible_only=True`, which drops anyone with `eligible` or `can_attend` explicitly `False`. That is exactly the kind of filter the address check needs.
- **Computed questions** (issue 793) are the nearest existing pattern: a rule, a source question, a value written into `attributes` on all four respondent write paths (registration, CSV import, backoffice create, backoffice edit), and a recompute over the whole pool. The "Map postcode to value" kind stores an uploaded lookup table in `respondent_field_mapping_entries` and already normalises postcodes (`normalise_lookup_key`: upper-case, no whitespace).
- **CSV handling** is in `service_layer/tabular_data.py` (`rows_from_csv`, `clean_table`), used by every upload. `upload_large_mapping` is a good model: parse in memory, resolve columns by header then by position, store rows only, return a report.
- **Google Sheets projects** keep no respondents in the database, so none of this applies to them. Their address check stays in the spreadsheet.

---

## 3. The matcher

### What it has to cope with

- Lines split differently ("Flat 2" on line 1 or line 2).
- Abbreviations (St / Street, Rd / Road, Ave / Avenue, Apt / Flat).
- Case, punctuation, whitespace.
- Parts left out (no street name, no building name, "Flat" dropped: "2 Oak Mansions").
- Typos, in the address and in the postcode.
- Named houses with no number.
- Flat notations: "Flat 2", "2/1", "1F2", "42B", "42 b".
- Other countries: number after the street, different abbreviations, and postcodes that cover a whole town.

### The shape I would build

A pure function in the domain layer: `(entered address lines, entered postcode, invited addresses) -> result`, where the result carries the verdict, the best candidate (if any) and a short machine-readable reason. No database, no Flask, easy to unit test with a table of cases.

1. **Normalise both sides the same way.** Upper-case, strip punctuation, collapse whitespace, join the address lines into one string, glue a lone letter to the number before it ("42 b" → "42B"), apply a small abbreviation table.
2. **Narrow by postcode.** Candidates are the invited addresses with the same normalised postcode. In the UK that is usually one to six.
3. **Split each address into number tokens and word tokens.** A number token is anything containing a digit: `42`, `42B`, `2/1`, `12-14`.
4. **Compare the numbers exactly.** The number tokens must be the same set. This is the rule that carries most of the weight.
5. **Compare the words fuzzily**, with a similarity score, to catch typos and missing parts.
6. **Decide:**
   - exactly one candidate has matching numbers and similar enough words → `OK`
   - anything else → `CHECK`, with the closest candidates attached for the reviewer

`CHECK` reasons worth distinguishing, because they tell the reviewer what to look at: postcode not on the list; postcode on the list but no number matches; numbers match but the words differ; more than one candidate fits; no address entered.

**The matcher never returns `BAD`.** A postcode that is not on the list is very likely a real mismatch, but it is also what a one-character postcode typo looks like. The costs are not symmetric: a wrong `CHECK` costs a reviewer a few seconds, a wrong `BAD` silently drops an invited person from the lottery. If the queue of "postcode not on the list" rows turns out to be large, the answer is a bulk action in the review screen, not an automatic verdict.

For a postcode that is not on the list, the matcher can still help: look for invited postcodes one edit away and offer their addresses as candidates. Still `CHECK`, but the reviewer has something to compare.

### A small spike

I ran eighteen made-up pairs through the normalisation above, scoring the words with Python's built-in `difflib` and with RapidFuzz. A selection:

| Entered                         | Invited                         | Same address? | Numbers equal | Word similarity |
| ------------------------------- | ------------------------------- | ------------- | ------------- | --------------- |
| 42 b High St.                   | 42B HIGH STREET                 | yes           | yes           | 100             |
| 42 High Street                  | 42B HIGH STREET                 | no            | **no**        | 100             |
| 51 Victoria Road                | 15 VICTORIA ROAD                | no            | **no**        | 100             |
| Flat 3, Oak Mansions, 12 Elm Rd | FLAT 2 OAK MANSIONS 12 ELM ROAD | no            | **no**        | 100             |
| 15 Victoia Rd                   | 15 VICTORIA ROAD                | yes           | yes           | 96              |
| 15 Albert Road                  | 15 VICTORIA ROAD                | no            | yes           | 50              |
| Flat 2 Oak Mansions             | FLAT 2 OAK MANSIONS 12 ELM ROAD | probably      | no            | 79              |
| Meadowview Cotage, Church Ln    | MEADOW VIEW COTTAGE CHURCH LANE | yes           | yes (none)    | 97              |
| Rose Cottage, Church Lane       | MEADOW VIEW COTTAGE CHURCH LANE | no            | yes (none)    | 80              |
| Fő u. 12                        | FŐ UTCA 12                      | yes           | yes           | 73              |
| Hauptstr. 5a                    | HAUPTSTRASSE 5A                 | yes           | yes           | 80              |

What this shows:

- **Text similarity cannot see the difference that matters most.** 42 against 42B, 15 against 51 and Flat 2 against Flat 3 all score 100 on the words. An off-the-shelf "fuzzy match the whole string" approach would wave them through or need a threshold so high it is useless. The exact number comparison is what makes this work.
- **Once the numbers agree, the words need only a loose threshold.** A typo'd street (96) is far from a different street (50).
- **Named houses are the weak spot.** With no number to anchor on, a different cottage on the same lane scores 80 — higher than a correct Hungarian address with an abbreviated street (73). Addresses with no number tokens need a stricter rule than addresses with them, and will produce most of the honest `CHECK`s.
- **Missing parts break strict number equality.** "Flat 2 Oak Mansions" lacks the building's street number. Whether "the entered numbers are a subset of one candidate's, and of no other candidate's" should count as `OK` is a judgement call I would settle with real data (§10).
- **`difflib` and RapidFuzz gave identical scores** on every pair. They differ in speed: 30,000 comparisons took 293 ms in `difflib` and 6 ms in RapidFuzz. With postcode narrowing we do a handful of comparisons per respondent, so speed is irrelevant.

The spike script was a throwaway and is not in the repository.

### Libraries

| Option                                    | What it gives                                                             | Verdict                                                                                                                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Standard library (`difflib`, `re`)        | A similarity ratio, and everything needed for normalising                 | **Enough for a first version.** No new dependency.                                                                                                                                                      |
| RapidFuzz                                 | Fast similarity scores, token-set and partial ratios, edit distances      | Mature, MIT-licensed, has Python 3.14 wheels (3.14.6 installed cleanly here). Worth adding only if we need speed (matching without postcode narrowing) or the token-set scorers. Would need your say-so. |
| libpostal (`postal`)                      | Proper international address parsing and abbreviation expansion           | The best at what it does, but a C library with roughly 2 GB of model data. Too heavy for our images and our problem.                                                                                    |
| `uk_address_matcher`, Splink, `dedupe`    | Probabilistic record linkage at national scale                            | Built for matching millions of messy records with no reliable postcode. We have a short list and a postcode. Overkill.                                                                                  |
| `usaddress`, `pyap`                       | Address parsing                                                           | US-centred. Not useful.                                                                                                                                                                                 |
| Paid lookup APIs (address finders)        | The respondent picks a canonical address; matching becomes exact          | See §9. Costs money, adds a third-party script to the registration page, and differs per country.                                                                                                       |

My recommendation is our own code. The hard part of this problem is the rules (what counts as a number token, when a missing part is acceptable), and no library supplies those. A similarity score is the easy part and the standard library has one.

### Other countries

The UK habit of "postcode narrows it to a few doors" does not travel. A Hungarian or Australian four-digit postcode covers a town or suburb, so the candidate set could be hundreds of addresses; a Dutch postcode plus house number is unique; an Irish Eircode is unique by itself.

The token approach copes, because it does not depend on where the number sits or on how small the postcode area is — it just has more candidates to rank, and leans harder on the street name. Two consequences:

- The abbreviation table has to be per-language and small, and the matcher should work acceptably without it.
- Postcode normalisation must not assume the UK format. `normalise_lookup_key` (upper-case, strip whitespace) is already format-neutral and is the right thing to reuse. The UK-specific "last three characters are the inward code" logic from the spreadsheet is not needed for matching.

---

## 4. Storing the invited addresses

### Options

**A. A new table** — `invited_addresses` or similar: `id`, `assembly_id`, `postcode_key` (normalised), the address as supplied, `created_at`; indexed on `(assembly_id, postcode_key)`.

**B. Reuse `respondent_field_mapping_entries`.** It is the existing "big uploaded lookup table". But it is unique on `(field_id, lookup_key)` — one output per key — and we need many addresses per postcode. It could only hold a pre-computed key such as `postcode|number`, which reproduces the spreadsheet's first-token check and gives the reviewer no candidates to look at.

**C. Do not store them.** Upload the list each time you want to run the check; hold it in Redis for the session. No long-term copy at all, which is attractive for data protection, but then registrations cannot be checked as they arrive and every recheck needs the file again.

**D. Store only hashes** of a normalised key. Exact matching still works; fuzzy matching and showing candidates to a reviewer do not. It also buys little: UK address space is small enough to enumerate, so the hashes are reversible in practice.

I recommend **A**. It is a plain additive migration (new table, backwards compatible, no downtime), and it needs the usual two test-cleanup entries (`_delete_all_test_data` and `delete_all_except_standard_users`).

### Upload

Follow `upload_large_mapping`: parse with `rows_from_csv` and `clean_table`, never keep the file, store rows, return a report (rows stored, duplicates, rows with no postcode). Then recompute the check for the whole pool.

Things to decide:

- **Column mapping.** The file has a postcode column and one or more address columns. Asking the organiser to pick them on a confirmation step is more robust than matching headers to question keys, which you rightly called fiddly. Header matching can still pre-fill the picks.
- **Replace or add.** Projects that send a second mailing need to add addresses. "Replace the whole list" is simpler and always correct if the organiser uploads the combined file. I would start with replace-only.
- **Size.** The large-mapping cap is 500,000 rows. An invite list is far smaller; I have assumed tens of thousands and would like a real number (§12).

### Who may upload and see it

The list is project data, so `can_manage_assembly` for upload and delete is the obvious starting point. Who can see candidates in the review screen is a separate question (§8).

---

## 5. Storing the result

A result has two layers, and the design should keep them apart:

- the **automatic verdict** (`OK` or `CHECK`), which is recomputed whenever the address or the list changes
- the **human decision** (`OK` or `BAD`), which must not be wiped by a recompute

The effective value is the human decision if there is one, otherwise the automatic verdict. A fourth state, "not checked", covers projects with the check switched on but no list uploaded yet.

When the respondent's address is edited after a human decision, the decision should probably be cleared, because the person decided about a different address. That is worth confirming (§12).

### Options

**A. Dedicated fields on the respondent.** Either a few columns (`address_check`, `address_check_decided_by`, …) or one JSON column holding verdict, reason, matched invited-address id, and the decision with who and when. Follows the `eligible` / `can_attend` precedent of top-level respondent state.

**B. A computed question** — a new `DerivationType` writing `OK` / `CHECK` into `attributes`. It gets the four write paths and the recompute for free. But `_recompute` is documented as "the derivation always wins over whatever value the attribute held", computed questions are deliberately not editable, and the rule machinery reads one source question (`derived_from[0]`) where we need several. The human decision would need its own storage anyway, at which point most of the benefit has gone.

**C. Reuse `eligible`.** Set it to `False` for `BAD`. This overwrites the respondent's own answer to the eligibility question with our verdict, and has nowhere to put `CHECK`. I would rule it out.

**D. A plain attribute plus a target**, as the spreadsheet does. See §6 for why I would not.

I recommend **A**, borrowing two things from B: call the check from the same four write paths that call `apply_derivations`, and model the whole-pool recheck on `_recompute` (including its report of how many changed).

Storing the **matched invited-address id** is worth the extra field. It lets the review screen show what was matched, lets us spot five registrations from one address, makes "how many invited households responded" a query, and helps with erasure (§11).

### Knock-on changes with option A

- **Export and import.** The respondent export should carry the effective value. `IMPORT_LIFTED_COLUMNS` could lift an `address_check` column from a CSV into the new field, which gives a migration path for pools that were checked in a spreadsheet — their `ok` / `BAD` decisions arrive as human decisions.
- **Name collision.** Pools imported from spreadsheets may already have an `address_check` key in `attributes`, and possibly an `address_check` target. Making the name reserved affects them. This needs checking against real projects before we pick the name.
- **Activity log.** A human decision should write a `RespondentComment`, as status changes do, so the respondent's history shows who decided and when.
- **Erasure.** `delete_personal_data` must clear the new fields.

---

## 6. Keeping people out of selection

You named the two options: a target with zero for `BAD`, or a filter before the algorithm.

**A target** is how the spreadsheet does it, and for Google Sheets projects it will stay that way. In the database I would not copy it:

- It is not a target. Nobody agrees a quota for it with a client; it would sit in the targets table as a fake row.
- It needs `OK` pinned at `min = max = panel size`, which breaks whenever the number to select changes, and interacts with the recent min/max-versus-number-to-select work and with replacement targets, which recalculate quotas.
- `CHECK` needs a value and a quota too. Zero, presumably — but then the "target" is three values of which two are always zero.
- The story's idea of listing "address check" among the options on the "Link targets to questions" step inherits all of this. The *step* is a reasonable home for the set-up UI; the *target* is the part I would drop.

**A filter** is one more condition on the rule "who is available for selection". That rule is currently written out in several places, all of which would need the new condition:

- `Respondent.is_available_for_selection` (domain)
- `get_by_assembly_id(..., eligible_only=True)` (what selection actually loads)
- `count_available_for_selection`
- `get_attribute_value_available_counts` (the "available" numbers on replacement targets)
- the dashboard's available count (`dashboard_stats.py`)

Having five copies of one rule is a smell that predates this work. Adding a third condition to each is the moment it starts to hurt, so pulling the rule into one place may be worth doing first, as its own change.

The filter applies only when the project has the address check switched on. With it off, nothing changes.

### What happens to `CHECK` at selection time

- **Exclude and warn** (recommended): `CHECK` and `BAD` are left out; the Selection tab says "12 respondents are waiting for an address check and will not be included", linking to the review queue. The selection run record stores the counts in `settings_used`.
- **Block**: refuse to run a selection while any `CHECK` remains. Safer for fairness — a `CHECK` person later found to be `OK` has missed the draw — but it stops test selections and holds the project hostage to one awkward address.

Excluding matches what you described ("only OK is eligible"). The warning makes the fairness cost visible to the person who can do something about it.

---

## 7. Knowing which questions are the address

The matcher needs two roles: **the postcode question** and **the address-line questions, in order**. City is probably not needed — the postcode already implies it, and it adds another thing to mistype — though it helps where postcodes are large.

Your options, plus one:

| Option                                                   | For                                                                                   | Against                                                                                                              |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| A setting holding a list of question keys                | Simple; mirrors `check_same_address_cols`                                             | A flat list does not say which one is the postcode. Keys are strings, so a renamed question breaks it silently.      |
| A setting holding references to the questions (by id)    | Survives renames; can hold the two roles explicitly                                   | A little more modelling.                                                                                             |
| A flag on each question ("use for address check")        | Visible where questions are edited                                                    | Still needs a role (postcode or line) and an order, so it is really an enum plus the question order, spread across rows. |
| Match CSV headers to question keys                       | No configuration                                                                      | Fiddly, as you said; depends on the mailing house's column names.                                                    |
| Reuse `check_same_address_cols`                          | One definition of "the address" for both features                                     | Same flat-list problem; and a project may want one feature without the other.                                        |

I would go for **explicit references with roles**: one postcode question, an ordered list of address-line questions, stored with the address-check settings for the project. The upload's column-mapping step (§4) then maps the file's columns to the same two roles, and the two sides never need matching names.

Worth a thought for later, not now: `check_same_address_cols` answers the same question ("which columns are the address") for the household rule. If the address check introduces a proper definition, the household rule could read it too, and could compare normalised addresses instead of raw strings. That is a separate change.

**Switching it on.** "Not every project wants this" suggests the feature is on when the project has address-check settings, and off otherwise — no separate tick box to get out of step. A feature flag (`FF_…`) can hide the whole thing while it is being built.

**Where the set-up lives.** Candidates: a step on the registration set-up checklist beside "Link targets to questions"; a section of the Data tab near the respondent upload; or the Selection settings beside "check same address". I have not looked hard at this and it needs design input.

---

## 8. Human review

The reviewer needs, for each `CHECK`:

- the address as the respondent typed it
- the reason (`postcode not on the list`, `no matching number`, …)
- the closest invited addresses, ideally with the differences made obvious
- buttons for `OK` and `BAD`, and perhaps "it is this one" to record which invited address was meant

COMMENT: need to check with the team if we want to edit the address to correct it if the review says it is a typo.

And across the queue: a count, a filter on the respondents list by address-check state, and probably a bulk action for the obvious cases.

Questions this raises:

- **Who can review?** Assembly managers, certainly. Confirmation callers already handle respondent contact details; whether they should also make this call is a policy question. It should be a capability in `permissions.py`, not a role test.
- **Can a decision be undone?** I would assume yes, with the change logged.
- **Is the registrant told?** I would assume not. The registration succeeds as normal either way; telling someone their address did not match invites argument and helps anyone trying to game it.

This is a new UI surface, so the `ui-components` skill, the accessibility rules and `docs/language.md` all apply when we get there. The interface words (`OK` / `CHECK` / `BAD` are spreadsheet jargon) need choosing, and the labels need a translated labels dict rather than rendering an enum value.

---

## 9. Alternatives to matching typed addresses

Returning the serve here: these avoid the fuzzy problem instead of solving it.

**A unique code printed on each letter.** The respondent types the code (or follows a QR code or personalised URL), and the code identifies the invited address exactly. No typos, no abbreviations, works in every country, and tells us the response rate per address for free.

- Costs: the mailing house has to mail-merge a code per letter; we generate and store the codes; people mistype codes too (a check digit helps); and a code proves someone had the letter, not that they live there — though a typed address proves even less.
- It could sit alongside address matching: a valid code gives `OK` at once, and anything else falls back to the matcher and the review queue.
- If the team has considered and rejected this before, it would be good to record why.

**Pick your address from a list.** The respondent enters a postcode and chooses from the invited addresses there. Matching becomes exact. But it shows anyone who types a postcode which households were invited, and it hands an uninvited neighbour the answer they would otherwise have had to guess. I would not do this.

**A commercial address finder** on the registration page. The respondent picks their real address from the national address file, so both sides are canonical. It costs per lookup, adds a third-party script to the public form (which reopens the analysis in `docs/personal-data.md` — read its "what would change the answer" list first), and needs a different supplier per country. It also only helps if the invite list uses the same canonical form.

---

## 10. Measuring before tuning

The thresholds in §3 are guesses. We have the means to replace them with measurements: each past "our working version" spreadsheet holds, per respondent, the address typed, the formula's `ok` / `CHECK`, and the human's final `ok` / `BAD`, alongside the invite list.

Run offline over a few of those, a candidate matcher gives us:

- how many `CHECK`s it produces compared with the formula (the size of the review queue)
- how many of its `OK`s a human had marked `BAD` (the number that matters most — false `OK`s)
- what the remaining `CHECK`s look like, which tells us which rule to add next

This is real personal data, so it must stay out of the repository and out of test fixtures: run it on a machine that is already allowed to hold those spreadsheets, and bring back only counts and made-up examples that reproduce the patterns found. The matcher's unit tests are then written from those patterns with invented addresses.

I would do this before settling the matcher's rules, and ideally before the detailed plan. It needs someone with access to the sheets — that is you or the team, not me.

---

## 11. Personal data

The invite list is a new store of personal data and of a new kind: addresses of people who have, for the most part, never interacted with us. An address with no name is still personal data when it points at a household. I am not a lawyer; this section says what the design must allow for, not what the law requires.

- **No raw file is kept.** The upload is parsed in memory and only rows are stored, as with the large mapping. This fits the existing rule against long-term copies of uploaded files.
- **The rows are findable.** One table, keyed by project, so they can be listed and deleted.
- **Retention needs a decision.** The list is needed while registration is open and while `CHECK`s are being reviewed, and arguably until the last replacement selection. After that it has no purpose. Options: a manual "delete invited addresses" action; deletion a set time after selection completes; deletion when the project is archived (the 1379 archive plan currently deletes nothing). A manual action is the minimum.
- **Erasure of a respondent.** Blanking the respondent row leaves their address sitting in the invite list. If we store the matched invited-address id (§5), erasure can delete or blank that row too. Whether it should is a question for whoever owns the data-protection position.
- **Cloning a project** should copy the address-check settings and not the invited addresses.
- **Logging.** Counts and ids only; never an address or a postcode in a log line. `censor_pii` will not catch an address in free text.
- **`docs/personal-data.md`** needs a section on the invite list when this is built.

---

## 12. Questions for the team

About how the check is used today:

1. In past projects, roughly what share of respondents came out as `CHECK`, and what share of those ended up `BAD`? (§10 would answer this properly.)
2. How big is a typical invite list, and what does the file from the mailing house look like — which columns, one address column or several, any identifier per address?
3. What are reviewers actually doing when they resolve a `CHECK`? Which cases are quick and which are painful?
4. What is `BAD` in practice — mostly people who heard about it from a neighbour, mostly typos, mostly spam?
5. Does this need to work outside the UK from the start? Hungary and Australia change the candidate-set sizes considerably (§3).

About the design:

6. Target or filter (§6)? I recommend a filter.
7. Should a selection be blocked while `CHECK`s remain, or exclude them and warn (§6)?
8. Who may review — assembly managers only, or confirmation callers too (§8)?
9. If a respondent's address is edited after a human decision, is the decision cleared (§5)?
10. Second mailings: is "upload the combined list again" acceptable, or is adding to a list needed (§4)?
11. How long is the invite list kept, and does erasing a respondent remove their invited address (§11)?
12. Has a code on the letter been considered (§9)?
13. Where does the set-up live in the interface, and what are `OK` / `CHECK` / `BAD` called there (§7, §8)?

Things I still need to check in the code, not questions for the team:

- Whether any database project already has an `address_check` attribute or target that a reserved name would collide with (§5).
- Whether question keys can be renamed, and what follows them when they are (§7).
- The actual spreadsheet formulas, against the Gemini description (§2).

---

## 13. A possible order of work

Not a plan — just the dependencies as I see them, to help the team discussion.

1. **Measure** on past spreadsheets (§10). Independent of everything else.
2. **Matcher** as pure domain code with a table of test cases. No database, no UI; could be written and reviewed before any design question is settled, and is what step 1 runs.
3. **Invited-address table, upload and settings.**
4. **Result storage and the four write paths, plus whole-pool recheck.**
5. **The selection gate** — possibly preceded by pulling the "available for selection" rule into one place.
6. **Review screen, list filter, counts on the Selection tab.**
7. **Export/import, clone, erasure, retention, documentation.**

Steps 3 to 7 are where the decisions in §12 bite.
