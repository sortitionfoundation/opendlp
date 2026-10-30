Feature: Respondent field schema
  As an assembly organiser
  I want one list of registration questions, with headings and text where I choose to put them
  So that the registration page, and a respondent's record, read in the order I think about the data.

  Scenario: Respondent detail page is sectioned at the questions list's headings
    Given there is an assembly with respondents imported from CSV called "Grouped Schema Demo"
    And the questions list for "Grouped Schema Demo" has the heading "About you" below "last_name"
    And I am signed in as an admin user
    When I open the first respondent for "Grouped Schema Demo"
    Then I should see the "Answers" collapsible block
    And I should see the "About you" collapsible block
    And I should see the "Activity" collapsible block

  Scenario: Schema editor lists fields in the CSV's order
    Given there is an assembly with respondents imported from CSV called "Schema Editor Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Editor Demo"
    Then the schema editor should list the "first_name" field
    And the schema editor should list the "last_name" field
    And the schema editor should list the "gender" field
    And the "first_name" field should appear before the "last_name" field

  Scenario: Organiser can move a field up
    Given there is an assembly with respondents imported from CSV called "Schema Reorder Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Reorder Demo"
    And I move the "last_name" field up
    Then the "last_name" field should appear before the "first_name" field

  Scenario: Organiser opens a question from its Edit button
    Given there is an assembly with respondents imported from CSV called "Schema Edit Button Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Edit Button Demo"
    And I click the Edit button on the "last_name" row
    Then the edit modal for "Last name" should be open
    And the question list behind the edit modal should be dimmed

  Scenario: Organiser removes a question from its row menu
    Given there is an assembly with respondents imported from CSV called "Schema Remove Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Remove Demo"
    And I choose "Remove" from the "custom_notes" row menu and confirm
    Then the schema editor should not list the "custom_notes" field

  Scenario: Organiser adds a choice field through the modal
    Given there is an assembly with respondents imported from CSV called "Schema Modal Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Modal Demo"
    And I open the add-field modal
    And I save a new choice field labelled "Preferred contact" with options "Phone" and "Email"
    Then the schema editor should list the "preferred_contact" field
    And the "preferred_contact" row should summarise its options as "Phone, Email"

  Scenario: The required switch says what turning it off means
    Given there is an assembly with respondents imported from CSV called "Schema Required Switch Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Required Switch Demo"
    And I open the add-field modal
    And I choose the "bool" question type
    Then the required switch should read "Required: Checkbox must be checked"
    When I turn the required switch off
    Then the required switch should read "Optional: Checkbox can be left unchecked"

  Scenario: Organiser adds a heading with some text to the end of the list
    Given there is an assembly with respondents imported from CSV called "Schema Heading Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Heading Demo"
    And I open the add heading or text dialog
    And I save the heading "About you" with the text "Tell us a little about yourself."
    Then the schema editor should list the heading "About you"
    And the heading "About you" should come last

  Scenario: Organiser adds a heading below a question from its row menu
    Given there is an assembly with respondents imported from CSV called "Schema Heading Below Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Heading Below Demo"
    And I choose "Add a heading or text below" from the "first_name" row menu
    And I save the heading "Your name" with the text "As you would like us to use it."
    Then the heading "Your name" should come straight after the "first_name" field

  Scenario: Organiser links some text in a heading or text block
    Given there is an assembly with respondents imported from CSV called "Schema Heading Link Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Heading Link Demo"
    And I open the add heading or text dialog
    And I type "privacy notice" into the text and select it
    And I press the Link button in the text toolbar
    And I apply the link address "https://example.org/privacy"
    Then the text should link to "https://example.org/privacy"
    And the add heading or text dialog should still be open

  Scenario: Organiser drags a question into a new place
    Given there is an assembly with respondents imported from CSV called "Schema Drag Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Drag Demo"
    And I drag the "gender" row above the "first_name" row
    Then the "gender" field should appear before the "first_name" field
    When I open the respondent field schema editor for "Schema Drag Demo"
    Then the "gender" field should appear before the "first_name" field

  Scenario: Organiser moves a question to the top with the keyboard
    Given there is an assembly with respondents imported from CSV called "Schema Keyboard Move Demo"
    And I am signed in as an admin user
    When I open the respondent field schema editor for "Schema Keyboard Move Demo"
    And I use the keyboard to choose "Move to top" from the "gender" row menu
    Then the page should say "Moved to position 1 of"
    And keyboard focus should be on the "gender" row menu button
    And the "gender" field should appear before the "eligible" field
