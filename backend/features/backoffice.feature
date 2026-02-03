Feature: Backoffice UI
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

  Scenario: View component showcase page
    Given I am on the backoffice showcase page
    Then I should see "Component Showcase"
    And I should see "Alpine.js Interactivity"
    And I should see "Primitive Tokens"

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

  Scenario: Card component variants are displayed
    Given I am on the backoffice showcase page
    Then I should see the basic card
    And I should see the card with header
    And I should see the card with actions
    And the card with actions should contain buttons

  # Dashboard Tests (Protected Route)

  Scenario: Unauthenticated user is redirected to login
    Given I am not logged in
    When I try to access the backoffice dashboard
    Then I should be redirected to the login page

  Scenario: Authenticated user can view backoffice dashboard
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    Then I should see "Dashboard"
    And I should see "Welcome back"

  Scenario: Dashboard displays assemblies using card components
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the backoffice dashboard
    Then I should see an assembly card with title "Climate Assembly"
