"""ABOUTME: Heuristic rules classifying a respondent field key into a RespondentFieldGroup.
ABOUTME: Used when seeding a fresh schema from CSV headers or adding new columns on re-upload."""

from collections.abc import Iterable

from opendlp.domain.respondent_field_schema import RespondentFieldGroup
from opendlp.domain.respondents import normalise_field_name

# Each rule is a triple of (group, exact-normalised matches, substring patterns).
# Rules are checked in declaration order; the first match wins. Substring patterns
# are matched against the normalised form (lowercase, alphanumeric only).
HEURISTIC_RULES: list[tuple[RespondentFieldGroup, set[str], list[str]]] = [
    (
        RespondentFieldGroup.ELIGIBILITY,
        {"eligible", "canattend", "available"},
        [],
    ),
    (
        RespondentFieldGroup.NAME_AND_CONTACT,
        {
            "firstname",
            "givenname",
            "forename",
            "lastname",
            "surname",
            "familyname",
            "fullname",
            "name",
            "email",
            "emailaddress",
            "phone",
            "phonenumber",
            "mobile",
            "mobilenumber",
            "tel",
            "telephone",
            "contactnumber",
            "countrycode",
            "externalid",
        },
        [],
    ),
    (
        RespondentFieldGroup.ADDRESS,
        {
            "address",
            "addressline1",
            "addressline2",
            "addressline3",
            "street",
            "streetaddress",
            "city",
            "town",
            "county",
            "region",
            "state",
            "postcode",
            "zip",
            "zipcode",
            "postalcode",
            "country",
        },
        ["addressline", "addrline"],
    ),
    (
        RespondentFieldGroup.CONSENT,
        {
            "consent",
            "consenttocontact",
            "stayondb",
            "stayonlist",
            "marketingconsent",
            "futurecontact",
        },
        [],
    ),
    (
        RespondentFieldGroup.ABOUT_YOU,
        {
            "gender",
            "sex",
            "age",
            "agebracket",
            "agerange",
            "dob",
            "dateofbirth",
            "dobday",
            "dobmonth",
            "dobyear",
            "yearofbirth",
            "birthyear",
            "ethnicity",
            "race",
            "disability",
            "disabilitystatus",
            "education",
            "educationlevel",
            "qualification",
            "income",
            "incomebracket",
            "occupation",
            "employment",
            "employmentstatus",
        },
        ["opinion", "attitude"],
    ),
]


def classify_field_key(
    field_key: str,
    target_category_names: Iterable[str] = (),
) -> RespondentFieldGroup:
    """Classify a field key into a ``RespondentFieldGroup``.

    If ``field_key`` matches any of ``target_category_names`` (case-insensitive,
    after normalisation) it is routed to ``ABOUT_YOU`` — target-relevant
    fields are the canonical "about you" content. Otherwise the pattern rules
    in ``HEURISTIC_RULES`` are checked in declaration order. Unmatched keys
    fall back to ``OTHER``.
    """
    normalised = normalise_field_name(field_key)
    if not normalised:
        return RespondentFieldGroup.OTHER

    target_normalised = {normalise_field_name(name) for name in target_category_names}
    target_normalised.discard("")
    if normalised in target_normalised:
        return RespondentFieldGroup.ABOUT_YOU

    for group, exact_matches, substrings in HEURISTIC_RULES:
        if normalised in exact_matches:
            return group
        for pattern in substrings:
            if pattern in normalised:
                return group
    return RespondentFieldGroup.OTHER
