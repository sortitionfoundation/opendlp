Feature: Backoffice UI
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

  Scenario: View backoffice hello page
    Given I am on the backoffice hello page
    Then I should see "Hello from Backoffice!"
    And I should see "Pines UI + Tailwind CSS"

  Scenario: Tailwind CSS is loaded and working
    Given I am on the backoffice hello page
    Then I should see the Tailwind test box
    And the Tailwind test box should have a blue background

  Scenario: Design tokens are loaded and working
    Given I am on the backoffice hello page
    Then I should see the primary token box
    And the primary token box should have the brand orange background
    And I should see the secondary token box
    And the secondary token box should have the brand plum background
