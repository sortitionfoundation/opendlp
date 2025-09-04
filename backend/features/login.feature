Feature: User Sign in and Registration
  As an Assembly Manager
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

  Scenario: Sign out
    Given the user is signed in
    When the user signs out
    Then the user should see the default view for an anonymous user

  Scenario: Successful Sign in with valid credentials
    Given the user is signing in
    When the user uses valid credentials
    Then the user should see the default view for an authorised user
