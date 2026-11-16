Feature: User Sign in and Registration
  As a Project Manager
  I want to be able to Register and Sign In
  So that I can view and edit my assemblies.

  Scenario: Register fails with invalid invite code
    Given the user is starting to register
    When the user uses an invalid invite code
    And the user finishes registration
    Then the user should not be registered
    And the user should be directed to try registering again

  Scenario: Register with valid invite code
    Given the user is starting to register
    When the user uses a valid invite code
    And the user finishes registration
    Then the user should be registered
    And the user should see the default view for an authorised user

  Scenario: The invite code field says who to ask for a code
    Given the user is starting to register
    Then the user should see who to contact for an invite code

  Scenario: The password field lists what a password must be
    Given the user is starting to register
    Then the user should see what their password must be

  Scenario: The password rules tick while the password is typed
    Given the user is starting to register
    When the user types a password of ten digits
    Then the password's length rule should be ticked and its digits rule should not
    When the user adds a letter to the password
    Then every password rule should be ticked

  Scenario: Sign out
    Given the user is signed in
    When the user signs out
    Then the user should be told they are signed out on the sign in page

  Scenario: Successful Sign in with valid credentials
    Given the user is signing in
    When the user uses valid credentials
    Then the user should see the default view for an authorised user
