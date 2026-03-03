Feature: Backoffice Assembly Team Members
  As an administrator
  I want to manage assembly team members
  So that I can control who has access to each assembly.

  Scenario: Admin can navigate to assembly members from details page
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    And I click the "Team Members" tab
    Then I should see the assembly members page
    And I should see "Team Members" as a section heading

  Scenario: Assembly members page displays breadcrumbs
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly members page for "Climate Assembly"
    Then I should see the breadcrumbs
    And the breadcrumbs should contain "Dashboard"
    And the breadcrumbs should contain "Climate Assembly"
    And the breadcrumbs should contain "Team Members"

  Scenario: Admin can see add user form on members page
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly members page for "Climate Assembly"
    Then I should see "Add User to Assembly"
    And I should see the user search dropdown
    And I should see the role selection radio buttons
    And I should see the "Add User to Assembly" button

  Scenario: Admin can see team members table when members exist
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    And "normal@opendlp.example" is assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly members page for "Climate Assembly"
    Then I should see the team members table
    And the team members table should show "normal@opendlp.example"
    And the team members table should show role "assembly-manager"
    And I should see remove buttons in the team members table

  Scenario: Non-admin member can view members page
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    And I am assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly members page for "Climate Assembly"
    Then I should see "Team Members" as a section heading
    And I should see the team members table

  Scenario: Non-admin member cannot see add user form
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    And I am assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly members page for "Climate Assembly"
    Then I should not see "Add User to Assembly"
    And I should not see the user search dropdown
    And I should not see remove buttons in the team members table

  Scenario: Search dropdown shows no results message when typing
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly members page for "Climate Assembly"
    And I type "nonexistent" into the user search dropdown
    Then I should see "No results found" after searching

  Scenario: Non-admin user without assembly role cannot see assembly in dashboard
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    When I visit the backoffice dashboard
    Then I should not see "Climate Assembly"

  Scenario: Non-admin user without assembly role cannot access assembly details page
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    When I try to access the assembly details page for "Climate Assembly"
    Then I should be redirected to the dashboard
    And I should see "You don't have permission to view this assembly"

  Scenario: Non-admin user without assembly role cannot access assembly members page
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    When I try to access the assembly members page for "Climate Assembly"
    Then I should be redirected to the dashboard
    And I should see "You don't have permission to view this assembly"
