BDD_PORT = 5002  # Test server on 5002 to avoid conflict with dev server


class Urls:
    base = f"http://localhost:{BDD_PORT}"
    front_page = f"{base}/"
    login = f"{base}/auth/login"
    register = f"{base}/auth/register"
    dashboard = f"{base}/dashboard"
    user_data_agreement = f"{base}/auth/user-data-agreement"


ADMIN_EMAIL = "admin@opendlp.example"
ADMIN_PASSWORD = "admin8d2wpass"
FRESH_PASSWORD = "sortition2x8w"
