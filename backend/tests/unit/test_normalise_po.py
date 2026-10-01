"""ABOUTME: Tests for the gettext catalogue normaliser behind the pre-commit hook and translate-accept-fuzzy
ABOUTME: Covers rewrapping another tool's output, idempotence, fuzzy acceptance and the hook's exit code"""

import pathlib
import subprocess

from babel.messages.pofile import read_po

from scripts.normalise_po import main, normalise

HEADER = """\
# Hungarian translations for PROJECT.
#
msgid ""
msgstr ""
"Project-Id-Version: PROJECT VERSION\\n"
"Language: hu\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=utf-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"
"""

# A long entry wrapped the way gettext's tools do it: the space stays at the end
# of the line, and the line runs to 79 columns.
GETTEXT_WRAPPED = (
    HEADER
    + """
#: src/opendlp/example.py:1
msgid "You can create assemblies. You can see the assemblies you have been added to, and the ones you create."
msgstr ""
"Létrehozhatsz közösségi gyűléseket. Láthatod azokat a gyűléseket, amelyekhez "
"hozzáadtak, és azokat, amelyeket te hoztál létre."

#: src/opendlp/example.py:2
#, fuzzy
msgid "Optional"
msgstr "Nem kötelező"

#: src/opendlp/example.py:3
msgid "Required"
msgstr "Kötelező"
"""
)


def write_catalogue(tmp_path: pathlib.Path, text: str = GETTEXT_WRAPPED) -> pathlib.Path:
    path = tmp_path / "messages.po"
    path.write_text(text, encoding="utf-8")
    return path


def entries(path: pathlib.Path) -> dict[str, tuple[str, bool]]:
    with path.open("rb") as handle:
        catalog = read_po(handle)
    return {message.id: (message.string, message.fuzzy) for message in catalog if message.id}


def test_rewraps_another_tools_output_and_keeps_every_translation(tmp_path):
    path = write_catalogue(tmp_path)
    before = entries(path)

    assert normalise(path) is True

    text = path.read_text(encoding="utf-8")
    assert all(len(line) <= 76 for line in text.splitlines()), "a line is wider than Babel's 76 columns"
    assert '"Létrehozhatsz közösségi gyűléseket. Láthatod azokat a gyűléseket, amelyekhez "' not in text
    assert entries(path) == before


def test_is_idempotent_and_ends_with_a_single_newline(tmp_path):
    path = write_catalogue(tmp_path)
    normalise(path)
    once = path.read_bytes()

    assert normalise(path) is False
    assert path.read_bytes() == once
    assert once.endswith(b"\n") and not once.endswith(b"\n\n")


def test_matches_what_pybabel_update_writes(tmp_path):
    """The hook must leave translate-regen's own output alone, or every regen would trip it."""
    pot = tmp_path / "messages.pot"
    pot.write_text(GETTEXT_WRAPPED.replace('"Language: hu\\n"\n', ""), encoding="utf-8")
    po_dir = tmp_path / "hu" / "LC_MESSAGES"
    po_dir.mkdir(parents=True)
    path = write_catalogue(po_dir)
    subprocess.run(  # noqa: S603 - a fixed pybabel command over files this test wrote
        [
            "pybabel",
            "update",
            "--ignore-obsolete",
            "--no-fuzzy-matching",
            f"--input-file={pot}",
            f"--output-dir={tmp_path}",
        ],
        check=True,
        capture_output=True,
    )
    # translate-regen runs end-of-file-fixer after pybabel update, which is the
    # one difference: pybabel leaves a blank line after the last entry.
    written = path.read_bytes().rstrip(b"\n") + b"\n"

    normalise(path)

    assert path.read_bytes() == written
    assert normalise(path) is False


def test_accept_fuzzy_clears_the_flags_and_keeps_the_translations(tmp_path):
    path = write_catalogue(tmp_path)

    assert normalise(path, accept_fuzzy=True) is True

    assert entries(path)["Optional"] == ("Nem kötelező", False)
    assert entries(path)["Required"] == ("Kötelező", False)
    assert "#, fuzzy" not in path.read_text(encoding="utf-8")


def test_the_pot_files_fuzzy_header_survives(tmp_path):
    """pybabel extract flags the POT header fuzzy; that is the template's marker, not a translation to accept."""
    pot = tmp_path / "messages.pot"
    pot.write_text(
        GETTEXT_WRAPPED.replace('"Language: hu\\n"\n', "").replace("#\nmsgid", "#\n#, fuzzy\nmsgid"), encoding="utf-8"
    )

    normalise(pot)

    assert pot.read_text(encoding="utf-8").startswith("# Hungarian translations for PROJECT.\n#\n#, fuzzy\nmsgid")


def test_main_fails_only_when_asked_to_and_a_file_changed(tmp_path, capsys):
    path = write_catalogue(tmp_path)

    assert main([str(path)]) == 0
    assert f"normalised {path}" in capsys.readouterr().out
    assert main([str(path), "--fail-if-changed"]) == 0

    path.write_text(GETTEXT_WRAPPED, encoding="utf-8")
    assert main([str(path), "--fail-if-changed"]) == 1


# What the /translate skill writes through gettext-auto and polib: 78-column
# wrapping with the space carried to the next line, a fuzzy flag on each new
# translation, plural forms, and an extracted comment for a failed entry.
GETTEXT_AUTO_WRAPPED = (
    HEADER
    + """
#: src/opendlp/example.py:1
#, fuzzy
msgid ""
"You can create assemblies. You can see the assemblies you have been added "
"to, and the ones you create."
msgstr ""
"Létrehozhatsz közösségi gyűléseket. Láthatod azokat a gyűléseket, amelyekhez"
" hozzáadtak, és azokat, amelyeket te hoztál létre."

#, fuzzy, python-format
msgid "%(count)d question"
msgid_plural "%(count)d questions"
msgstr[0] "%(count)d kérdés"
msgstr[1] "%(count)d kérdés"

#. AUTOTRANS-ERROR: placeholder mismatch
msgid "Required"
msgstr ""
"""
)


def test_keeps_everything_the_translate_skill_writes(tmp_path):
    path = write_catalogue(tmp_path, GETTEXT_AUTO_WRAPPED)

    assert normalise(path) is True

    with path.open("rb") as handle:
        catalog = read_po(handle)
    long_entry = catalog.get(
        "You can create assemblies. You can see the assemblies you have been added to, and the ones you create."
    )
    assert long_entry.fuzzy
    assert long_entry.string.startswith("Létrehozhatsz közösségi gyűléseket.")
    plural = catalog.get("%(count)d question")
    assert plural.string == ("%(count)d kérdés", "%(count)d kérdés")
    assert plural.flags == {"fuzzy", "python-format"}
    assert catalog.get("Required").auto_comments == ["AUTOTRANS-ERROR: placeholder mismatch"]
    assert "#. AUTOTRANS-ERROR: placeholder mismatch" in path.read_text(encoding="utf-8")
