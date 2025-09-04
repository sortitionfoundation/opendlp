Feature: Create Assembly.
  As an Admin
  I want to be able to create Assemblies
  So that I can see the state of the Assembly and get to the next action.

  Scenario: Create Assembly
    Given the user is creating an assembly
    When the user makes the title "Liliput Climate Assembly"
    And the user finishes creating the assembly
    Then the user should see the created assembly
    And the user should see the assembly title "Liliput Climate Assembly"
