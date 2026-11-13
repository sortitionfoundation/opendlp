Feature: Create a project in a dialog
  As an organiser
  I want to create a project in a few short steps
  So that I can say where its data lives without leaving the page I am on.

  Background:
    Given I am logged in as an admin user
    And there are no projects
    And I am on the list of my projects

  Scenario: The create button opens the dialog at its first step
    When I open the create project dialog
    Then the create project dialog is at the step "Project details"
    And focus is on the project title
    And the page behind the dialog is still the list of my projects

  Scenario: Creating a project and deciding about its data later
    When I open the create project dialog
    And I give the project the title "Decide Later Panel"
    And I move on to the next step
    Then the create project dialog is at the step "Data location"
    And the data location is "In OpenDLP"
    When I move on to the next step
    Then the create project dialog is at the step "Targets and people"
    And the target data source is "Decide later"
    And the respondents data source is "Decide later"
    When I save the create project dialog
    Then I am on the details page of "Decide Later Panel"
    And I am told the project was created

  Scenario: A title is needed before moving on
    When I open the create project dialog
    And I move on to the next step
    Then the create project dialog is at the step "Project details"
    And the project title is marked as required

  Scenario: Going back keeps what was typed
    When I open the create project dialog
    And I give the project the title "Kept Through Back"
    And I move on to the next step
    And I choose the data location "In Google Sheets"
    And I move on to the next step
    And I go back a step
    Then the data location is "In Google Sheets"
    When I go back a step
    Then the project title reads "Kept Through Back"

  Scenario: Cancelling asks before discarding and leaves no project
    When I open the create project dialog
    And I give the project the title "Never Made"
    And I cancel the create project dialog
    Then I am asked whether to discard my changes
    When I discard my changes
    Then I am on the list of my projects
    And there is no project called "Never Made"

  Scenario: Escape on an untouched dialog just closes it
    When I open the create project dialog
    And I press Escape
    Then I am on the list of my projects
    And the create project dialog is closed

  Scenario: The CSV panels follow the two dropdowns
    When I open the create project dialog
    And I give the project the title "Panels Follow Choices"
    And I move on to the next step
    And I move on to the next step
    Then I cannot see where to upload targets
    And I cannot see where to upload respondents
    When I choose the target data source "Import from CSV"
    Then I can see where to upload targets
    And I cannot see where to upload respondents
    When I choose the respondents data source "Import from CSV"
    Then I can see where to upload respondents

  Scenario: Uploading a CSV creates the project and locks the earlier steps
    When I open the create project dialog
    And I give the project the title "Made By Upload"
    And I move on to the next step
    And I move on to the next step
    And I choose the target data source "Import from CSV"
    And I upload the example targets
    Then the dialog says "4 targets uploaded"
    And there is a project called "Made By Upload"
    And I cannot go back a step
    And the dialog offers "Close" instead of "Cancel"
    When I choose the respondents data source "Import from CSV"
    And I upload the example respondents
    Then the dialog says "100 respondents uploaded"
    When I save the create project dialog
    Then I am on the details page of "Made By Upload"
    And I am told the project was created

  Scenario: A file that is refused creates no project
    When I open the create project dialog
    And I give the project the title "Refused File"
    And I move on to the next step
    And I move on to the next step
    And I choose the target data source "Import from CSV"
    And I upload the example respondents as targets
    Then the dialog says "CSV import failed"
    And there is no project called "Refused File"
    And I can go back a step

  Scenario: Creating a project managed in Google Sheets
    When I open the create project dialog
    And I give the project the title "Sheet Panel"
    And I move on to the next step
    And I choose the data location "In Google Sheets"
    And I move on to the next step
    Then I can see the Google Sheets settings
    And I cannot see the target data source
    When I give the spreadsheet URL "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    And I choose the team "UK Team"
    Then I cannot see the custom column settings
    When I save the create project dialog
    Then I am on the details page of "Sheet Panel"
    And I am told the project was created

  Scenario: A spreadsheet URL that is not one is refused in the dialog
    When I open the create project dialog
    And I give the project the title "Bad Sheet"
    And I move on to the next step
    And I choose the data location "In Google Sheets"
    And I move on to the next step
    And I give the spreadsheet URL "https://example.com/not-a-sheet"
    And I choose the team "UK Team"
    And I save the create project dialog
    Then the create project dialog is at the step "Targets and people"
    And the spreadsheet URL is marked as refused
    And there is no project called "Bad Sheet"
