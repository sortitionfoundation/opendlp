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
    Then the "Region" target row should say "Asked on the registration page"
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
    Then I should see a warning toast saying "2 fell back to UNKNOWN"
    And the "age bracket" target row should say "Computed from"

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

  Scenario: Removing the computed question a target was set up with
    Given there is an assembly with respondents imported from CSV called "Remove Computed Demo"
    And the assembly "Remove Computed Demo" has a "year_of_birth" number field
    And the assembly "Remove Computed Demo" has an "age bracket" target with values "16-24, 25-39, 40+"
    And I am signed in as an admin user
    When I open the target data sources for "Remove Computed Demo"
    And I set up the "age bracket" target with age ranges from "year_of_birth"
    And I open the more actions menu for the "age bracket" target
    And I choose "Delete computed question" from the menu and confirm
    Then the "age bracket" target row should say "No data source"
    When I open the respondent field schema editor for "Remove Computed Demo"
    Then the schema editor should list the "year_of_birth" field

  Scenario: Unlinking from a row's more actions menu
    Given there is an assembly with respondents imported from CSV called "Menu Unlink Demo"
    And the assembly "Menu Unlink Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Menu Unlink Demo"
    And I set up the "Region" target as an exact copy
    And I open the more actions menu for the "Region" target
    And I press Escape
    Then the more actions menu for the "Region" target should be closed
    And the target data sources should still be open
    When I open the more actions menu for the "Region" target
    And I choose "Unlink" from the menu and confirm
    Then the "Region" target row should say "isn't linked to it yet"

  Scenario: A lookup-table target moves straight on to uploading its table
    Given there is an assembly with respondents imported from CSV called "Lookup Upload Demo"
    And the assembly "Lookup Upload Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Lookup Upload Demo"
    And I set up the "Region" target to map from "postcode"
    Then the set-up dialog should be on "Step 2 of 2"
    And the "Upload later" button should be hidden
    When I upload a lookup table mapping "SW1A 1AA" to "North"
    Then the set-up dialog should say "Rows stored:"
    And the "Region" target row should say "1 lookup row"

  Scenario: Putting off a lookup table upload
    Given there is an assembly with respondents imported from CSV called "Lookup Defer Demo"
    And the assembly "Lookup Defer Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Lookup Defer Demo"
    And I set up the "Region" target to map from "postcode"
    And I tick "I don't have the lookup table yet"
    And I press the "Upload later" button
    Then I should see a warning toast saying "Until the lookup table is uploaded, everyone's Region will be UNKNOWN."
    And the "Region" target row should say "Until the lookup table is uploaded, everyone's Region is UNKNOWN."

  Scenario: Working a row's more actions menu from the keyboard
    Given there is an assembly with respondents imported from CSV called "Menu Keyboard Demo"
    And the assembly "Menu Keyboard Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Menu Keyboard Demo"
    And I set up the "Region" target as an exact copy
    And I focus the more actions button for the "Region" target and press "ArrowDown"
    Then keyboard focus should be on the "Unlink" menu item
    When I press Escape
    Then the more actions menu for the "Region" target should be closed
    And keyboard focus should be on the more actions button for the "Region" target
    And the target data sources should still be open

  Scenario: Keyboard focus follows a set-up dialog in and back out
    Given there is an assembly with respondents imported from CSV called "Dialog Focus Demo"
    And the assembly "Dialog Focus Demo" has a "Region" target with values "North, South"
    And I am signed in as an admin user
    When I open the target data sources for "Dialog Focus Demo"
    And I focus the set-up button for the "Region" target and press "Enter"
    Then keyboard focus should be on the method chooser in the set-up dialog
    And the checklist behind the set-up dialog should be out of reach
    When I choose the "exact" method from the keyboard
    Then keyboard focus should be on the method chooser in the set-up dialog
    When I press the "Save" button
    Then keyboard focus should be on the set-up button for the "Region" target
