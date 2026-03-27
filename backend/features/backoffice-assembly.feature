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

  Scenario: Assembly details page displays breadcrumbs
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see the breadcrumbs
    And the breadcrumbs should contain "Dashboard"
    And the breadcrumbs should contain "Climate Assembly"

  Scenario: Assembly details page displays assembly information
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly" with question "How should we address climate change?"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see the assembly question section
    And I should see "How should we address climate change?"
    And I should see the assembly details summary
    And I should see "Status"
    And I should see "Number to Select"
    And I should see "Created"

  Scenario: Assembly details page has edit button
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    Then I should see the "Edit Assembly" button

  # Edit Assembly Page Tests

  Scenario: User can navigate to edit assembly from details page
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the assembly details page for "Climate Assembly"
    And I click the "Edit Assembly" button
    Then I should see the edit assembly page
    And I should see "Edit Assembly" as the page heading

  Scenario: Edit assembly page displays breadcrumbs
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the edit assembly page for "Climate Assembly"
    Then I should see the breadcrumbs
    And the breadcrumbs should contain "Dashboard"
    And the breadcrumbs should contain "Climate Assembly"
    And the breadcrumbs should contain "Edit"

  Scenario: Edit assembly page displays form fields
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly" with question "How should we address climate change?"
    When I visit the edit assembly page for "Climate Assembly"
    Then I should see the title input field
    And I should see the question textarea field
    And I should see the first assembly date field
    And I should see the number to select field
    And the title input should contain "Climate Assembly"
    And the question textarea should contain "How should we address climate change?"

  Scenario: Edit assembly page has save and cancel buttons
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the edit assembly page for "Climate Assembly"
    Then I should see the "Save Changes" button
    And I should see the "Cancel" button

  Scenario: User can update assembly details
    Given I am logged in as an admin user
    And there is an assembly called "Climate Assembly"
    When I visit the edit assembly page for "Climate Assembly"
    And I fill in the title with "Updated Climate Assembly"
    And I click the "Save Changes" button
    Then I should see the assembly details page
    And I should see "Updated Climate Assembly" as the page heading
    And I should see "updated successfully"

  # Create Assembly Page Tests

  Scenario: Dashboard displays create assembly button
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    Then I should see the "Create New Assembly" button

  Scenario: User can navigate to create assembly page from dashboard
    Given I am logged in as an admin user
    When I visit the backoffice dashboard
    And I click the "Create New Assembly" button
    Then I should see the create assembly page
    And I should see "Create Assembly" as the page heading

  Scenario: Create assembly page displays breadcrumbs
    Given I am logged in as an admin user
    When I visit the create assembly page
    Then I should see the breadcrumbs
    And the breadcrumbs should contain "Dashboard"
    And the breadcrumbs should contain "Create Assembly"

  Scenario: Create assembly page displays form fields
    Given I am logged in as an admin user
    When I visit the create assembly page
    Then I should see the title input field
    And I should see the question textarea field
    And I should see the first assembly date field
    And I should see the number to select field

  Scenario: Create assembly page has create and cancel buttons
    Given I am logged in as an admin user
    When I visit the create assembly page
    Then I should see the "Create Assembly" button
    And I should see the "Cancel" button

  Scenario: User can create a new assembly
    Given I am logged in as an admin user
    When I visit the create assembly page
    And I fill in the title with "New Test Assembly"
    And I fill in the question with "What should we discuss?"
    And I fill in the number to select with "50"
    And I click the "Create Assembly" button
    Then I should see the assembly details page
    And I should see "New Test Assembly" as the page heading
    And I should see "created successfully"

  Scenario: Empty state shows create assembly button
    Given I am logged in as an admin user
    And there are no assemblies
    When I visit the backoffice dashboard
    Then I should see "No assemblies yet"
    And I should see the "Create Your First Assembly" button

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
