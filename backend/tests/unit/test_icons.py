"""ABOUTME: Guards that templates draw icons through the shared macros rather than inline SVG
ABOUTME: A fresh copy-pasted <svg> is how the backoffice ended up with three bins and three ticks"""

import re
from pathlib import Path

from opendlp import config

SVG_RE = re.compile(r"<svg\b")

# Files allowed to hold a raw <svg>, and why. Everything else draws its icons
# through backoffice/components/icons.html.
ALLOWED: dict[str, str] = {
    "backoffice/components/icons.html": "the shared icon set itself",
    "components/brand_marks.html": "vendor trademarks, reproduced to their own brand guidelines",
    "backoffice/components/navigation.html": "the Sortition Foundation logo, drawn once",
    "backoffice/components/button.html": "an <svg> inside a macro docstring, not markup",
    "backoffice/service_docs/_registration.html": "arrows drawn as parts of a flow diagram",
    "main/index.html": "decorative shapes in the public landing page banner",
    # GOV.UK Frontend prescribes this pagination markup, arrows included. Three
    # templates hand-roll it instead of using components/pagination.html, which
    # is worth fixing on its own terms - but not by restyling GOV.UK's arrows.
    "admin/users.html": "GOV.UK pagination component markup",
    "main/view_assembly_data.html": "GOV.UK pagination component markup",
    "respondents/view_respondents.html": "GOV.UK pagination component markup",
}


def _templates_with_raw_svg(templates_path: Path) -> set[str]:
    found = set()
    for template in sorted(templates_path.rglob("*.html")):
        if SVG_RE.search(template.read_text()):
            found.add(str(template.relative_to(templates_path)))
    return found


def _icon_macro_names(icons_file: Path) -> set[str]:
    return set(re.findall(r"\{%\s*macro\s+(icon_[a-z0-9_]+)", icons_file.read_text()))


def test_scan_finds_raw_svg(tmp_path: Path) -> None:
    """The scanner spots an inline <svg> and ignores a template without one."""
    (tmp_path / "drawn.html").write_text('<span><svg viewBox="0 0 24 24"></svg></span>')
    (tmp_path / "clean.html").write_text("<span>{{ icon_user() }}</span>")
    assert _templates_with_raw_svg(tmp_path) == {"drawn.html"}


def test_icons_file_defines_the_shared_set() -> None:
    """The shared set exists and holds the icons the backoffice actually draws."""
    icons_file = config.get_templates_path() / "backoffice" / "components" / "icons.html"
    assert icons_file.is_file()
    names = _icon_macro_names(icons_file)
    assert len(names) > 25
    assert {"icon_user", "icon_check", "icon_copy", "icon_chevron_down"} <= names


def test_every_icon_macro_is_decorative() -> None:
    """A glyph never carries the accessible name - the control wrapping it does.

    Without aria-hidden a screen reader announces the raw <svg> alongside the
    label its button already provides, so the action is read out twice.
    """
    icons_file = config.get_templates_path() / "backoffice" / "components" / "icons.html"
    bodies = re.findall(r"\{%\s*macro\s+icon_[a-z0-9_]+.*?\{%\s*endmacro\s*%\}", icons_file.read_text(), re.DOTALL)
    assert len(bodies) == len(_icon_macro_names(icons_file))
    missing = [body.split("%}")[0] for body in bodies if 'aria-hidden="true"' not in body]
    assert not missing, f"icon macros without aria-hidden: {missing}"


def test_templates_draw_icons_through_the_shared_macros() -> None:
    """An inline <svg> is invisible to anyone looking for an existing icon to reuse.

    That is how one product came to hold three bins, three ticks and three info
    circles. Add a macro to backoffice/components/icons.html and call it, or -
    if the drawing genuinely is not an icon - add the file to ALLOWED with a
    reason.
    """
    stray = _templates_with_raw_svg(config.get_templates_path()) - set(ALLOWED)
    assert not stray, (
        f"Templates hold a raw <svg> instead of calling a macro from backoffice/components/icons.html: {sorted(stray)}"
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted file that no longer holds an <svg> should leave the list."""
    drawn = _templates_with_raw_svg(config.get_templates_path())
    stale = set(ALLOWED) - drawn
    assert not stale, f"ALLOWED names templates that no longer hold an <svg>: {sorted(stale)}"
