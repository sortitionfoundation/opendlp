Feature: My account
  As a signed-in user
  I want to change my name and my password on My account
  So that I do not have to leave the page to do it

  Background:
    Given I am signed in with a password of my own
    And I am on My account

  Scenario: Editing my first name in place
    When I edit my first name to "Ada" and press Enter
    Then my first name reads "Ada"
    And the "Edit first name" button has focus

  Scenario: Escape leaves my name as it was
    When I start editing my first name and type "Grace"
    And I press Escape
    Then my first name reads "Dis"
    And the "Edit first name" button has focus

  Scenario: The X leaves my name as it was
    When I start editing my first name and type "Grace"
    And I press "Cancel editing first name"
    Then my first name reads "Dis"
    And the "Edit first name" button has focus
    When I reload the page
    Then my first name reads "Dis"

  Scenario: Leaving the row saves the name where it is
    When I start editing my last name and type "Lovelace"
    And I click the page heading
    Then my last name reads "Lovelace"

  Scenario: Changing my password opens a dialog over My account
    When I press "Change password"
    Then the "Change password" dialog is open
    And the "Current password" field has focus
    When I press Escape
    Then no dialog is open
    And the "Change password" button has focus

  Scenario: A wrong current password is said beside its field
    When I press "Change password"
    And I try to change my password with a wrong current password
    Then the dialog says "Current password is incorrect"
    And the "Current password" field has focus

  Scenario: Show reveals a password in the dialog
    When I press "Change password"
    And I press Show beside "Current password"
    Then the "Current password" field shows what is typed
    When I press Show beside "Current password"
    Then the "Current password" field hides what is typed

  Scenario: Setting a password opens a dialog over My account
    Given my account signs in only with Google
    When I press "Set password"
    Then the "Set password" dialog is open
    And the "Password" field has focus
    When I press Escape
    Then no dialog is open
    And the "Set password" button has focus

  Scenario: A refused new password is said beside its field
    Given my account signs in only with Google
    When I press "Set password"
    And I try to set a password with a confirmation that does not match
    Then the dialog says "Passwords must match"
    And the "Confirm password" field has focus

  Scenario: Show reveals a password in the Set password dialog
    Given my account signs in only with Google
    When I press "Set password"
    And I press Show beside "Password"
    Then the "Password" field shows what is typed

  Scenario: Setting a password reloads My account
    Given my account signs in only with Google
    When I press "Set password"
    And I set my password
    Then I see "Password set successfully"
    And the "Change password" button has focus
