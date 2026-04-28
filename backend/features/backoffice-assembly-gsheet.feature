Feature: Backoffice Assembly Google Sheet Configuration
  As an administrator
  I want to configure Google Spreadsheet data sources for assemblies
  So that I can import targets and people data for selection.

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
