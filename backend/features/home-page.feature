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

  Scenario: The hero puts the picture beside the text on a wide screen
    Given an anonymous visitor opens the home page on a wide screen
    Then the product picture should sit to the right of the heading

  Scenario: The hero stacks the picture under the text on a phone
    Given an anonymous visitor opens the home page on a phone
    Then the product picture should sit below the heading
