Feature: Democratic Lottery part 2
As an Assembly Manager
I want to be able to configure the system
So that I can do the selection.

Note that there are multiple ways we will do this.
- The registrant data could be in a Google Spreadsheet, a CSV or could be in the local database.
- The categories and targets could be read from a Google Spreadsheet, a CSV, or could be set in the web app.
- The options could all be chosen manually, or the app could suggest values with the user reviewing and editing.

  Scenario: Configure selection
    Given that the assembly is set up for "manual gsheet setup"
    And people are registered
    When I open the Assembly with "manual gsheet setup"
    Then I can specify the source of the respondents data in "manual gsheet setup"
    And I can specify the categories and targets in "manual gsheet setup"
    And I can configure the options for selection in "manual gsheet setup"
