Feature: Organiser assemblies
  As an organiser
  I want to create assemblies and run my own
  So that I can do my work without being able to read everyone else's.

  Scenario: An organiser creates an assembly and becomes its manager
    Given I am logged in as an organiser
    When I visit the backoffice dashboard
    And I create an assembly called "Lilliput Transport Assembly"
    Then I should see "Lilliput Transport Assembly"
    When I visit the backoffice dashboard
    Then I should see "Lilliput Transport Assembly"
    When I visit the assembly members page for "Lilliput Transport Assembly"
    Then the team members table should show "organiser@opendlp.example"
    And the team members table should show role "assembly-manager"

  Scenario: An organiser adds a colleague to their own assembly by exact email
    Given I am logged in as an organiser
    And there is an assembly called "Lilliput Housing Assembly" created by the organiser
    When I visit the assembly members page for "Lilliput Housing Assembly"
    Then I should see "Add User to Assembly"
    When I type "normal@opendlp.example" into the user search dropdown
    Then I should see "normal@opendlp.example" in the search results

  Scenario: An organiser cannot fish for accounts with a partial address
    Given I am logged in as an organiser
    And there is an assembly called "Lilliput Energy Assembly" created by the organiser
    When I visit the assembly members page for "Lilliput Energy Assembly"
    And I type "normal" into the user search dropdown
    Then I should see "No results found" after searching

  Scenario: An organiser cannot reach an assembly they were not added to
    Given I am logged in as an organiser
    And there is an assembly called "Someone Else's Assembly" created by admin
    When I visit the backoffice dashboard
    Then I should not see "Someone Else's Assembly"
    When I try to access the assembly details page for "Someone Else's Assembly"
    Then I should be redirected to the dashboard
    And I should see "You don't have permission to view this assembly"

  Scenario: A plain user is not offered the create button
    Given I am logged in as a normal user
    When I visit the backoffice dashboard
    Then I should not see "Create New Assembly"
