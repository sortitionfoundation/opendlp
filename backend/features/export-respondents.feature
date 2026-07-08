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
