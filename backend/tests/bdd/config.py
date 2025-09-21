import typing

BDD_PORT = 5002  # Test server on 5002 to avoid conflict with dev server
ADMIN_EMAIL = "admin@opendlp.example"
ADMIN_PASSWORD = "admin8d2wpass"
FRESH_PASSWORD = "sortition2x8w"


class Urls:
    # note that we can't use url_for() in the BDD code as there is no app context.
    # Hence the duplication here.
    # TODO: investigate making a copy of the app object to use here
    base = f"http://localhost:{BDD_PORT}"
    front_page = f"{base}/"
    login = f"{base}/auth/login"
    register = f"{base}/auth/register"
    dashboard = f"{base}/dashboard"
    user_data_agreement = f"{base}/auth/user-data-agreement"
    view_assembly_list = f"{base}/dashboard"
    create_assembly = f"{base}/assemblies/new"

    assembly_urls: typing.ClassVar = {
        "view_assembly": "{base}/assemblies/{assembly_id}",
        "update_assembly": "{base}/assemblies/{assembly_id}/edit",
        "gsheet_configure": "{base}/assemblies/{assembly_id}/gsheet",
        "gsheet_select": "{base}/assemblies/{assembly_id}/gsheet_select",
    }

    @classmethod
    def for_assembly(cls, url_name: str, assembly_id: str) -> str:
        return cls.assembly_urls[url_name].format(base=cls.base, assembly_id=assembly_id)
