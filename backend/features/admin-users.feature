Feature: Manage Users
  As an Admin
  I want to be able to invite and manage users
  So that new users can be added to the system to manage assemblies.

  Scenario: Invite user
    Given the user is signed in
    When the user creates an invite
    Then the user sees the invite to give to the user
