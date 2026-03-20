Feature: Backoffice CSV Upload
  As an administrator
  I want to upload CSV files for assemblies
  So that I can import participant data without using Google Spreadsheets.

  Scenario: Targets tab appears when CSV data source is selected
    Given I am logged in as an admin user
    And there is an assembly called "CSV Test Assembly"
    When I visit the assembly data page for "CSV Test Assembly"
    And I select "CSV file" from the data source selector
    Then I should see a "Targets" tab in the assembly navigation
    And the "Targets" tab should be disabled

  Scenario: Targets tab disappears when switching to Google Spreadsheet
    Given I am logged in as an admin user
    And there is an assembly called "CSV Switch Assembly"
    When I visit the assembly data page for "CSV Switch Assembly" with source "csv"
    Then I should see a "Targets" tab in the assembly navigation
    When I select "Google Spreadsheet" from the data source selector
    Then I should not see a "Targets" tab in the assembly navigation
