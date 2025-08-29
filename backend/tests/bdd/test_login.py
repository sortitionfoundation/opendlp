from pytest_bdd import scenarios

scenarios("../../features/login.feature")

# all stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`
