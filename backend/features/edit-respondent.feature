Feature: Edit a respondent
  As an assembly organiser
  I want to correct a respondent's details
  So that the selection uses the right answers.

  Scenario: A yes/no answer from the registration form is shown when editing
    Given there is an assembly with a respondent who answered yes to "Attending"
    And I am signed in as an admin user
    When I open the edit page for that respondent
    Then "Yes" is selected for "Attending"
    When I enter the change note "Checked by phone"
    And I save the changes
    Then I see "Respondent updated"

  Scenario: A failed save says why, and links to the field
    Given there is an assembly with a respondent who has not answered "Attending"
    And I am signed in as an admin user
    When I open the edit page for that respondent
    And I enter the change note "Checked by phone"
    And I save the changes
    Then I see that there is a problem with "Attending"
    When I follow the link to the problem with "Attending"
    Then the first option for "Attending" has keyboard focus
