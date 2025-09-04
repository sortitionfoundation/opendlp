Feature: User Data Agreement
  As the Data Protection Officer
  I want people to consent to an agreement about the data we store about them (and other things)
  so that we comply with our responsibilities under the GDPR (and similar legislation).

  Scenario: Can view the data agreement
    Given the user is starting to register
    When the user goes to the data agreement
    Then the user sees the data agreement text

  Scenario: Register fails without data agreement
    Given the user is starting to register
    When the user uses a valid invite code
    And the user does not accept the data agreement
    And the user finishes registration
    Then the user should not be registered
    Then the user should be directed to try registering again

  Scenario: Register with data agreement
    Given the user is starting to register
    When the user uses a valid invite code
    And the user accepts the data agreement
    And the user finishes registration
    Then the user should be registered
    And the user should see the default view for an authorised user
