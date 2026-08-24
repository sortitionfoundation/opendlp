Feature: Backoffice registration HTML editor
  As an assembly organiser
  I want the registration form HTML field to have syntax highlighting and auto-indent
  So that hand-writing registration HTML is easier and less error-prone

  Scenario: The registration form HTML field is enhanced into a code editor
    Given I am logged in as an admin user
    And there is an assembly called "Editor Assembly" with a registration page
    When I visit the registration form editor for "Editor Assembly"
    Then the HTML content field should be a mounted code editor

  Scenario: Editing the HTML in the code editor and saving persists the content
    Given I am logged in as an admin user
    And there is an assembly called "Roundtrip Assembly" with a registration page
    When I visit the registration form editor for "Roundtrip Assembly"
    And I type "ROUNDTRIP-MARKER-4931" into the HTML content code editor
    And I save the registration form
    Then the saved registration HTML should contain "ROUNDTRIP-MARKER-4931"

  Scenario: The form skeleton preview is shown in a read-only code editor
    Given I am logged in as an admin user
    And there is an assembly called "Skeleton Assembly" with a registration page
    When I visit the registration form editor for "Skeleton Assembly"
    And I open the form skeleton preview
    Then the form skeleton should be shown in a read-only code editor

  Scenario: The form skeleton can be toggled between plain and GOV.UK styled HTML
    Given I am logged in as an admin user
    And there is an assembly called "Skeleton Toggle Assembly" with a registration page
    When I visit the registration form editor for "Skeleton Toggle Assembly"
    And I open the form skeleton preview
    Then the form skeleton should show plain markup
    When I switch the form skeleton to the GOV.UK styled view
    Then the form skeleton should show GOV.UK styled markup
    When I switch the form skeleton to the plain HTML view
    Then the form skeleton should show plain markup

  Scenario: Wizard navigation is locked while editing
    Given I am logged in as an admin user
    And there is an assembly called "Locked Nav Assembly" with a registration page
    When I visit the registration form editor for "Locked Nav Assembly"
    Then the wizard Next button should be disabled
    And the stepper navigation should be disabled

  Scenario: Cancelling without changes returns straight to the read-only view
    Given I am logged in as an admin user
    And there is an assembly called "Clean Cancel Assembly" with a registration page
    When I visit the registration form editor for "Clean Cancel Assembly"
    And I click the Cancel button in the editor header
    Then I should be on the read-only registration form view

  Scenario: The preview step embeds a read-only preview of the registration form
    Given I am logged in as an admin user
    And there is an assembly called "Form Preview Assembly" with a saved registration form
    When I visit the registration preview step for "Form Preview Assembly"
    Then I should see the embedded registration form preview
    And submitting the embedded preview form does not leave the page

  Scenario: Unpublishing a published registration returns it to test mode
    Given I am logged in as an admin user
    And there is an assembly called "Unpublish Assembly" with a published registration form
    When I visit the registration preview step for "Unpublish Assembly"
    And I click the Unpublish button
    Then the registration should be shown as in test mode

  Scenario: Closing a published registration asks for confirmation
    Given I am logged in as an admin user
    And there is an assembly called "Close Guard Assembly" with a published registration form
    When I visit the registration preview step for "Close Guard Assembly"
    And I click the Close registration button
    Then I should see the close registration confirmation
    When I choose to keep the registration open
    Then the close registration confirmation should be closed
    When I click the Close registration button
    And I confirm closing the registration
    Then the registration should be shown as closed

  # Scroll preservation: forms/links append ?scroll=<y> on navigation
  # (x-preserve-scroll-on-submit / x-scroll-preserve-links) and the page restores
  # it on load. This exercises the restore leg deterministically. It replaces an
  # older "enter edit mode preserves scroll" scenario, whose premise the 680
  # redesign invalidated (the Edit control is now top-anchored under the sticky
  # header, so scrolling down then clicking it legitimately returns to the top).
  Scenario: A saved scroll position is restored on load
    Given I am logged in as an admin user
    And there is an assembly called "Scroll Restore Assembly" with a registration page
    When I open the read-only registration form view for "Scroll Restore Assembly" with a saved scroll of 400
    Then the page should be scrolled down

  Scenario: Cancelling with unsaved changes asks for confirmation
    Given I am logged in as an admin user
    And there is an assembly called "Guard Assembly" with a registration page
    When I visit the registration form editor for "Guard Assembly"
    And I type "UNSAVED-MARKER-7719" into the HTML content code editor
    And I click the Cancel button in the editor header
    Then I should see the discard changes confirmation
    When I choose to keep editing
    Then the discard changes confirmation should be closed
    When I click the Cancel button in the editor header
    And I choose to discard my changes
    Then I should be on the read-only registration form view
    And the saved registration HTML should not contain "UNSAVED-MARKER-7719"

  Scenario: The registration tab lists the assembly's pages and opens a page's editor
    Given I am logged in as an admin user
    And there is an assembly called "List View Assembly" with a registration page
    When I visit the registration tab for "List View Assembly"
    Then I should see the registration page list
    When I open the first registration page from the list
    Then I should be on the read-only registration form view

  Scenario: Deleting a registration page from the list asks for confirmation first
    Given I am logged in as an admin user
    And there is an assembly called "Delete Page Assembly" with a registration page
    When I visit the registration tab for "Delete Page Assembly"
    And I choose to delete the first registration page
    Then I should see the delete registration page confirmation
    When I choose to keep the registration page
    Then the delete registration page confirmation should be closed
    And the assembly "Delete Page Assembly" should still have a registration page
    When I choose to delete the first registration page
    And I confirm deleting the registration page
    Then the assembly "Delete Page Assembly" should have no registration pages
