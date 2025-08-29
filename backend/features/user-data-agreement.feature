Feature: User Data Agreement
  As the Data Protection Officer
  I want people to consent to an agreement about the data we store about them (and other things)
  so that we comply with our responsibilities under the GDPR (and similar legislation).

  Scenario: Can view the data agreement
    Given the user is on the register page
    When the user clicks on the link to the data agreement
    Then the user sees the data agreement text

  Scenario: Register fails without data agreement
    Given the user is on the register page
    When the user registers using a valid invite code
    And the data agreement is not accepted
    And the registration form is submitted
    Then the user should be on the register page

  Scenario: Register with data agreement
    Given the user is on the register page
    When the user registers using a valid invite code
    And the data agreement is accepted
    And the registration form is submitted
    Then the user should be redirected to the dashboard
