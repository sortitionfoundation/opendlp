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

  # Selection Tab Tests

  Scenario: User can navigate to selection tab from assembly details
    Given I am logged in as an admin user
    And there is an assembly called "Selection Test Assembly"
    When I visit the assembly details page for "Selection Test Assembly"
    And I click the "Selection" tab
    Then I should see the assembly selection page
    And I should see "Selection Test Assembly" as the page heading

  Scenario: Selection tab displays breadcrumbs
    Given I am logged in as an admin user
    And there is an assembly called "Selection Test Assembly"
    When I visit the assembly selection page for "Selection Test Assembly"
    Then I should see the breadcrumbs
    And the breadcrumbs should contain "Dashboard"
    And the breadcrumbs should contain "Selection Test Assembly"
    And the breadcrumbs should contain "Selection"

  Scenario: Selection tab shows warning when no gsheet configured
    Given I am logged in as an admin user
    And there is an assembly called "Selection No GSheet Assembly"
    When I visit the assembly selection page for "Selection No GSheet Assembly"
    Then I should see "Please use the Data tab to tell us about your data"
    And I should see the "Configure Data Source" button
    And I should not see "Initial Selection"

  Scenario: Selection tab shows selection cards when gsheet configured
    Given I am logged in as an admin user
    And there is an assembly called "Selection With GSheet Assembly"
    And the assembly "Selection With GSheet Assembly" has a gsheet configuration
    When I visit the assembly selection page for "Selection With GSheet Assembly"
    Then I should see "Initial Selection"
    And I should see "Replacement Selection"
    And I should see "Manage Generated Tabs"
    And I should see "Number to select:"

  Scenario: User can edit number to select from selection tab
    Given I am logged in as an admin user
    And there is an assembly called "Edit Number Assembly" with number_to_select 50
    And the assembly "Edit Number Assembly" has a gsheet configuration
    When I visit the assembly selection page for "Edit Number Assembly"
    Then I should see "Number to select:"
    And I should see "50"
    When I click the "Edit" link
    Then I should see "Edit Number to Select"
    When I fill in "number_to_select" with "75"
    And I click the "Save" button
    Then I should see "Number to select updated to 75"
    And I should see "75"

  Scenario: Selection tab is accessible from all assembly tabs
    Given I am logged in as an admin user
    And there is an assembly called "Selection Tab Navigation Assembly"
    When I visit the assembly data page for "Selection Tab Navigation Assembly"
    And I click the "Selection" tab
    Then I should see the assembly selection page

  Scenario: Non-admin user without assembly role cannot access selection page
    Given I am logged in as a normal user
    And there is an assembly called "Selection Unauthorized Assembly" created by admin
    When I try to access the assembly selection page for "Selection Unauthorized Assembly"
    Then I should be redirected to the dashboard
    And I should see "You don't have permission to view this assembly"
