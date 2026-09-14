Feature: Target data sources
  As an assembly organiser
  I want each target wired to the registration field that feeds it
  So that the data selection needs is collected or computed without hand-building matching fields.

  Scenario: Exact copy creates a linked registration field
    Given there is an assembly with respondents imported from CSV called "Exact Copy Demo"
    And the assembly "Exact Copy Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Exact Copy Demo"
    And I set up the "Region" target as an exact copy
    Then the "Region" target row should say "Asked on the registration form"
    When I open the respondent field schema editor for "Exact Copy Demo"
    Then the schema editor should list the "Region" field
    And the "Region" row should carry the "Feeds target: Region" tag

  Scenario: Age ranges compute the target from a year of birth
    Given there is an assembly with respondents imported from CSV called "Age Ranges Demo"
    And the assembly "Age Ranges Demo" has a "year_of_birth" number field
    And the assembly "Age Ranges Demo" has an "age bracket" target with values "16-24, 25-39, 40+"
    And I am signed in as an admin user
    When I open the target data sources for "Age Ranges Demo"
    And I set up the "age bracket" target with age ranges from "year_of_birth"
    Then I should see the recompute report
    When I close the recompute report
    Then the "age bracket" target row should say "Computed from"

  Scenario: Renaming a linked target asks before unlinking its field
    Given there is an assembly with respondents imported from CSV called "Force Unlink Demo"
    And the assembly "Force Unlink Demo" has a "Regions" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Force Unlink Demo"
    And I set up the "Regions" target as an exact copy
    And I rename the "Regions" target to "Areas" on the targets page
    Then I should be asked to confirm unlinking
    When I confirm the unlinking
    And I open the target data sources for "Force Unlink Demo"
    Then the "Areas" target row should say "No data source"
