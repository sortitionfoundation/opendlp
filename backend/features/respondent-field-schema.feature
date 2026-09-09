Feature: Respondent field schema
  As an assembly organiser
  I want respondent fields grouped into meaningful sections that I can customise
  So that a respondent's record is readable at a glance and the layout matches how I think about the data.

  Scenario: CSV-sourced respondent detail page shows grouped sections
    Given there is an assembly with respondents imported from CSV called "Grouped Schema Demo"
    And I am signed in as an admin user
    When I open the first respondent for "Grouped Schema Demo"
    Then I should see the "Name and contact" collapsible block
    And I should see the "About you" collapsible block
    And I should see the "Activity" collapsible block

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

  Scenario: Organiser adds a choice field through the modal
    Given there is an assembly with respondents imported from CSV called "Schema Modal Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Modal Demo"
    And I open the add-field modal
    And I save a new choice field labelled "Preferred contact" with options "Phone" and "Email"
    Then the schema editor should list the "preferred_contact" field
    And the "preferred_contact" row should summarise its options as "Phone, Email"

  Scenario: Organiser creates an age-bracket derived field and sees the recompute report
    Given there is an assembly with respondents imported from CSV called "Derived Field Demo"
    And the assembly "Derived Field Demo" has a "year_of_birth" number field
    And the assembly "Derived Field Demo" has an "age bracket" target with values "16-24, 25-39, 40+"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Derived Field Demo"
    And I create an age-bracket derived field feeding "age bracket" from "year_of_birth"
    Then I should see the recompute report
    When I close the recompute report
    Then the schema editor should list the "age bracket" field
    And the "age bracket" row should carry the "Derived" tag
