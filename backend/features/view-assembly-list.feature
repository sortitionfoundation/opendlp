Feature: View Assembly List.
  As an Assembly Manager
  I want to be able to see all assemblies I have access to
  So that I can see statuses, and interact with the one I want.

  Scenario: List page with no assemblies
    Given there are 0 assemblies in the system
    When the user sees the list of assemblies
    Then the user sees the message "No assemblies"

  Scenario: List page with assemblies
    Given there are 2 assemblies in the system
    When the user sees the list of assemblies
    Then the user sees the title of both assemblies
