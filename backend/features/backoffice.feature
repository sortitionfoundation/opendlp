Feature: Backoffice UI
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

  Scenario: View component showcase page
    Given I am on the backoffice showcase page
    Then I should see "Component Showcase"
    And I should see "Alpine.js Interactivity"
    And I should see "Design Tokens"

  Scenario: Design tokens are loaded and working
    Given I am on the backoffice showcase page
    Then I should see the primary token box
    And the primary token box should have the brand orange background
    And I should see the secondary token box
    And the secondary token box should have the brand plum background

  Scenario: Alpine.js toggle button works
    Given I am on the backoffice showcase page
    Then the Alpine message should be hidden
    When I click the Alpine toggle button
    Then the Alpine message should be visible
    And I should see "Alpine.js is working!"
    When I click the Alpine toggle button
    Then the Alpine message should be hidden

  Scenario: Button component variants are displayed
    Given I am on the backoffice showcase page
    Then I should see the primary button
    And I should see the secondary button
    And I should see the outline button
    And I should see the disabled button

  Scenario: Button component uses correct design tokens
    Given I am on the backoffice showcase page
    Then the primary button should have the brand orange background
    And the secondary button should have the brand plum background
    And the disabled button should be disabled
