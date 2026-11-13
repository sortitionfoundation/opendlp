Feature: Project details
  As an organiser
  I want everything about a project's set-up on one page
  So that I can see it and change it without hunting through tabs.

  Background:
    Given I am logged in as an admin user
    And there is a project called "Riverside Panel" asking "How should we use the riverside?"
    And I am on the details page of the project

  # Basic details, edited in place

  Scenario: The title is edited in place and the page heading follows
    When I edit the project title to "Riverside Jury" and press Enter
    Then the project title reads "Riverside Jury"
    And the page heading is "Riverside Jury"
    And focus is on the "Edit project title" button
    And I am told "Project details saved"
    And the project is stored with the title "Riverside Jury"

  Scenario: Escape puts the stored title back
    When I start editing the project title and type "Never Saved"
    And I press Escape
    Then the project title reads "Riverside Panel"
    And the project is stored with the title "Riverside Panel"

  Scenario: Leaving the row saves
    When I start editing the project title and type "Saved By Leaving"
    And I click elsewhere on the page
    Then the project title reads "Saved By Leaving"
    And the project is stored with the title "Saved By Leaving"

  Scenario: A title that is too short is refused in the row
    When I edit the project title to "ab" and press Enter
    Then the project title field is open and marked as refused
    And the page heading is "Riverside Panel"
    When I press Escape
    Then the project title reads "Riverside Panel"

  Scenario: In the framing question Enter adds a line and Ctrl+Enter saves
    When I start editing the framing question and type "First line"
    And I press Enter and type "Second line"
    Then the framing question field is still open
    When I press Ctrl+Enter
    Then the framing question has the lines "First line" and "Second line"
    And I am told "Project details saved"

  Scenario: The panel size is edited in place
    When I edit the panel size to "45" and press Enter
    Then the panel size reads "45"
    And I am told "Panel size saved."

  Scenario: The first event date is edited in place
    When I edit the first event date to "2031-04-01" and press Enter
    Then the first event date reads "April 1, 2031"

  Scenario: Someone with a read-only role sees the values and no pencils
    Given a read-only member of the project is signed in
    And I am on the details page of the project
    Then I can read "Riverside Panel" and "How should we use the riverside?"
    And there are no edit buttons on the page

  # Data source

  Scenario: The cog opens the data source settings over the page
    When I open the data source settings
    Then the data source settings dialog is open
    And the dialog's data location is "In OpenDLP"
    And the dialog has no stepper
    When I close the data source settings
    Then the data source settings dialog is closed
    And focus is on the "Data source settings" button

  Scenario: Targets uploaded in the settings dialog show on the card
    When I open the data source settings
    And I choose to import targets from a CSV
    And I upload the example targets in the settings dialog
    Then the settings dialog says "4 targets uploaded"
    And the dialog's data location cannot be changed
    When I close the data source settings
    Then the data source card says "Import from CSV"
    And the data source card says "4 targets uploaded"

  Scenario: Saving how the data will arrive shows on the card
    When I open the data source settings
    And I choose to collect respondents through registration
    And I save the data source settings
    Then the data source card says "Through OpenDLP registration"
    And I am told "Data source settings saved"

  Scenario: Moving an empty project to Google Sheets
    When I open the data source settings
    And I change the dialog's data location to "In Google Sheets"
    Then the settings dialog shows the Google Sheets fields
    When I fill in a spreadsheet URL and the UK team
    And I save the data source settings
    Then the data source card says "In Google Sheets"
    And the data source card links to the spreadsheet
    And the spreadsheet's access is checked on the page

  Scenario: Deleting uploaded targets comes back to the settings dialog
    When I open the data source settings
    And I choose to import targets from a CSV
    And I upload the example targets in the settings dialog
    And I delete the targets and confirm
    Then the data source settings dialog is open
    And the settings dialog does not say "targets uploaded"
    And the dialog's data location can be changed

  # Registration link

  Scenario: A project with no registration page offers to create one
    Then the registration link card links to the Registration tab as "Create"

  Scenario: A project with a registration page shows its links
    Given the project has a registration page
    And I am on the details page of the project
    Then the registration link card links to the Registration tab as "See details"
    And the registration link card shows the page's URL and its short URL
    And the registration link card offers the QR code to download

  # Team

  Scenario: Adding a team member from the dialog
    Given there is a user "normal@opendlp.example"
    When I open the add a team member dialog
    Then focus is in the team member search
    When I search for "normal@" and pick "normal@opendlp.example"
    And I choose the team role "Read Only"
    And I add the team member
    Then the add a team member dialog is closed
    And the team lists "normal@opendlp.example" as "Read only"
    And I am told "added to project"
    And focus is on the "Add a team member" button

  Scenario: Adding one person and then another
    Given there is a user "normal@opendlp.example"
    When I open the add a team member dialog
    And I search for "normal@" and pick "normal@opendlp.example"
    And I add the team member and ask for another
    Then the add a team member dialog says "has been added"
    And the team lists "normal@opendlp.example" as "Confirmation caller"
    And focus is in the team member search
    And the team member search is empty

  Scenario: Adding nobody is refused in the dialog
    When I open the add a team member dialog
    And I add the team member
    Then the add a team member dialog says "This field is required"

  Scenario: Changing a team member's role
    Given "normal@opendlp.example" is a read-only member of the project
    And I am on the details page of the project
    When I open the change role dialog for "normal@opendlp.example"
    And I change the role to "Confirmation Caller"
    Then the team lists "normal@opendlp.example" as "Confirmation caller"
    And I am told "is now Confirmation caller"

  Scenario: Removing a team member
    Given "normal@opendlp.example" is a read-only member of the project
    And I am on the details page of the project
    When I remove "normal@opendlp.example" from the team and confirm
    Then the team does not list "normal@opendlp.example"
    And I am told "removed from project"
