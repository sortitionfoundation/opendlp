// ABOUTME: Tests for the visual editor's round-trip check and HTML normalisation.
// ABOUTME: Uses the starter intros and the real intros in tests/fixtures/registration_intros/.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { createSchemaExtensions } from "./rich-editor-schema.js";
import {
  normaliseHtml,
  roundTrip,
  roundTripsCleanly,
} from "./rich-editor-html.js";

const extensions = createSchemaExtensions();

const PLAIN_STARTER_INTRO =
  "<h1>{{ assembly_title }}</h1>\n<p>{{ assembly_question }}</p>\n";
const GOVUK_STARTER_INTRO = [
  '<div class="govuk-grid-row">',
  '<div class="govuk-grid-column-two-thirds" style="float: none; margin: 0 auto;">',
  '<h1 class="govuk-heading-xl">{{ assembly_title }}</h1>',
  '<p class="govuk-body">{{ assembly_question }}</p>',
  "</div>",
  "</div>",
].join("\n");

const INTRO_FIXTURE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/fixtures/registration_intros",
);

function fixture(name) {
  return readFileSync(resolve(INTRO_FIXTURE_DIR, `${name}.html`), "utf8");
}

function contentOf(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const root = template.content;
  return {
    // Whitespace between blocks disappears in the round trip; the words must not.
    text: root.textContent.replace(/[ \t\n\r\f]+/g, ""),
    hrefs: Array.from(root.querySelectorAll("a"), (a) =>
      a.getAttribute("href"),
    ),
    srcs: Array.from(root.querySelectorAll("img"), (img) =>
      img.getAttribute("src"),
    ),
  };
}

describe("normaliseHtml", () => {
  it("ignores attribute order and how a style is spelt", () => {
    expect(normaliseHtml('<p style="margin: 0 auto" class="x">a</p>')).toBe(
      normaliseHtml('<p class="x" style="margin: 0px auto;">a</p>'),
    );
  });

  it("ignores whitespace between blocks but keeps it inside text", () => {
    expect(normaliseHtml("<p>a b</p>\n\n<p>c</p>\n")).toBe(
      "<p>a b</p><p>c</p>",
    );
  });

  it("treats &nbsp; and a literal no-break space as the same", () => {
    expect(normaliseHtml("<p>a&nbsp;b</p>")).toBe(
      normaliseHtml("<p>a\u00a0b</p>"),
    );
  });

  it("treats <b> and <i> as <strong> and <em>", () => {
    expect(normaliseHtml("<p><b>a</b><i>b</i></p>")).toBe(
      "<p><strong>a</strong><em>b</em></p>",
    );
  });

  it("drops attribute-less spans and empty formatting", () => {
    expect(normaliseHtml("<p><span>a</span><strong></strong></p>")).toBe(
      "<p>a</p>",
    );
  });

  it("keeps a span that has attributes, and an empty anchor", () => {
    expect(
      normaliseHtml('<p><span style="color: red;">a</span></p>'),
    ).toContain("<span");
    expect(normaliseHtml('<p><a id="top"></a>a</p>')).toContain('<a id="top">');
  });

  it("treats a list item's text with or without a wrapping <p> as the same", () => {
    expect(normaliseHtml("<ul><li>a</li></ul>")).toBe(
      normaliseHtml("<ul><li><p>a</p></li></ul>"),
    );
  });

  it("treats a table cell's or blockquote's text with or without a wrapping <p> as the same", () => {
    expect(normaliseHtml("<table><tr><td>a</td></tr></table>")).toBe(
      normaliseHtml("<table><tr><td><p>a</p></td></tr></table>"),
    );
    expect(normaliseHtml("<blockquote>a</blockquote>")).toBe(
      normaliseHtml("<blockquote><p>a</p></blockquote>"),
    );
  });

  it("treats <del> and <strike> as <s>", () => {
    expect(normaliseHtml("<p><del>a</del><strike>b</strike></p>")).toBe(
      "<p><s>ab</s></p>",
    );
  });

  it("ignores the nesting order of formatting", () => {
    expect(normaliseHtml('<p><strong><a href="/x">a</a></strong></p>')).toBe(
      normaliseHtml('<p><a href="/x"><strong>a</strong></a></p>'),
    );
  });

  it("still tells different text apart", () => {
    expect(normaliseHtml("<p>a</p>")).not.toBe(normaliseHtml("<p>b</p>"));
  });
});

