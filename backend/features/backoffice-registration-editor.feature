Feature: Backoffice registration HTML editor
  As an assembly organiser
  I want the registration form HTML field to have syntax highlighting and auto-indent
  So that hand-writing registration HTML is easier and less error-prone

  Scenario: The registration form HTML field is enhanced into a code editor
    Given I am logged in as an admin user
    And there is an assembly called "Editor Assembly" with a registration page
    When I visit the registration form editor for "Editor Assembly"
    Then the HTML content field should be a mounted code editor
