import typing

BDD_PORT = 5002  # Test server on 5002 to avoid conflict with dev server
ADMIN_EMAIL = "admin@opendlp.example"
ADMIN_PASSWORD = "admin8d2wpass"
NORMAL_EMAIL = "normal@opendlp.example"
NORMAL_PASSWORD = "normal8d2wpass"  # pragma: allowlist secret
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
    admin = f"{base}/admin"
    admin_users = f"{base}/admin/users"
    admin_invites = f"{base}/admin/invites"

    # Backoffice URLs (Pines UI + Tailwind)
    backoffice_showcase = f"{base}/backoffice/showcase"
    backoffice_dashboard = f"{base}/backoffice/dashboard"
    backoffice_create_assembly = f"{base}/backoffice/assembly/new"
    backoffice_assembly = "{base}/backoffice/assembly/{assembly_id}"
    backoffice_edit_assembly = "{base}/backoffice/assembly/{assembly_id}/edit"
    backoffice_members_assembly = "{base}/backoffice/assembly/{assembly_id}/members"
    backoffice_data_assembly = "{base}/backoffice/assembly/{assembly_id}/data"
    backoffice_selection_assembly = "{base}/backoffice/assembly/{assembly_id}/selection"

    assembly_urls: typing.ClassVar = {
        "view_assembly": "{base}/assemblies/{assembly_id}",
        "view_assembly_data": "{base}/assemblies/{assembly_id}/data",
        "view_assembly_members": "{base}/assemblies/{assembly_id}/members",
        "update_assembly": "{base}/assemblies/{assembly_id}/edit",
        "gsheet_configure": "{base}/assemblies/{assembly_id}/gsheet",
        "gsheet_select": "{base}/assemblies/{assembly_id}/gsheet_select",
        "gsheet_replace": "{base}/assemblies/{assembly_id}/gsheet_replace",
    }

    @classmethod
    def for_assembly(cls, url_name: str, assembly_id: str) -> str:
        return cls.assembly_urls[url_name].format(base=cls.base, assembly_id=assembly_id)

    @classmethod
    def backoffice_assembly_url(cls, assembly_id: str) -> str:
        return cls.backoffice_assembly.format(base=cls.base, assembly_id=assembly_id)

    @classmethod
    def backoffice_edit_assembly_url(cls, assembly_id: str) -> str:
        return cls.backoffice_edit_assembly.format(base=cls.base, assembly_id=assembly_id)

    @classmethod
    def backoffice_members_assembly_url(cls, assembly_id: str) -> str:
        return cls.backoffice_members_assembly.format(base=cls.base, assembly_id=assembly_id)

    @classmethod
    def backoffice_data_assembly_url(cls, assembly_id: str, source: str = "", mode: str = "") -> str:
        url = cls.backoffice_data_assembly.format(base=cls.base, assembly_id=assembly_id)
        params = []
        if source:
            params.append(f"source={source}")
        if mode:
            params.append(f"mode={mode}")
        if params:
            url += "?" + "&".join(params)
        return url

    @classmethod
    def backoffice_selection_assembly_url(cls, assembly_id: str) -> str:
        return cls.backoffice_selection_assembly.format(base=cls.base, assembly_id=assembly_id)
