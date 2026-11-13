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
