Feature: Democratic Lottery part 2
As an Assembly Manager
I want to be able to configure the system
So that I can do the selection.

Note that there are multiple ways we will do this.
- The registrant data could be in a Google Spreadsheet, a CSV or could be in the local database.
- The categories and targets could be read from a Google Spreadsheet, a CSV, or could be set in the web app.
- The options could all be chosen manually, or the app could suggest values with the user reviewing and editing.

  Scenario: Configure selection
    Given the assembly is set up
    And people are registered
    When I open the Assembly
    Then I can specify the source of the respondents data
    And I can specify the categories and targets
    And I can configure the options for selection
    And I can save the options

  Scenario: Initialise selection
    Given the assembly is set up
    And people are registered
    And the selection options are set
    When I check the data
    Then I am told the number of categories and category values

  Scenario: Do full selection
    Given the assembly is set up
    And people are registered
    And the selection options are set
    When I start the selection
    Then I should see progress messages
    And the task should go from pending to finished
    And the results are reported
