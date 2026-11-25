# Future work: the BDD features still say "assembly" where the interface says "project"

Left over from sc-1341, retiring the legacy signed-in pages (2026-11-25).
Written to be pasted into an issue.

## Problem

The interface was renamed from "assembly" to "project" (sc-1000), and the
legacy pages that still said "assembly" are gone. The older feature files were
converted to drive the backoffice pages without changing a word of their
Gherkin, so they describe a product that no longer uses their vocabulary:

| Feature file | Step file | What it says |
| --- | --- | --- |
| `create-assembly.feature` | `tests/bdd/test_assembly_crud.py` | "the user is creating an assembly", "the user should see the created assembly" |
| `update-assembly.feature` | same | "the user starts editing the assembly" |
| `view-assembly.feature` | same | "the user sees the assembly", `the "title" of the Assembly` |
| `view-assembly-list.feature` | same | "there are 2 assemblies in the system", `the message "No assemblies"` |
| `admin-users.feature` | `tests/bdd/test_admin_users.py` | "the admin adds them to the assembly", "the non-admin user cannot see the assembly" |
| `selection.feature` | `tests/bdd/test_selection_manual_gsheet.py`, `tests/bdd/test_selection_db.py` | "the assembly is set up", "I open the Assembly" |
| `organiser-assemblies.feature`, `backoffice-assembly.feature`, `backoffice-assembly-members.feature` | `tests/bdd/test_backoffice.py` | file names and steps |

`the user sees the message "No assemblies"` is the sharpest case: the step
asserts the page says "No projects yet", so the quoted text in the feature is
not what is on the screen.

## What to do

Reword the steps, and rename the feature and step files, to "project". Two
things make it more than a search and replace:

- `selection.feature` is run by two step files, so a step's text has to change
  in the feature and in both at once.
- `tests/bdd/shared/ui_shared.py` holds steps used by several features
  (`there is an assembly created`); changing one means changing every feature
  that uses it in the same commit.

The domain still calls the thing an `Assembly`, and so do the fixtures
(`assembly_creator`). Those stay: [docs/language.md](../../language.md) is
about what the interface says, and the feature files are a description of the
interface.

Some of these features overlap with newer ones written against the backoffice
from the start (`create-project.feature`, `project-details.feature`). Check
each scenario for a newer twin before rewording it; a duplicate is better
deleted than renamed.
