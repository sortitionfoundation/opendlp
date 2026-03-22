Feature: Backoffice CSV Upload
  As an administrator
  I want to upload CSV files for assemblies
  So that I can import participant data without using Google Spreadsheets.

  Scenario: Targets and Respondents tabs are always visible
    Given I am logged in as an admin user
    And there is an assembly called "Tab Test Assembly"
    When I visit the assembly details page for "Tab Test Assembly"
    Then I should see a "Targets" tab in the assembly navigation
    And I should see a "Respondents" tab in the assembly navigation
    And the "Targets" tab should be disabled
    And the "Respondents" tab should be disabled

  Scenario: Targets tab is disabled when no data source is configured
    Given I am logged in as an admin user
    And there is an assembly called "No Data Source Assembly"
    When I visit the assembly data page for "No Data Source Assembly"
    Then I should see a "Targets" tab in the assembly navigation
    And the "Targets" tab should be disabled
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

  Scenario: Targets tab is disabled for CSV source until targets uploaded
    Given I am logged in as an admin user
    And there is an assembly called "CSV Targets Assembly"
    When I visit the assembly data page for "CSV Targets Assembly" with source "csv"
    Then I should see a "Targets" tab in the assembly navigation
    And the "Targets" tab should be disabled
