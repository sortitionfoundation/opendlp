Feature: Backoffice UI
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

  Scenario: View backoffice hello page
    Given I am on the backoffice hello page
    Then I should see "Hello from Backoffice!"
    And I should see "Pines UI + Tailwind CSS"
