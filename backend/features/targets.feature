Feature: Target percentages, notes and ordering
  As an assembly organiser
  I want to set targets as percentages, record why I changed them, and order the categories
  So that the quotas match my source data and anyone reading them can see where they came from.

  Scenario: Percentages drive min and max
    Given there is an assembly with targets called "Percentage Demo"
    And I am signed in as an admin user
    When I open the targets page for "Percentage Demo"
    Then I should see the percentage total "100.0%"
    And the "Male" target should show min "10" and max "11"

  Scenario: A hand-set target is marked, with its reason visible, and can be linked back
    Given there is an assembly with targets called "Relink Demo"
    And I am signed in as an admin user
    And the "Male" target was set by hand with the note "boosted by 2 for the callback rate"
    When I open the targets page for "Relink Demo"
    Then I should see "Set by hand"
    And I should see "boosted by 2 for the callback rate"
    And the "Male" target should show min "12" and max "13"
    When I link the "Male" target back to its percentage
    Then I should not see "Set by hand"
    And the "Male" target should show min "10" and max "11"

  Scenario: Editing every target at once
    Given there is an assembly with targets called "Edit All Demo"
    And I am signed in as an admin user
    When I open the targets page for "Edit All Demo"
    And I choose to edit all targets
    Then I should see the bulk edit form
    When I save all targets
    Then I should see "Targets saved"

  Scenario: Reordering the target categories
    Given there is an assembly with two target categories called "Reorder Demo"
    And I am signed in as an admin user
    When I open the targets page for "Reorder Demo"
    Then the "Gender" category should appear before the "Age" category
    When I move the "Gender" category down
    Then the "Age" category should appear before the "Gender" category
