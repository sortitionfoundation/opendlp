Feature: Respondent field schema
  As an assembly organiser
  I want respondent fields grouped into meaningful sections that I can customise
  So that a respondent's record is readable at a glance and the layout matches how I think about the data.

  Scenario: CSV-sourced respondent detail page shows grouped sections
    Given there is an assembly with respondents imported from CSV called "Grouped Schema Demo"
    And I am signed in as an admin user
    When I open the first respondent for "Grouped Schema Demo"
    Then I should see the "Name and contact" group heading
    And I should see the "About you" group heading
    And I should see the "Record metadata" collapsible block

  Scenario: Schema editor lists fields in their groups
    Given there is an assembly with respondents imported from CSV called "Schema Editor Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Editor Demo"
    Then the schema editor should list the "first_name" field
    And the schema editor should list the "last_name" field
    And the schema editor should list the "gender" field
    And the "first_name" field should appear before the "last_name" field

  Scenario: Organiser can move a field up within its group
    Given there is an assembly with respondents imported from CSV called "Schema Reorder Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Reorder Demo"
    And I move the "last_name" field up
    Then the "last_name" field should appear before the "first_name" field
