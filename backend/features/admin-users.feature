Feature: Manage Users
  As an Admin
  I want to be able to invite and manage users
  So that new users can be added to the system to manage assemblies.

  Scenario: Invite user
    Given the user is signed in
    When the user creates an invite
    Then the user sees the invite to give to the user

  Scenario: Add user to assembly
    Given there is a non-admin user
    And there is an assembly created
    And the non-admin user cannot see the assembly
    When the admin adds them to the assembly
    Then the non-admin user can see the assembly

  Scenario: Remove user from assembly
    Given there is a non-admin user
    And there is an assembly created
    And the non-admin user is a manager for the assembly
    When the admin removes them from the assembly
    Then the non-admin user cannot see the assembly

  Scenario: Lock a user out of a compromised account
    Given there is a disposable user
    When the admin disables their account
    Then the disposable user cannot sign in

  Scenario: Let a locked out user back in
    Given there is a disposable user
    And the admin has disabled their account
    When the admin enables their account
    Then the disposable user still cannot sign in with their old password

  Scenario: Change your mind about disabling an account
    Given there is a disposable user
    When the admin starts to disable their account and cancels
    Then the disposable user's account is still active

  Scenario: Rename a user in place
    Given there is a disposable user
    When the admin edits their first name to "Renamed" and presses Enter
    Then the admin sees the first name "Renamed" without leaving the page
    And the user's first name is "Renamed" after a reload

  Scenario: Change a user's role
    Given there is a disposable user
    When the admin changes their role to Organiser
    Then the user's role is Organiser

  Scenario: Clear a search with one click
    Given there is a disposable user
    And the admin has searched the users for the disposable user among organisers
    When the admin clears the search
    Then the search is empty and the role filter is kept
