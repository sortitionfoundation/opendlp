Feature: User Sign in and Registration

  Scenario: Register fails with invalid invite code
    Given the user is on the register page
    When the user registers using an invalid invite code
    Then the user should be on the register page

  Scenario: Register with valid invite code
    Given the user is on the register page
    When the user registers using a valid invite code
    Then the user should be redirected to the dashboard

  Scenario: Sign out
    Given the user is on the dashboard page
    When the user clicks the logout link
    Then the user should be redirected to the front page

  Scenario: Successful Sign in with valid credentials
    Given the user is on the login page
    When the user logs in with valid credentials
    Then the user should be redirected to the dashboard
