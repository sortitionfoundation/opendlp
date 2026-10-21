Feature: Backoffice registration thank-you page
  As an assembly organiser
  I want to choose what respondents see after they send the form
  So that I can thank them in my own words, or rely on the standard translated page

  A new page shows the standard thank-you page. The starter content gives the
  author something to edit, and must open in the visual editor rather than its
  HTML view. Component tests cover the markup and the saves; these scenarios
  confirm the real browser behaviour.

  Background:
    Given I am logged in as an admin user

  Scenario: Writing our own thank-you page from the starter content
    Given there is an assembly called "Thank You Assembly" with a registration page
    When I visit the thank-you step for "Thank You Assembly"
    And I fill the thank-you page with starter content
    And I click Edit on the thank-you step
    Then the thank-you editor should be in its Visual view
    When I type "Lovely to hear from you. " at the start of the visual thank-you editor
    And I save the registration form
    And I open the public thank-you page for "Thank You Assembly"
    Then the public page should show "Lovely to hear from you."
    When I follow the "Start a new registration" link
    Then I should be on the public registration form for "Thank You Assembly"

  Scenario: Switching to the standard page hides the editor and keeps our HTML
    Given there is an assembly called "Standard Thanks Assembly" with its own thank-you page "<p>Our own thanks</p>"
    When I visit the thank-you step for "Standard Thanks Assembly" in edit mode
    Then the thank-you editor should be shown
    When I choose the "Standard thank-you page" option
    Then the thank-you editor should be hidden
    When I save the registration form
    And I open the public thank-you page for "Standard Thanks Assembly"
    Then the public page should show "Thank you for registering"
    When I visit the thank-you step for "Standard Thanks Assembly" in edit mode
    And I choose the "Your own thank-you page" option
    Then the visual thank-you editor should show "Our own thanks"

  Scenario: The editor hidden behind the standard page works once shown
    Given there is an assembly called "Hidden Editor Assembly" with a registration page
    When I visit the thank-you step for "Hidden Editor Assembly" in edit mode
    Then the thank-you editor should be hidden
    When I choose the "Your own thank-you page" option
    And I type "Thanks, everyone" into the visual thank-you editor
    And I save the registration form
    And I open the public thank-you page for "Hidden Editor Assembly"
    Then the public page should show "Thanks, everyone"
