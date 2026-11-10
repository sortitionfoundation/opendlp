Feature: Draft home page
  As a member of the OpenDLP team
  I want to review the redesigned home page on the live site
  So that we can agree its look and feel before it replaces the current one

  Scenario: Anonymous visitor reaches sign in from the draft home page
    Given an anonymous visitor opens the draft home page
    Then they should see the draft home page hero
    When they choose to sign in from the draft home page
    Then they should be on the sign in page

  Scenario: Draft home page fits a phone screen
    Given an anonymous visitor opens the draft home page on a phone
    Then the draft home page should not scroll sideways
