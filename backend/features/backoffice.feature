Feature: Backoffice Dashboard
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

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

  Scenario: Dashboard displays footer with links and version
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    Then I should see the footer
    And the footer should contain GitHub link
    And the footer should contain Sortition Foundation link
    And the footer should contain User Data Agreement link
    And the footer should display the version
