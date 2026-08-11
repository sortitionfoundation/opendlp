Feature: Service layer documentation console
  As a developer testing a service by hand
  I want the service docs console to execute services and show me the response
  So that I can exercise the service layer without writing a script for it

  The console's Alpine component moved out of a 722-line inline <script> - the last one
  in the repo - into src/js/components/service-docs/, configured by a JSON data block
  carrying dev.py's own service-name map. Component tests cover the markup, the data
  block and that every bound method exists; only a browser can confirm the bundle loads,
  Alpine registers it, and the execute route accepts what it posts.

  Background:
    Given a user is logged in as an admin

  Scenario: The console loads its component from a built bundle
    Given the user is on the service docs console
    Then the console should have no inline script body
    And the console forms should respond to Alpine

  Scenario: Loading a sample fills the form it belongs to
    Given the user is on the service docs console
    When the user loads the respondents CSV sample
    Then the respondents CSV field should hold the sample data

  Scenario: Executing a service shows the response in its own panel
    Given the user is on the service docs assembly tab
    When the user creates an assembly called "Console Created Assembly"
    Then the create assembly panel should show a success response
    And the response should name the assembly that was created

  Scenario: A service that fails shows its error in its own panel, not as a toast
    Given the user is on the service docs emails tab
    When the user asks for an email template that does not exist
    Then the get email template panel should show an error response
