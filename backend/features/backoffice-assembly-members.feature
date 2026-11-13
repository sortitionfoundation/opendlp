Feature: Backoffice Assembly Team Members
  As an administrator
  I want to manage assembly team members
  So that I can control who has access to each assembly.

  # Adding, changing a role and removing are in project-details.feature. These
  # are about who sees what on the Team card, and where old links go.

  Scenario: The old Team Members address lands on the Team card
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly members page for "Climate Assembly"
    Then I should see the assembly details page
    And I should see "Team" as a section heading

  Scenario: Admin can open the add a team member dialog from the Team card
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see the "Add a team member" button
    When I open the add a team member dialog
    Then I should see the user search dropdown
    And I should see the team role dropdown

  Scenario: Admin can see team members table when members exist
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    And "normal@opendlp.example" is assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see the team members table
    And the team members table should show "normal@opendlp.example"
    And the team members table should show role "Project manager"
    And I should see remove buttons in the team members table

  Scenario: Non-admin member can view the team
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    And I am assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see "Team" as a section heading
    And I should see the team members table

  Scenario: Assembly manager can add a team member
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    And I am assigned to "Climate Assembly" as "assembly-manager"
    When I visit the assembly details page for "Climate Assembly"
    And I open the add a team member dialog
    Then I should see the user search dropdown

  Scenario: Non-manager member cannot add or remove team members
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    And I am assigned to "Climate Assembly" as "confirmation-caller"
    When I visit the assembly details page for "Climate Assembly"
    Then I should not see "Add a team member"
    And I should not see remove buttons in the team members table

  Scenario: Search dropdown shows no results message when typing
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    And I open the add a team member dialog
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
    And I should see "You don't have permission to view this project"

  Scenario: Non-admin user without assembly role cannot reach the team through its old address
    Given I am logged in as a normal user
    And there is an assembly called "Climate Assembly" created by admin
    When I try to access the assembly members page for "Climate Assembly"
    Then I should be redirected to the dashboard
    And I should see "You don't have permission to view this project"
