# Future work: the search dropdown never shows "No results found"

Spotted while fixing the organiser search BDD scenarios. Written to be pasted
into an issue.

## Problem

`templates/backoffice/components/search_dropdown.html` has a visible
"No results found" message, shown when
`results.length === 0 && !isLoading && query.length >= min_chars`. But it sits
inside the results container, which has `x-show="isOpen"`, and
`src/js/components/autocomplete.js` sets `isOpen = data.length > 0`. The two
conditions cannot both hold, so a sighted user who searches for something that
matches nothing sees the dropdown close and no message at all.

Screen reader users are told: the component's `aria-live` region announces
"No results found".

The BDD step `I should see "{text}" after searching` used to check the page
body, which always contains the hidden message, so it passed whatever the
search found. It now checks the live region instead, which is why the BDD
suite did not catch this.

## Possible fixes

- Open the dropdown when a search completes with no results (`isOpen = true`
  once a fetch returns), and let the existing `x-show` on the message decide
  what is inside it.
- Or move the message outside the `isOpen` container.

Either way, add a vitest case in `autocomplete.test.js` and a BDD assertion
that the message is *visible*, not merely present.
