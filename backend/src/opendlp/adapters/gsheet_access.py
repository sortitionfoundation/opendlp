"""ABOUTME: gspread client for checking what the service account can do with a Google Sheet
ABOUTME: Fails fast with a short timeout, because the check runs inside a web request"""

import gspread
from sortition_algorithms import make_gsheet_client

from opendlp import config

# (connect, read) in seconds, applied to each request, not to the whole check.
# Connect: 3.05 rather than 3 because TCP retransmits an unanswered connection
# attempt after 3 seconds; a timeout just past that lets the retry happen.
# Read: the longest gap allowed between chunks of a response. Typical calls take
# 0.2-1.6s, and the slowest seen was 4.2s. A check makes at most 4 requests, so
# the worst case is about 45s, under the 60s gunicorn worker timeout.
GSHEET_CHECK_TIMEOUT = (3.05, 8)


def make_check_client() -> gspread.client.Client:
    """Build a gspread client that does not retry, from the shared service-account credentials."""
    return make_gsheet_client(
        config.get_google_auth_json_path(),
        request_timeout=GSHEET_CHECK_TIMEOUT,
        http_client=gspread.HTTPClient,
    )
