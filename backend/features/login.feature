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
    And the user's agreement to the terms and the data agreement should be recorded
    And the user should see the default view for an authorised user

  Scenario: The sign-up page asks to agree to the terms and the data agreement
    Given the user is starting to register
    Then the user should be asked to agree to the terms and the data agreement

  Scenario: Register fails without agreeing to the terms and the data agreement
    Given the user is starting to register
    When the user uses a valid invite code
    And the user does not agree to the terms and the data agreement
    And the user finishes registration
    Then the user should not be registered
    And the user should be told to agree to the terms and the data agreement

  Scenario: The invite code field says who to ask for a code
    Given the user is starting to register
    Then the user should see who to contact for an invite code

  Scenario: The password field lists what a password must be
    Given the user is starting to register
    Then the user should see what their password must be

  Scenario: The sign-up page shows the beta disclaimer
    Given the user is starting to register
    Then the user should see the beta disclaimer

  Scenario: Sign out
    Given the user is signed in
    When the user signs out
    Then the user should be told they are signed out on the sign in page

  Scenario: Successful Sign in with valid credentials
    Given the user is signing in
    When the user uses valid credentials
    Then the user should see the default view for an authorised user
