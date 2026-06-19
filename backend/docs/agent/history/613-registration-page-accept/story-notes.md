## Acceptance Criteria:

- when someone clicks "Register" on the form, a Respondent is created in the assembly.
- check form contents against fields - reject if it is invalid
- an assembly manager can publish/unpublish
  - when unpublished
    - normally do temporary redirect to a "registration closed" page
    - a token in the URL is required to be able to view the page and submit it. Any submission produces a Respondent with the new RespondentStatus.RegistrationTest status
    - the URL with the token is shown to users in the web UI

## Scope

- Form endpoint
- check form contents against fields - reject if it is invalid and re-show the form with error context
- check publish/unpublish state
  - if no token, 302 redirect to "registration closed"
  - if token, accept the form but create Respondent with special RegistrationTest
- if form submission is successful, redirect to "thank you" page, using the "thank you" page HTML for this form
  - form success is HTTP 302 to thank-you URL

## Out of scope

- bot protection - need it, but do in another story
- field editing
- dates to publish/unpublish
- QR code

## Technical notes

This means having a web endpoint that will accept a POST request from a compatible form, that will create a Respondent record in the database, for the assembly.

This will mean we'll need to use the "respondent field schema".

Think about what URL it will be on. Let user select, but maybe it is on a public url under `<domain>/register/<reg_name>`

Consider - do GET and POST URLs need to be the same? Is it useful to have multiple forms that hit the same submit/POST URL. Translated forms? A/B testing? Or just have multiple URLs!

Should we now extend the Respondent Field Schema to distinguish fields that are part of the form, derived later, added during confirmation calls ... Select one of the options (map to enum)? Multiple booleans?
