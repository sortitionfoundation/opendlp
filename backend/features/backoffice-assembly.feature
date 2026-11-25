Feature: Backoffice Assembly Management
  As an administrator
  I want to manage assemblies
  So that I can create, view, and edit assembly details.

  # Assembly Details Page Tests

  Scenario: User can navigate to assembly details from dashboard
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the backoffice dashboard
    And I click the "Go to Assembly" button for "Climate Assembly"
    Then I should see the assembly details page
    And I should see "Climate Assembly" as the page heading

  Scenario: Assembly details page displays assembly information
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly" with question "How should we address climate change?"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see "Basic details" as a section heading
    And I should see "How should we address climate change?"
    And I should see "Status"
    And I should see "Panel size"
    And I should see "Created"

  # Editing a project's details is in project-details.feature

  # Archiving

  Scenario: A project manager archives a project and unarchives it
    Given I am logged in as a normal user
    And there is an assembly called "Riverside Panel" created by admin
    And I am assigned to "Riverside Panel" as "assembly-manager"
    When I visit the assembly details page for "Riverside Panel"
    And I archive the project
    Then I should see "Project archived"
    And I should see "This project is archived. It doesn't appear in project lists."
    When I visit the backoffice dashboard
    Then I should not see "Riverside Panel"
    When I click the "Archived projects" button
    Then I should see an assembly card with title "Riverside Panel"
    When I click the "Go to Assembly" button for "Riverside Panel"
    And I unarchive the project
    Then I should see "Project unarchived"
    And I should not see "This project is archived."
    When I visit the backoffice dashboard
    Then I should see an assembly card with title "Riverside Panel"

  # Creating a project is in create-project.feature

  Scenario: Dashboard displays create assembly button
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    Then I should see the "Create project" button

  Scenario: Empty state shows create assembly button
    Given I am logged in as an admin user
    And there are no assemblies
    When I visit the backoffice dashboard
    Then I should see "No projects yet"
    And I should see the "Create your first project" button

  # Update Number to Select (from Selection Page)

  Scenario: User can update number to select from selection page
    Given I am logged in as an admin user
    And there is an assembly called "Selection Test Assembly" with number to select "25"
    And the assembly "Selection Test Assembly" has a gsheet configuration
    When I visit the selection page for "Selection Test Assembly"
    And I click the "Edit" link next to number to select
    And I fill in the number to select with "50"
    And I click the "Save" button
    Then I should be on the selection page for "Selection Test Assembly"
    And I should see "updated"
    And the number to select should be "50"

  Scenario: User dismisses the edit number modal without saving
    Given I am logged in as an admin user
    And there is an assembly called "Dismiss Number Assembly" with number to select "25"
    And the assembly "Dismiss Number Assembly" has a gsheet configuration
    When I visit the selection page for "Dismiss Number Assembly"
    And I click the "Edit" link next to number to select
    And I close the edit number modal
    Then the edit number modal is no longer shown
    And I should be on the selection page for "Dismiss Number Assembly"
    And the number to select should be "25"
