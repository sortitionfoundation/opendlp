Feature: Frontend patterns reference page
  As a developer writing backoffice interactivity
  I want the patterns page's own examples to actually work
  So that the page we point people at demonstrates the convention rather than contradicting it

  The page's Alpine components moved out of an inline <script> block into
  src/js/backoffice/patterns.js. Component tests cover the markup; only a real
  browser can confirm the bundle loads, registers, and drives the page.

  Background:
    Given a user is logged in as an admin

  Scenario: The patterns page loads its components from a built bundle
    Given the user is on the frontend patterns page
    Then the page should have no inline script body
    And the patterns Alpine components should be registered

  Scenario: The file upload demo reacts to a chosen CSV
    Given the user is on the file upload patterns tab
    When the user chooses a CSV file in the demo
    Then the demo should show the file name and size

  Scenario: The file upload demo rejects a file that is not a CSV
    Given the user is on the file upload patterns tab
    When the user chooses a text file in the demo
    Then the demo should show a file type error
    And the demo should show no file name

  Scenario: Copying a code sample shows a toast
    Given the user is on the frontend patterns page
    When the user clicks the copy button for the urlSelect sample
    Then a toast should appear
