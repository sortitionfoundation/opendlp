Feature: Home page
  As a visitor to OpenDLP
  I want a home page that explains what OpenDLP does
  So that I can decide to sign in or create an account

  Scenario: Anonymous visitor reaches sign in from the home page
    Given an anonymous visitor opens the home page
    Then they should see the home page hero
    When they choose to sign in from the home page
    Then they should be on the sign in page

  Scenario: Home page fits a phone screen
    Given an anonymous visitor opens the home page on a phone
    Then the home page should not scroll sideways

  Scenario: The hero puts the demo beside the text on a wide screen
    Given an anonymous visitor opens the home page on a wide screen
    Then the product demo should sit to the right of the heading

  Scenario: The hero stacks the demo under the text on a phone
    Given an anonymous visitor opens the home page on a phone
    Then the product demo should sit below the heading

  Scenario: The demo plays through the product's screens
    Given an anonymous visitor opens the home page on a wide screen
    Then the product demo should move on from its first screen

  Scenario: The demo rests on its result for a visitor who prefers reduced motion
    Given an anonymous visitor who prefers reduced motion opens the home page
    Then the product demo should rest on the dashboard screen
    And there should be no button to pause the demo

  Scenario: The visitor pauses the demo and plays it on, from the keyboard
    Given an anonymous visitor opens the home page on a wide screen
    When they pause the product demo from the keyboard
    Then the product demo should hold still
    When they play the product demo from the keyboard
    Then the product demo should move on again
