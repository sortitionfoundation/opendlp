Feature: Selection settings of a project held in OpenDLP
  As an organiser
  I want the selection settings to ask only for what they need
  So that I am not filling in fields that have no effect

  Background:
    Given a user is logged in as an admin

  Scenario: The address attributes appear only while the address check is ticked
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    And the user opens the selection settings
    Then the settings do not ask for attributes to keep
    And the address attributes are hidden
    When the user ticks Check same address
    Then the address attributes are shown
    When the user unticks Check same address
    Then the address attributes are hidden

  Scenario: Settings saved with the address check ticked keep the address attributes on show
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    And the user opens the selection settings
    And the user ticks Check same address
    And the user enters "Postcode" as the address attributes
    And the user saves the selection settings
    And the user opens the selection settings
    Then the address attributes are shown
    And the address attributes are "Postcode"

  Scenario: Selection waits for the settings, and says how to give them
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    Then the page says selection is waiting for the selection settings
    And running a selection is not possible
    When the user follows the page's way to review the selection settings
    Then the selection settings dialog is open
    When the user saves the selection settings
    Then the user is on the selection page
    And the page does not say selection is waiting
    And running a selection is possible

  Scenario: Cancelling the settings changes nothing and returns focus to the cog
    Given a database assembly whose selection settings are confirmed
    When the user visits the selection page
    And the user opens the selection settings
    And the user cancels the selection settings
    Then the selection settings dialog is closed
    And focus is on the selection settings cog

  Scenario: An address attribute the respondents do not have is refused in the dialog
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    And the user opens the selection settings
    And the user ticks Check same address
    And the user enters "Nowhere" as the address attributes
    And the user tries to save the selection settings
    Then the selection settings dialog is open
    And the dialog says "Unrecognised attribute names: Nowhere"

  Scenario: The settings open from the project details page and come back to it
    Given a database assembly whose selection settings are still to confirm
    When the user visits the project details page
    Then the selection settings card says "To confirm"
    When the user opens the selection settings
    And the user saves the selection settings
    Then the user is on the project details page
    And the selection settings card says "Confirmed"
