"""ABOUTME: Tests for the UnitOfWork convention checker
ABOUTME: The checker fails the build when a function that is handed a UnitOfWork opens its own context"""

import pathlib

import pytest

from scripts.check_uow_convention import DEFAULT_ROOT, find_self_managing, main

SELF_MANAGING = '''
def do_the_thing(uow, thing_id):
    """Opens its own context, which only an entrypoint may do."""
    with uow:
        uow.things.get(thing_id)
'''

CALLER_MANAGES = '''
def do_the_thing(uow, thing_id):
    """The caller is expected to manage the `uow` context (`with uow: ...`)."""
    return uow.things.get(thing_id)
'''

ENTRYPOINT = """
def a_route(thing_id):
    uow = bootstrap.get_flask_uow()
    with uow:
        return do_the_thing(uow, thing_id)
"""

NO_UOW = """
def unrelated(thing_id):
    with open(thing_id) as handle:
        return handle.read()
"""


def write_module(root: pathlib.Path, name: str, source: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


class TestFindSelfManaging:
    def test_reports_a_function_that_opens_its_own_context(self, tmp_path):
        write_module(tmp_path, "thing_service.py", SELF_MANAGING)

        assert find_self_managing(tmp_path) == {"thing_service.py::do_the_thing"}

    def test_ignores_a_function_that_expects_an_open_context(self, tmp_path):
        write_module(tmp_path, "thing_service.py", CALLER_MANAGES)

        assert find_self_managing(tmp_path) == set()

    def test_ignores_an_entrypoint_that_makes_its_own_unit_of_work(self, tmp_path):
        """The rule is about functions handed a UnitOfWork, not ones that build one."""
        write_module(tmp_path, "blueprints/things.py", ENTRYPOINT)

        assert find_self_managing(tmp_path) == set()

    def test_ignores_a_with_block_that_is_not_a_unit_of_work(self, tmp_path):
        write_module(tmp_path, "thing_service.py", NO_UOW)

        assert find_self_managing(tmp_path) == set()

    def test_reports_nested_modules(self, tmp_path):
        write_module(tmp_path, "pkg/thing_service.py", SELF_MANAGING)

        assert find_self_managing(tmp_path) == {"pkg/thing_service.py::do_the_thing"}


class TestMain:
    def test_passes_when_nothing_opens_its_own_context(self, tmp_path):
        write_module(tmp_path, "thing_service.py", CALLER_MANAGES)

        assert main([str(tmp_path)]) == 0

    def test_fails_on_an_offender(self, tmp_path, capsys):
        write_module(tmp_path, "thing_service.py", SELF_MANAGING)

        assert main([str(tmp_path)]) == 1
        assert "thing_service.py::do_the_thing" in capsys.readouterr().out


class TestTheRealCodebase:
    def test_the_repository_passes_its_own_check(self, capsys):
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0, captured.out

    def test_the_default_scan_covers_the_entrypoints_too(self):
        """An entrypoint helper handed a UnitOfWork is as much an offender as a service function."""
        assert (DEFAULT_ROOT / "entrypoints").is_dir()
        assert (DEFAULT_ROOT / "service_layer").is_dir()


@pytest.mark.parametrize("source", [SELF_MANAGING, CALLER_MANAGES, ENTRYPOINT, NO_UOW])
def test_every_sample_module_parses(source):
    compile(source, "<sample>", "exec")
