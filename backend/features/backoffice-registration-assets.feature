Feature: Registration page assets panel
  As an assembly organiser
  I want to add images and PDFs to a registration page without losing my place
  So that I can reference them from the form HTML I am part-way through writing

  The page's Alpine component moved out of a 580-line inline <script> into
  src/js/backoffice/registration-page.js, configured by a JSON data block.
  Component tests cover the markup and the data block; only a real browser can
  confirm the bundle loads, registers, and drives the panel against the JSON
  routes - including that the CSRF token made it across.

  Background:
    Given I am logged in as an admin user

  Scenario: The page loads its component from a built bundle
    Given there is an assembly called "Bundle Assembly" with a registration page
    When I visit the registration form editor for "Bundle Assembly"
    Then the registration page should have no inline script body
    And the assets panel should respond to Alpine

  Scenario: Uploading an image adds it to the list without reloading the page
    Given there is an assembly called "Image Upload Assembly" with a registration page
    When I visit the registration form editor for "Image Upload Assembly"
    And I upload an image called "Assembly logo"
    Then the assets panel should list an image called "Assembly logo"
    And the page should not have reloaded

  Scenario: The upload button stays disabled until there is a file and alt text
    Given there is an assembly called "Alt Guard Assembly" with a registration page
    When I visit the registration form editor for "Alt Guard Assembly"
    And I open the image upload modal
    Then the image upload button should be disabled

  Scenario: Editing an image's alt text updates the list in place
    Given there is an assembly called "Alt Edit Assembly" with a registration page
    When I visit the registration form editor for "Alt Edit Assembly"
    And I upload an image called "First name"
    And I change the alt text of "First name" to "Second name"
    Then the assets panel should list an image called "Second name"
    And the assets panel should not list an image called "First name"
    And the page should not have reloaded

  Scenario: Deleting an image from its details modal removes it from the list
    Given there is an assembly called "Image Delete Assembly" with a registration page
    When I visit the registration form editor for "Image Delete Assembly"
    And I upload an image called "Doomed logo"
    And I delete "Doomed logo" from its details modal
    Then the assets panel should list no images

  Scenario: Uploading a PDF adds it to the documents list
    Given there is an assembly called "Document Upload Assembly" with a registration page
    When I visit the registration form editor for "Document Upload Assembly"
    And I upload a document labelled "Information pack"
    Then the assets panel should list a document called "Information pack"
    And the page should not have reloaded
