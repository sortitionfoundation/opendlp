Feature: Export respondents
  As an assembly organiser
  I want to export the respondents of an assembly
  So that I can work with their data outside OpenDLP.

  Scenario: Organiser exports respondents to CSV
    Given there is an assembly with respondents ready to export called "Export Demo"
    And I am signed in as an admin user
    When I open the respondents page for "Export Demo"
    And I open the export modal
    Then a CSV download starts when I run the export
    And the downloaded CSV contains the respondent ids

  Scenario: Organiser dismisses the export modal
    Given there is an assembly with respondents ready to export called "Dismiss Demo"
    And I am signed in as an admin user
    When I open the respondents page for "Dismiss Demo"
    And I open the export modal
    And I dismiss the export modal with the Cancel button
    Then the export modal is no longer visible

  Scenario: Keyboard focus follows the export modal in and back out
    Given there is an assembly with respondents ready to export called "Export Focus Demo"
    And I am signed in as an admin user
    When I open the respondents page for "Export Focus Demo"
    And I open the export modal
    Then keyboard focus should be inside the export modal
    And the page behind the export modal should be out of reach
    When I press Escape
    Then the export modal is no longer visible
    And keyboard focus should be on the Export button
    And the page behind the export modal should be back in reach

  Scenario: Organiser stops the automatic export
    Given there is an assembly with respondents ready to export called "Auto Export Demo"
    And the respondents of "Auto Export Demo" are automatically exported to Google Sheets
    And I am signed in as an admin user
    When I open the respondents page for "Auto Export Demo"
    Then the page says the respondents are automatically exported
    When I press the button to stop the automatic export
    Then the page says the automatic export has stopped
    And the page no longer offers to stop the automatic export
