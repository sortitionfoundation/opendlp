Feature: Backoffice registration HTML editor
  As an assembly organiser
  I want the registration form HTML field to have syntax highlighting and auto-indent
  So that hand-writing registration HTML is easier and less error-prone

  Scenario: The registration form HTML field is enhanced into a code editor
    Given I am logged in as an admin user
    And there is an assembly called "Editor Assembly" with a registration page
    When I visit the registration form editor for "Editor Assembly"
    Then the HTML content field should be a mounted code editor

  Scenario: Editing the HTML in the code editor and saving persists the content
    Given I am logged in as an admin user
    And there is an assembly called "Roundtrip Assembly" with a registration page
    When I visit the registration form editor for "Roundtrip Assembly"
    And I type "ROUNDTRIP-MARKER-4931" into the HTML content code editor
    And I save the registration form
    Then the saved registration HTML should contain "ROUNDTRIP-MARKER-4931"

  Scenario: The form skeleton preview is shown in a read-only code editor
    Given I am logged in as an admin user
    And there is an assembly called "Skeleton Assembly" with a registration page
    When I visit the registration form editor for "Skeleton Assembly"
    And I open the form skeleton preview
    Then the form skeleton should be shown in a read-only code editor
