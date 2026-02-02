Feature: Email Confirmation for User Registration
  As a new user
  I want to confirm my email address
  So that I can securely access my account

  Background:
    Given a valid invite code exists

  Scenario: Password registration requires email confirmation
    Given the user is starting to register
    When the user registers with a password
    Then the user should receive a confirmation email
    And the user should not be logged in
    And the user should be directed to the login page with a confirmation message

  Scenario: User cannot login before confirming email
    Given the user has registered but not confirmed their email
    When the user attempts to login
    Then the user should see an error about unconfirmed email
    And the user should see a link to resend confirmation

  Scenario: User confirms email with valid token
    Given the user has registered but not confirmed their email
    When the user clicks the confirmation link
    Then the user should be automatically logged in
    And the user should see a success message
    And the user should see the dashboard

  Scenario: User can login after confirming email
    Given the user has registered and confirmed their email
    When the user attempts to login
    Then the user should see the dashboard

  Scenario: OAuth registration auto-confirms email
    Given the user is starting to register with OAuth
    When the user completes OAuth registration
    Then the user should be automatically logged in
    And the user should not receive a confirmation email
    And the user should see the dashboard

  Scenario: Resend confirmation email
    Given the user has registered but not confirmed their email
    When the user requests to resend confirmation
    Then the user should receive a new confirmation email
    And the user should see a success message

  Scenario: Confirmation link expires after 24 hours
    Given the user has registered but not confirmed their email
    And the confirmation token has expired
    When the user clicks the expired confirmation link
    Then the user should see an error about the expired link
    And the user should be directed to login

  Scenario: Rate limiting prevents email spam
    Given the user has registered but not confirmed their email
    When the user requests to resend confirmation 3 times
    Then the 4th request should be rate limited
    And the user should see a rate limit error

  Scenario: Existing users are grandfathered in
    Given the user registered before email confirmation was implemented
    When the user attempts to login
    Then the user should be able to login successfully
    And the user should see the dashboard

  Scenario: Cannot use confirmation token twice
    Given the user has registered but not confirmed their email
    And the user has confirmed their email once
    When the user clicks the confirmation link again
    Then the user should see an error about the already-used token
    And the user should be directed to login
