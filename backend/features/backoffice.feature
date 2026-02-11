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
    Then I should see the brand-400 primary action token box
    And the brand-400 token box should have the brand crimson background
    And I should see the brand-300 secondary token box
    And the brand-300 token box should have the brand red background

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
    Then the primary button should have the brand crimson background
    And the secondary button should have the brand red background
    And the disabled button should be disabled

  Scenario: Card component variants are displayed
    Given I am on the backoffice showcase page
    Then I should see the basic card
    And I should see the card with header
    And I should see the card with actions
    And the card with actions should contain buttons

  # Typography Tests

  Scenario: Typography section is visible in showcase
    Given I am on the backoffice showcase page
    Then I should see the typography section
    And I should see "Semantic Tokens"
    And I should see "Use Cases"

  Scenario: Display typography uses Oswald font
    Given I am on the backoffice showcase page
    Then the display-lg sample should use the Oswald font
    And the display-lg sample should have font size 32px
    And the display-md sample should use the Oswald font
    And the display-md sample should have font size 28px

  Scenario: Heading typography uses Oswald font
    Given I am on the backoffice showcase page
    Then the heading-lg sample should use the Oswald font
    And the heading-lg sample should have font size 20px

  Scenario: Body typography uses Lato font
    Given I am on the backoffice showcase page
    Then the body-lg sample should use the Lato font
    And the body-lg sample should have font size 16px

  Scenario: Overline typography is uppercase with Lato font
    Given I am on the backoffice showcase page
    Then the overline sample should use the Lato font
    And the overline sample should be uppercase

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

  # Navigation Component Tests

  Scenario: Navigation component is displayed
    Given I am on the backoffice showcase page
    Then I should see the navigation component
    And the navigation should contain the logo
    And the navigation should contain nav links
    And the navigation should contain the CTA button

  # Button Link Variant Tests

  Scenario: Button with href renders as anchor tag
    Given I am on the backoffice showcase page
    Then I should see the link button
    And the link button should be an anchor tag

  # Footer Component Tests

  Scenario: Dashboard displays footer with links and version
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    Then I should see the footer
    And the footer should contain GitHub link
    And the footer should contain Sortition Foundation link
    And the footer should contain User Data Agreement link
    And the footer should display the version
