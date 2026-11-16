Feature: Selection settings of a project held in OpenDLP
  As an organiser
  I want the selection settings to ask only for what they need
  So that I am not filling in fields that have no effect

  Background:
    Given a user is logged in as an admin

  Scenario: The address attributes appear only while the address check is ticked
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    Then the settings do not ask for attributes to keep
    And the address attributes are hidden
    When the user ticks Check same address
    Then the address attributes are shown
    When the user unticks Check same address
    Then the address attributes are hidden

  Scenario: Settings saved with the address check ticked keep the address attributes on show
    Given a database assembly whose selection settings are still to confirm
    When the user visits the selection page
    And the user ticks Check same address
    And the user enters "Postcode" as the address attributes
    And the user saves the selection settings
    And the user opens the selection settings
    Then the address attributes are shown
    And the address attributes are "Postcode"

  Scenario: Confirmed settings are folded away behind an Edit button
    Given a database assembly whose selection settings are confirmed
    When the user visits the selection page
    Then the selection settings are folded away with an Edit button
    When the user clicks the Edit button of the selection settings
    Then the selection settings are open with no Edit button
