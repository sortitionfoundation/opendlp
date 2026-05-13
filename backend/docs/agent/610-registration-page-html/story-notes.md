Acceptance Criteria:

Assembly manager can paste in HTML, it will be served at a URL the user chooses.

## Scope

- "registration" tab in assembly, in it you can:
- choose URL and short URL
- QR code (based on short URL) - show on page, have button to download image (to use in paper invites)
- put HTML in a text box and save it
- inline CSS and `<style>` tags allowed
- publish/unpublish
  - when published, it is live
  - when not published
    - default is redirect to generic "Registration is Closed" page
    - the page is only visible with token
- basic templating for CSRF token, form action
  - `{{ csrf_form_element }}` and `<form action="{{ form_url }}" ...>` and the like
  - required input fields listed as templates
- images via static URL on other server
- thank you for registering page - second HTML-in-textbox

### Open question

any?

## Consider - if not too expensive to do

- produce complete unstyled form HTML below the text box that they could take and edit/style
- encourage gov.uk design system
- docs, examples ...
- auto-checking that the form will be accepted
  - could be, check that all the required template bits are present
- auto-check for broken HTML

## Out of scope

- bot protection - see sc-614
- javascript support
- rich text editor, splitting the edits into intro and form, ...
- upload image to our server - see sc-672
- auto-reply email template - see sc-615
- auto publish/unpublish on dates - see sc-673
- processing the form submission - see sc-613
- admin interface to see URL/short-URL for all assemblies
- multiple registration forms for one assembly
- registration form translations
- list all open registration pages - see sc-674

## Notes

It's an early version behind a feature flag. First used for testing and later can be used as part of the system

Can be a plain text box where you can paste html and inline css, or could be a rich text editor that saves HTML (like the nationbuilder HTML editor).

Note that "raw" does not mean "ugly". It means that the user is editing raw HTML (and CSS).

### Data notes

Data model

- RegistrationPage model
  - methods
    - `get_html()` to fetch HTML
    - `get_url()` and `get_short_url()`
    - stuff to get the stuff that will be used for the template items above - csrf token etc - or maybe this is a service layer thing. Or ...
  - fields
    - link to Assembly
    - type - plainHtml, template, ...
    - url_slug
    - short_url_slug
    - is_published
    - token - auto-generated - used to view the page when not published
- RegistrationHTML model
  - fields
    - link to RegistrationPage
    - the HTML
- RegistrationPostPage
  - holds the info for the "thank you" page you see after successful registration
  - fields
    - link to RegistrationPage
    - HTML for thank you page
- UploadedImage
  - fields
    - path on filesystem
    - filename
  - method
    - url() - get the URL it will be served at

## Notes from an earlier discussion

- can anybody do it?
  - for version 1, just have it enabled for all assemblies, any assembly manager can set up the registration page
- how much HTML is editable
  - agreed that we will set the `<head>` and a little bit of the `<body>` - probably a footer like the current registration page
- short URL? automatically generated or typed in by the user?
  - agreed - typed in by the user
  - QR codes can be shown automatically
- can we set the URL before we create the form - so that it can be included in the invites before the registration page actually exists
  - from data point of view - yes
  - UX
    - go to Registration tab and you can set the URL and some other bits without creating the page itself.
    - have the URL on an earlier page of "assembly settings"
    - or both - but stored in the same place in the database
- preview questions
  - is preview just looking at it? or can you submit the form and see the results in the Respondents tab?
    - you can submit the form
    - flag respondents who were entered when the form was not properly published. New selection-state of "test-submission"
  - how to get to preview page, when not published - i.e. how to avoid going to the "Registration Closed" page?
    - the preview URL will be `/r/url-slug?preview=<token>`
- can you edit while the page is published? For MVP, just have a warning. That allows fixing typos, broken links etc.
