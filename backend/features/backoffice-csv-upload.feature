Feature: Backoffice CSV Upload
  As an administrator
  I want a project's tabs to follow the data it holds
  So that I can only go where there is something to do.

  Scenario: A new project has its Targets tab open and its Respondents tab waiting for data
    Given I am logged in as an admin user
    And there is an assembly called "Tab Test Assembly"
    When I visit the assembly details page for "Tab Test Assembly"
    Then I should see a "Targets" tab in the assembly navigation
    And I should see a "Respondents" tab in the assembly navigation
    And the "Targets" tab should be enabled
    And the "Respondents" tab should be disabled

  Scenario: Targets and Respondents tabs are enabled when gsheet is configured
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Configured Assembly"
    And the assembly "GSheet Configured Assembly" has a gsheet configuration
    When I visit the assembly details page for "GSheet Configured Assembly"
    Then I should see a "Targets" tab in the assembly navigation
    And I should see a "Respondents" tab in the assembly navigation
    And the "Targets" tab should be enabled
    And the "Respondents" tab should be enabled

  Scenario: Targets page shows gsheet info when gsheet source is configured
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Targets Assembly"
    And the assembly "GSheet Targets Assembly" has a gsheet configuration
    When I visit the assembly targets page for "GSheet Targets Assembly"
    Then I should see "Targets are configured in Google Sheets"
    And I should see "Categories"

  Scenario: Respondents page shows gsheet info when gsheet source is configured
    Given I am logged in as an admin user
    And there is an assembly called "GSheet Respondents Assembly"
    And the assembly "GSheet Respondents Assembly" has a gsheet configuration
    When I visit the assembly respondents page for "GSheet Respondents Assembly"
    Then I should see "Respondents are configured in Google Sheets"
    And I should see "Respondents"

  # The upload itself is in the data source dialog: see create-project.feature
  # and project-details.feature.

  Scenario: Targets tab is enabled after targets uploaded
    Given I am logged in as an admin user
    And there is an assembly called "CSV Targets Tab Enable"
    And the assembly "CSV Targets Tab Enable" has targets uploaded
    When I visit the assembly details page for "CSV Targets Tab Enable"
    Then the "Targets" tab should be enabled
    And the "Respondents" tab should be disabled

  Scenario: Both tabs enabled after both CSVs uploaded
    Given I am logged in as an admin user
    And there is an assembly called "CSV Both Uploaded"
    And the assembly "CSV Both Uploaded" has targets uploaded
    And the assembly "CSV Both Uploaded" has respondents uploaded
    When I visit the assembly details page for "CSV Both Uploaded"
    Then the "Targets" tab should be enabled
    And the "Respondents" tab should be enabled

  # Building the targets from the respondent data, on the Targets tab

  Scenario: The respondent columns are only offered once there is data to read
    Given I am logged in as an admin user
    And there is an assembly called "No Respondents Yet"
    When I visit the assembly targets page for "No Respondents Yet"
    Then I should not see "Create from respondent data"

  Scenario: Building the target categories from the respondent data columns
    Given I am logged in as an admin user
    And there is an assembly called "Targets From Respondents"
    And the assembly "Targets From Respondents" has respondents uploaded
    When I visit the assembly targets page for "Targets From Respondents"
    And I open the dialog to create targets from respondent data
    And I choose the respondent column "Gender"
    And I add the selected categories
    Then I should see "Created 1 targets"
    And I should see "Gender"
