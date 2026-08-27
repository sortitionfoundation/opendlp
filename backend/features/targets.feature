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
    And the "Male" target should be marked as auto calculated
    And I should see "Number to select: 20"

  Scenario: A hand-set target is marked, with its reason visible, and can be linked back
    Given there is an assembly with targets called "Relink Demo"
    And I am signed in as an admin user
    And the "Male" target was set by hand with the note "boosted by 2 for the callback rate"
    When I open the targets page for "Relink Demo"
    Then the "Male" target should be marked as manually modified
    And I should see "boosted by 2 for the callback rate"
    And the "Male" target should show min "12" and max "13"
    When I choose to edit all targets
    And I link the "Male" target back to its percentage
    And I save all targets
    Then the "Male" target should be marked as auto calculated
    And the "Male" target should show min "10" and max "11"

  Scenario: Editing every target at once
    Given there is an assembly with targets called "Edit All Demo"
    And I am signed in as an admin user
    When I open the targets page for "Edit All Demo"
    And I choose to edit all targets
    Then I should see the bulk edit form
    When I save all targets
    Then I should see "Targets saved"

  Scenario: A rejected save comes back as the form, with the error on its field
    Given there is an assembly with targets called "Bad Numbers Demo"
    And I am signed in as an admin user
    When I open the targets page for "Bad Numbers Demo"
    And I choose to edit all targets
    And I set the "Male" min to "9" and max to "2"
    And I save all targets
    Then I should see the bulk edit form
    And the "Male" edit row should show min "9" and max "2"
    And the "Male" edit row should show the error "Max must be at least the min"

  Scenario: Saving the targets runs the detailed check
    Given there is an assembly with targets called "Check On Save Demo"
    And I am signed in as an admin user
    When I open the targets page for "Check On Save Demo"
    Then I should not see the "Check targets in detail" button
    When I choose to edit all targets
    And I save all targets
    Then I should see "Targets saved"
    And I should see "Target check found problems"

  Scenario: The view page offers no way to change a target on the spot
    Given there is an assembly with targets called "Read Only Demo"
    And I am signed in as an admin user
    When I open the targets page for "Read Only Demo"
    Then I should see the "Edit targets" button
    And I should see the "Add target" button
    And I should not see the "Delete value" button
    And I should not see the "Add value" button

  Scenario: Adding a value while editing every target at once
    Given there is an assembly with targets called "Add Value Demo"
    And I am signed in as an admin user
    When I open the targets page for "Add Value Demo"
    And I choose to edit all targets
    And I add a target value called "Non-binary" with percentage "10"
    And I save all targets
    Then I should see "Targets saved"
    And the "Non-binary" target should show min "2" and max "3"

  Scenario: Deleting a value while editing every target at once
    Given there is an assembly with targets called "Delete Value Demo"
    And I am signed in as an admin user
    When I open the targets page for "Delete Value Demo"
    And I choose to edit all targets
    And I delete the "Female" target value
    And I save all targets
    Then I should see "Targets saved"
    And there should be no "Female" target value

  Scenario: A deletion can be taken back before saving
    Given there is an assembly with targets called "Undo Delete Demo"
    And I am signed in as an admin user
    When I open the targets page for "Undo Delete Demo"
    And I choose to edit all targets
    And I delete the "Female" target value
    And I take back the deletion of the "Female" target value
    And I save all targets
    Then I should see "Targets saved"
    And the "Female" target should show min "10" and max "11"

  Scenario: Deleting a whole target category
    Given there is an assembly with two target categories called "Delete Category Demo"
    And I am signed in as an admin user
    When I open the targets page for "Delete Category Demo"
    And I choose to edit all targets
    And I delete the "Age" category
    And I save all targets
    Then I should see "Targets saved"
    And there should be no "Age" category

  Scenario: The totals row keeps up as the percentages are typed
    Given there is an assembly with targets called "Totals Demo"
    And I am signed in as an admin user
    When I open the targets page for "Totals Demo"
    And I choose to edit all targets
    Then the bulk edit total should show "100%"
    When I set the "Male" percentage to "30"
    Then the bulk edit total should show "80%"

  Scenario: Adding a target while editing every target at once
    Given there is an assembly with targets called "Add Target Demo"
    And I am signed in as an admin user
    When I open the targets page for "Add Target Demo"
    And I choose to edit all targets
    And I add a target called "Age"
    And I add a target value called "16-29" with percentage "100"
    And I save all targets
    Then I should see "Targets saved"
    And the "Age" category should appear after the "Gender" category
    And the "16-29" target should show min "20" and max "20"

  Scenario: Adding a target from the read-only page
    Given there is an assembly with targets called "Add From View Demo"
    And I am signed in as an admin user
    When I open the targets page for "Add From View Demo"
    And I add a target called "Age"
    Then the "Age" category should be on screen with one blank value
    And I should see the "Save all" button

  Scenario: A target added by mistake can be taken straight back out
    Given there is an assembly with targets called "Undo Add Target Demo"
    And I am signed in as an admin user
    When I open the targets page for "Undo Add Target Demo"
    And I choose to edit all targets
    And I add a target called "Age"
    And I delete the "Age" category
    And I save all targets
    Then I should see "Targets saved"
    And there should be no "Age" category

  Scenario: Reordering the target categories
    Given there is an assembly with two target categories called "Reorder Demo"
    And I am signed in as an admin user
    When I open the targets page for "Reorder Demo"
    Then the "Gender" category should appear before the "Age" category
    When I choose to edit all targets
    And I move the "Gender" category down
    And I save all targets
    Then the "Age" category should appear before the "Gender" category
