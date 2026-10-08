Feature: Backoffice registration visual intro editor
  As an assembly organiser
  I want to format the registration page intro without writing HTML
  So that I can write a clear introduction even if I do not know HTML

  The visual editor is Tiptap mounted over the intro textarea, with the
  CodeMirror editor as its HTML view. Unit tests cover the schema, the
  round-trip check and the toolbar wiring in jsdom; these scenarios confirm
  the real browser behaviour - focus, selection, drag and drop, and images
  loading - that jsdom cannot.

  Background:
    Given I am logged in as an admin user

  Scenario: Formatting the intro from the toolbar and saving it
    Given there is an assembly called "Visual Format Assembly" with a registration page
    When I visit the registration intro editor for "Visual Format Assembly"
    And I type "Welcome everyone" into the visual intro editor
    And I press the "Heading 2" toolbar button
    And I select everything in the visual intro editor
    And I press the "Bold" toolbar button
    And I save the registration form
    Then the intro HTML view should contain "<h2><strong>Welcome everyone</strong></h2>"
    And the registration preview should show a level 2 heading "Welcome everyone"

  Scenario: HTML the visual editor cannot show stays in the HTML view
    Given there is an assembly called "Visual Refuse Assembly" with a registration page
    When I visit the registration intro editor for "Visual Refuse Assembly"
    And I switch the intro editor to its HTML view
    And I enter "<table><tr><td>Logo</td></tr></table>" in the intro HTML view
    And I switch the intro editor to its Visual view
    Then the intro editor should still be in its HTML view
    And the intro editor should explain that the HTML stays in the HTML view

  Scenario: Formatting with the keyboard alone
    Given there is an assembly called "Visual Keyboard Assembly" with a registration page
    When I visit the registration intro editor for "Visual Keyboard Assembly"
    And I type "Plain words" into the visual intro editor
    And I select everything in the visual intro editor
    And I move focus back into the formatting toolbar
    And I press the right arrow key 4 times
    And I press Enter
    Then the intro should hold "<p><strong>Plain words</strong></p>"

  Scenario: Template variables are highlighted in the visual editor
    Given there is an assembly called "Visual Variable Assembly" with a registration page
    When I visit the registration intro editor for "Visual Variable Assembly"
    And I type "Welcome to {{ assembly_title }}" into the visual intro editor
    Then "{{ assembly_title }}" should be highlighted as a variable

  Scenario: An image dropped into the visual editor is uploaded and shown
    Given there is an assembly called "Visual Drop Assembly" with a registration page
    When I visit the registration intro editor for "Visual Drop Assembly"
    And I drop an image file called "dropped.png" into the visual intro editor
    Then the image upload dialog should show "dropped.png"
    When I give the dropped image the alt text "Dropped logo" and upload it
    Then the visual intro editor should show the image "Dropped logo"
    And the assets panel should list the image "Dropped logo"
    When I save the registration form
    Then the registration preview should show the image "Dropped logo"

  Scenario: The read-only intro view shows the visual editor without a toolbar
    Given there is an assembly called "Visual Read Only Assembly" with the intro "<h1>Read only title</h1>"
    When I visit the read-only registration intro for "Visual Read Only Assembly"
    Then the visual intro editor should show a level 1 heading "Read only title"
    And the visual intro editor should not be editable
    And there should be no formatting toolbar

  Scenario: The intro style radio changes the look in the editor and on the page
    Given there is an assembly called "Visual Style Assembly" with the intro "<p>Styled words</p>"
    When I visit the registration intro editor for "Visual Style Assembly"
    Then the paragraph in the visual intro editor should use the GOV.UK body font size
    When I choose the "Plain — bring your own styles" intro style
    Then the paragraph in the visual intro editor should not use the GOV.UK body font size
    When I choose the "GOV.UK (recommended, accessible)" intro style
    And I save the registration form
    Then the registration preview should show the paragraph "Styled words" with the class "govuk-body"
