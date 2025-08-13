# ABOUTME: This is a copy of some of the code from Django - django/contrib/auth/password_validation.py
# ABOUTME: adapted so we can use it without Django models.

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from django.contrib.auth.password_validation import CommonPasswordValidator, exceeds_maximum_length_ratio
from django.core.exceptions import ValidationError

# We need to override the error message and help text to avoid Django localisation being triggered.
# Of the 4 validators from Django:
#
# - MinimumLengthValidator and NumericPasswordValidator as so simple we copy them entirely.
# - CommonPasswordValidator is complicated - so we just override the text.
# - UserAttributeSimilarityValidator expects user to be a Django model with _meta - so
#   we just copy it all and chop out that code.


class MinimumLengthValidator:
    """
    Validate that the password is of a minimum length.
    """

    def __init__(self, min_length: int = 8) -> None:
        self.min_length = min_length

    def validate(self, password: str, user: object | None = None) -> None:
        if len(password) < self.min_length:
            raise ValidationError(
                self.get_error_message(),
                code="password_too_short",
            )

    def get_error_message(self) -> str:
        return f"This password is too short. It must contain at least {self.min_length} characters."

    def get_help_text(self) -> str:
        return f"Your password must contain at least {self.min_length} character."


class UserAttributeSimilarityValidator:  # pragma: no cover
    """
    Validate that the password is sufficiently different from the user's
    attributes.

    If no specific attributes are provided, look at a sensible list of
    defaults. Attributes that don't exist are ignored. Comparison is made to
    not only the full attribute value, but also its components, so that, for
    example, a password is validated against either part of an email address,
    as well as the full address.
    """

    DEFAULT_USER_ATTRIBUTES = ("username", "first_name", "last_name", "email")

    def __init__(self, user_attributes: Iterable[str] = DEFAULT_USER_ATTRIBUTES, max_similarity: float = 0.7) -> None:
        self.user_attributes = user_attributes
        if max_similarity < 0.1:
            raise ValueError("max_similarity must be at least 0.1")
        self.max_similarity = max_similarity

    def validate(self, password: str, user: object | None = None) -> None:
        if not user:
            return

        password = password.lower()
        for attribute_name in self.user_attributes:
            value = getattr(user, attribute_name, None)
            if not value or not isinstance(value, str):
                continue
            value_lower = value.lower()
            value_parts = [*re.split(r"\W+", value_lower), value_lower]
            for value_part in value_parts:
                if exceeds_maximum_length_ratio(password, self.max_similarity, value_part):
                    continue
                if SequenceMatcher(a=password, b=value_part).quick_ratio() >= self.max_similarity:
                    raise ValidationError(
                        self.get_error_message(),
                        code="password_too_similar",
                        params={"verbose_name": attribute_name},
                    )

    def get_error_message(self) -> str:
        return "The password is too similar to the %(verbose_name)s."

    def get_help_text(self) -> str:
        return "Your password cannot be too similar to your other personal information."


class SafeCommonPasswordValidator(CommonPasswordValidator):  # type: ignore[no-any-unimported]
    """
    The internals are a little complex - we'll just override the error and help text.
    """

    def get_error_message(self) -> str:
        return "This password is too common."

    def get_help_text(self) -> str:
        return "Your password cannot be a commonly used password."


class NumericPasswordValidator:
    """
    Validate that the password is not entirely numeric.
    """

    def validate(self, password: str, user: object | None = None) -> None:
        if password.isdigit():
            raise ValidationError(
                self.get_error_message(),
                code="password_entirely_numeric",
            )

    def get_error_message(self) -> str:
        return "This password is entirely numeric."

    def get_help_text(self) -> str:
        return "Your password cannot be entirely numeric."