describe("roundTripsCleanly", () => {
  it("accepts both starter intros and an empty intro", () => {
    expect(roundTripsCleanly(PLAIN_STARTER_INTRO, extensions)).toBe(true);
    expect(roundTripsCleanly(GOVUK_STARTER_INTRO, extensions)).toBe(true);
    expect(roundTripsCleanly("", extensions)).toBe(true);
    expect(roundTripsCleanly("  \n", extensions)).toBe(true);
  });

  it("refuses elements the visual editor cannot hold", () => {
    expect(
      roundTripsCleanly(
        '<p><span style="color: red;">a</span></p>',
        extensions,
      ),
    ).toBe(false);
    expect(roundTripsCleanly("<h4>a</h4>", extensions)).toBe(false);
    expect(roundTripsCleanly("<!-- note --><p>a</p>", extensions)).toBe(false);
  });

  it("accepts underline, strikethrough, blockquotes and horizontal rules", () => {
    expect(
      roundTripsCleanly(
        "<p><u>a</u><s>b</s><del>c</del><strike>d</strike></p>",
        extensions,
      ),
    ).toBe(true);
    expect(
      roundTripsCleanly("<blockquote>quoted</blockquote>", extensions),
    ).toBe(true);
    expect(
      roundTripsCleanly('<p>a</p><hr class="x"><p>b</p>', extensions),
    ).toBe(true);
  });

  it("accepts a plain table, keeping its attributes and spans", () => {
    const html =
      '<table border="0" role="presentation" style="width: 100%">' +
      '<tr><td colspan="2" style="text-align: center"><img src="/a.png" alt="a"></td></tr>' +
      "<tr><th>b</th><td><p>c</p></td></tr></table>";
    expect(roundTripsCleanly(html, extensions)).toBe(true);
  });

  it("writes a table without the colgroup and sizing Tiptap adds by default", () => {
    expect(
      roundTrip("<table><tr><td>a</td><td>b</td></tr></table>", extensions),
    ).toBe(
      "<table><tbody><tr><td><p>a</p></td><td><p>b</p></td></tr></tbody></table>",
    );
  });

  it("refuses table parts the editor drops", () => {
    for (const html of [
      "<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>a</td></tr></tbody></table>",
      "<table><caption>c</caption><tr><td>a</td></tr></table>",
      '<table><colgroup><col style="width: 50%"></colgroup><tr><td>a</td></tr></table>',
      '<table><tr><td width="50%">a</td></tr></table>',
    ]) {
      expect(roundTripsCleanly(html, extensions)).toBe(false);
    }
  });

  it("refuses an inline data: image, which the editor drops", () => {
    expect(
      roundTripsCleanly(
        '<p><img src="data:image/png;base64,AAAA"></p>',
        extensions,
      ),
    ).toBe(false);
  });

  it("refuses text outside any block, such as a bare Jinja tag", () => {
    expect(roundTripsCleanly("{% if x %}<p>a</p>{% endif %}", extensions)).toBe(
      false,
    );
  });

  it("keeps a variable in a link address or image source", () => {
    const html =
      '<p><a href="{{ url }}">a</a><img src="{{ logo }}" alt=""></p>';
    expect(roundTripsCleanly(html, extensions)).toBe(true);
  });

  it("does not add target or rel to links that had none", () => {
    expect(roundTrip('<p><a href="/x">a</a></p>', extensions)).toBe(
      '<p><a href="/x">a</a></p>',
    );
  });

  it("keeps an image inside its paragraph", () => {
    expect(
      roundTrip(
        '<p>a<img src="/i.png" alt="logo" width="10">b</p>',
        extensions,
      ),
    ).toBe('<p>a<img src="/i.png" alt="logo" width="10">b</p>');
  });
});

describe("the real intros", () => {
  it.each(["inline_styles_intro", "centred_image_intro"])(
    "%s round-trips cleanly",
    (name) => {
      expect(roundTripsCleanly(fixture(name), extensions)).toBe(true);
    },
  );

  it("layout_table_intro falls back to HTML because the editor drops its colgroup", () => {
    const html = fixture("layout_table_intro");
    expect(roundTripsCleanly(html, extensions)).toBe(false);
    expect(html).toContain("<colgroup");
    const visual = roundTrip(html, extensions);
    expect(visual).toContain("<table");
    expect(visual).not.toContain("<colgroup");
    expect(
      normaliseHtml(html.replace(/<colgroup>[\s\S]*?<\/colgroup>/, "")),
    ).toBe(normaliseHtml(visual));
  });

  it.each(["inline_styles_intro", "centred_image_intro", "layout_table_intro"])(
    "%s keeps its text, link addresses and image sources",
    (name) => {
      const html = fixture(name);
      expect(contentOf(roundTrip(html, extensions))).toEqual(contentOf(html));
    },
  );
});
