"""ABOUTME: Tests for the UnitOfWork convention checker
ABOUTME: The checker blocks new self-managing service functions while the known ones are migrated"""

import pathlib

import pytest

from scripts.check_uow_convention import DEFAULT_ALLOWLIST, SEEDED_COUNT, find_self_managing, load_allowlist, main

SELF_MANAGING = '''
def do_the_thing(uow, thing_id):
    """Opens its own context, which is what we are migrating away from."""
    with uow:
        uow.things.get(thing_id)
'''

CALLER_MANAGES = '''
def do_the_thing(uow, thing_id):
    """The caller is expected to manage the `uow` context (`with uow: ...`)."""
    return uow.things.get(thing_id)
'''

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

    def test_ignores_a_with_block_that_is_not_a_unit_of_work(self, tmp_path):
        write_module(tmp_path, "thing_service.py", NO_UOW)

        assert find_self_managing(tmp_path) == set()

    def test_reports_nested_helpers(self, tmp_path):
        write_module(tmp_path, "pkg/thing_service.py", SELF_MANAGING)

        assert find_self_managing(tmp_path) == {"pkg/thing_service.py::do_the_thing"}


class TestLoadAllowlist:
    def test_skips_comments_and_blank_lines(self, tmp_path):
        path = tmp_path / "known.txt"
        path.write_text("# a comment\n\nthing_service.py::do_the_thing\n")

        assert load_allowlist(path) == {"thing_service.py::do_the_thing"}

    def test_a_missing_file_is_an_empty_allowlist(self, tmp_path):
        assert load_allowlist(tmp_path / "absent.txt") == set()


class TestMain:
    def test_passes_when_every_offender_is_allowlisted(self, tmp_path, capsys):
        write_module(tmp_path, "thing_service.py", SELF_MANAGING)
        allowlist = tmp_path / "known.txt"
        allowlist.write_text("thing_service.py::do_the_thing\n")

        assert main([str(tmp_path), "--allowlist", str(allowlist)]) == 0

    def test_fails_on_a_new_offender(self, tmp_path, capsys):
        write_module(tmp_path, "thing_service.py", SELF_MANAGING)
        allowlist = tmp_path / "known.txt"
        allowlist.write_text("")

        assert main([str(tmp_path), "--allowlist", str(allowlist)]) == 1
        assert "thing_service.py::do_the_thing" in capsys.readouterr().out

    def test_fails_on_a_stale_allowlist_entry(self, tmp_path, capsys):
        """The allowlist is a ratchet: a migrated function must be removed from it."""
        write_module(tmp_path, "thing_service.py", CALLER_MANAGES)
        allowlist = tmp_path / "known.txt"
        allowlist.write_text("thing_service.py::do_the_thing\n")

        assert main([str(tmp_path), "--allowlist", str(allowlist)]) == 1
        assert "no longer" in capsys.readouterr().out


class TestTheRealCodebase:
    """The checked-in allowlist must match the codebase exactly."""

    def test_the_repository_passes_its_own_check(self, capsys):
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0, captured.out

    def test_the_allowlist_shrinks_to_nothing(self):
        """A reminder that phase 3 deletes this file - and a check it is not growing."""
        assert len(load_allowlist(DEFAULT_ALLOWLIST)) <= SEEDED_COUNT


@pytest.mark.parametrize("source", [SELF_MANAGING, CALLER_MANAGES, NO_UOW])
def test_every_sample_module_parses(source):
    compile(source, "<sample>", "exec")
