Feature: Backoffice UI
  As an administrator
  I want to access the backoffice interface
  So that I can manage the platform with a modern UI.

  Scenario: View component showcase page
    Given I am on the backoffice showcase page
    Then I should see "Design System"
    And I should see "Alpine.js Interactivity"
    And I should see "Primitive Tokens"

  Scenario: Design tokens are loaded and working
    Given I am on the backoffice showcase page
    And I select the "Foundations" tab
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

  # Assembly Members Page Tests

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

  # Google Sheet Configuration Tests

  Scenario: User can navigate to data tab from assembly details
    Given I am logged in as an admin user
    And there is an assembly called "Data Test Assembly"
    When I visit the assembly details page for "Data Test Assembly"
    And I click the "Data" tab
    Then I should see the assembly data page
    And I should see "Data Source"

  Scenario: Data source selector is shown when no config exists
    Given I am logged in as an admin user
    And there is an assembly called "Data Test Assembly"
    When I visit the assembly data page for "Data Test Assembly"
    Then I should see the data source selector
    And the data source selector should be enabled

  Scenario: User can select Google Spreadsheet data source
    Given I am logged in as an admin user
    And there is an assembly called "Data Test Assembly"
    When I visit the assembly data page for "Data Test Assembly"
    And I select "Google Spreadsheet" from the data source selector
    Then I should see "Google Spreadsheet Configuration"
    And I should see the gsheet URL input field

  Scenario: User can create new gsheet configuration
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Create Assembly"
    When I visit the assembly data page for "GSheet Create Assembly" with source "gsheet"
    And I fill in the gsheet URL with "https://docs.google.com/spreadsheets/d/1234567890/edit"
    And I uncheck the "Check Same Address" checkbox
    And I click the "Save Configuration" button
    Then I should see "created successfully"
    And I should see the gsheet configuration in view mode

  Scenario: Form shows validation errors for missing URL
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Validation Assembly"
    When I visit the assembly data page for "GSheet Validation Assembly" with source "gsheet"
    And I uncheck the "Check Same Address" checkbox
    And I click the "Save Configuration" button
    Then I should see validation error for missing URL

  Scenario: Form shows validation errors for invalid URL
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Invalid URL Assembly"
    When I visit the assembly data page for "GSheet Invalid URL Assembly" with source "gsheet"
    And I fill in the gsheet URL with "not-a-valid-url"
    And I click the "Save Configuration" button
    Then I should see "Invalid URL"

  Scenario: User sees readonly view when config exists
    Given I am logged in as an admin user
    And there is an assembly called "GSheet View Assembly"
    And the assembly "GSheet View Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet View Assembly" with source "gsheet"
    Then I should see the gsheet configuration in view mode
    And the gsheet URL input field should be readonly
    And I should see the "Edit Configuration" button

  Scenario: User can click Edit to switch to edit mode
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Edit Mode Assembly"
    And the assembly "GSheet Edit Mode Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Edit Mode Assembly" with source "gsheet"
    And I click the "Edit Configuration" button
    Then I should see the gsheet configuration in edit mode
    And the gsheet URL input field should be editable

  Scenario: User can update existing configuration
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Update Assembly"
    And the assembly "GSheet Update Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Update Assembly" with source "gsheet" and mode "edit"
    And I fill in the gsheet URL with "https://docs.google.com/spreadsheets/d/new-id-9999/edit"
    And I click the "Save Configuration" button
    Then I should see "updated successfully"
    And I should see the gsheet configuration in view mode

  Scenario: User can cancel edit and return to view mode
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Cancel Assembly"
    And the assembly "GSheet Cancel Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Cancel Assembly" with source "gsheet" and mode "edit"
    And I click the gsheet form cancel link
    Then I should see the gsheet configuration in view mode

  Scenario: Data source selector is locked when config exists
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Locked Assembly"
    And the assembly "GSheet Locked Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Locked Assembly"
    Then the data source selector should be disabled
    And I should see "Data source is locked"

  Scenario: User can delete configuration with confirmation
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Delete Assembly"
    And the assembly "GSheet Delete Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Delete Assembly" with source "gsheet"
    And I click the "Delete" button and confirm
    Then I should see "removed successfully"
    And the data source selector should be enabled

  Scenario: After delete data source selector is unlocked
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Unlock Assembly"
    And the assembly "GSheet Unlock Assembly" has a gsheet configuration
    When I visit the assembly data page for "GSheet Unlock Assembly" with source "gsheet"
    And I click the "Delete" button and confirm
    Then the data source selector should be enabled
    And I should see "Select Data Source"
