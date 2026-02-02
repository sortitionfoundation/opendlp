"""ABOUTME: BDD tests for email confirmation flows using pytest-bdd and Playwright.
ABOUTME: Tests password registration, login blocking, email confirmation, OAuth auto-confirmation, resend, rate limiting, and edge cases."""

from pytest_bdd import scenarios

scenarios("../../features/email_confirmation.feature")

# All step definitions are in email_confirmation_steps.py
# Included from conftest via pytest_plugins
