# Future work: an organiser BDD scenario fails when run on its own

Spotted on `767-rich-text-autoreply`, and not caused by that branch: it fails
the same way on `f00fecfe`, before the branch's work. Written to be pasted into
an issue.

## Problem

```
CI=true uv run pytest tests/bdd/test_backoffice.py -k colleague_to_their_own_assembly_by_exact_email
FAILED ... AssertionError: Locator expected to contain text 'normal@opendlp.example'
```

The scenario in `features/organiser-assemblies.feature`:

```gherkin
Scenario: An organiser adds a colleague to their own assembly by exact email
  Given I am logged in as an organiser
  And there is an assembly called "Lilliput Housing Assembly" created by the organiser
  When I visit the assembly members page for "Lilliput Housing Assembly"
  Then I should see "Add User to Assembly"
  When I type "normal@opendlp.example" into the user search dropdown
  Then I should see "normal@opendlp.example" in the search results
```

It searches for the standard normal user, but none of its steps asks for that
user to exist. The user is made by the `normal_user` fixture in
`tests/bdd/conftest.py`, which is session-scoped and only runs when a scenario
requests it, for example through "I am logged in as a normal user". So:

- **In the full run** an earlier scenario has already requested `normal_user`.
  `delete_all_except_standard_users` keeps the admin, normal and organiser
  users between scenarios, so the user is still there and the scenario passes.
- **Run on its own**, or first after a change to the scenario order, nothing
  has made the user. The search correctly finds nothing, and the scenario
  fails.

The scenario depends on test order, so it can fail on a filtered run, under
`pytest -k`, or if the suite is ever randomised or split across workers.

The scenario after it, "An organiser cannot fish for accounts with a partial
address", has the matching problem the other way round. It types "normal"
and expects "No results found". Run on its own, there is no normal user to
find, so it passes **even if partial matching were broken**, which is the very
thing it exists to catch.

## Possible fixes

- Make the setup explicit: a step such as
  `And there is a user "normal@opendlp.example"` that requests `normal_user`,
  added to both scenarios as a `Given`. This is the clearest, because the
  scenario then says what it relies on.
- Or have the search steps (`type_into_search_dropdown`, or the two `Then`
  steps) take the `normal_user` fixture, so the user always exists. This is
  smaller, but hides the dependency inside the step code.

Either way, check the fix by running each of the two scenarios on its own, and
check the partial-address scenario would fail if the search matched
partially, for example by temporarily searching for the full address in it.
