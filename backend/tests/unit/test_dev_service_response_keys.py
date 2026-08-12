"""ABOUTME: Unit tests for the service-name to response-key map the service docs page uses
ABOUTME: Pins that it covers exactly the services dev.py can actually execute"""

from opendlp.entrypoints.blueprints.dev import _SERVICE_HANDLERS, SERVICE_RESPONSE_KEYS


class TestServiceResponseKeys:
    """The page keys its loading flags and response panels by a short name per service.

    That map used to live in the page's inline JavaScript, where nothing connected it to
    the handler table it is a view of. Renaming a handler left the page posting a service
    name the server did not know, and the only symptom was a request that failed at run
    time. Here the two are one import apart.
    """

    def test_names_every_service_that_can_be_executed(self) -> None:
        missing = sorted(set(_SERVICE_HANDLERS) - set(SERVICE_RESPONSE_KEYS))

        assert not missing, (
            f"No response key for: {', '.join(missing)}. A service the page cannot key "
            "has nowhere to show its result, so add an entry to SERVICE_RESPONSE_KEYS."
        )

    def test_names_no_service_that_does_not_exist(self) -> None:
        unknown = sorted(set(SERVICE_RESPONSE_KEYS) - set(_SERVICE_HANDLERS))

        assert not unknown, (
            f"No handler for: {', '.join(unknown)}. The page would post a service name "
            "the server does not know - either the handler was renamed or the entry is stale."
        )

    def test_the_keys_are_unique_so_two_services_cannot_share_a_response_panel(self) -> None:
        keys = list(SERVICE_RESPONSE_KEYS.values())

        assert len(keys) == len(set(keys))
