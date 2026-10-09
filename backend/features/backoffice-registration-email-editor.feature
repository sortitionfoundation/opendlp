Feature: Backoffice registration auto-reply email visual editor
  As an assembly organiser
  I want to format the auto-reply email without writing HTML
  So that I can write a clear confirmation email even if I do not know HTML

  The email body uses the same visual editor as the intro, offering only what
  works in an email: no images or tables, and only links that work from an
  inbox. Unit tests cover the schema and the link dialog's rule in jsdom; these
  scenarios confirm the real browser behaviour.

  Background:
    Given I am logged in as an admin user

  Scenario: Formatting the auto-reply email from the toolbar and saving it
    Given there is an assembly called "Email Format Assembly" with the auto-reply body "<p>Thanks for registering</p>"
    When I visit the auto-reply email editor for "Email Format Assembly"
    And I select everything in the visual email editor
    And I press the "Bold" toolbar button
    And I save the registration form
    Then the email HTML view should contain "<p><strong>Thanks for registering</strong></p>"

  Scenario: The email toolbar offers no images or tables
    Given there is an assembly called "Email Toolbar Assembly" with the auto-reply body "<p>Hello</p>"
    When I visit the auto-reply email editor for "Email Toolbar Assembly"
    Then the formatting toolbar should offer "Bold"
    And the formatting toolbar should not offer "Image"
    And the formatting toolbar should not offer "Table"

  Scenario: An email body with a table opens in its HTML view
    Given there is an assembly called "Email Table Assembly" with the auto-reply body "<table><tr><td>Date</td><td>12 May</td></tr></table>"
    When I visit the auto-reply email editor for "Email Table Assembly"
    Then the email editor should be in its HTML view, saying why

  Scenario: A relative link is refused in the email
    Given there is an assembly called "Email Link Assembly" with the auto-reply body "<p>Read the guide</p>"
    When I visit the auto-reply email editor for "Email Link Assembly"
    And I select everything in the visual email editor
    And I press the "Link" toolbar button
    And I apply the link address "/guide"
    Then the link dialog should say "so the link works in an email"
    When I apply the link address "https://example.org/guide"
    Then the email body should link to "https://example.org/guide"

  Scenario: The read-only email view shows the visual editor without a toolbar
    Given there is an assembly called "Email Read Only Assembly" with the auto-reply body "<p>Hello <strong>{{ respondent.first_name_or_friend }}</strong></p>"
    When I visit the read-only auto-reply email for "Email Read Only Assembly"
    Then the visual email editor should show "Hello"
    And the visual email editor should not be editable
    And there should be no formatting toolbar
