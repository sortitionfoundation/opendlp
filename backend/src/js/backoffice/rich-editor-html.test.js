// ABOUTME: Tests for the visual editor's round-trip check, HTML normalisation and HTML layout.
// ABOUTME: Uses the starter intros, and the real intros and auto-replies in tests/fixtures/.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { createSchemaExtensions } from "./rich-editor-schema.js";
import {
  formatHtml,
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

const FIXTURE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/fixtures",
);
const INTRO_FIXTURE_DIR = resolve(FIXTURE_DIR, "registration_intros");
const AUTO_REPLY_FIXTURE_DIR = resolve(
  FIXTURE_DIR,
  "registration_auto_replies",
);

function fixture(name) {
  return readFileSync(resolve(INTRO_FIXTURE_DIR, `${name}.html`), "utf8");
}

function autoReplyFixture(name) {
  return readFileSync(resolve(AUTO_REPLY_FIXTURE_DIR, `${name}.html`), "utf8");
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

describe("styled spans (A8 in auto-reply-plan.md)", () => {
  it("keeps a span with a style, a class and a direction", () => {
    const html =
      '<p>a <span style="color: red;" class="x" dir="ltr">b</span> c</p>';
    expect(roundTripsCleanly(html, extensions)).toBe(true);
    const template = document.createElement("template");
    template.innerHTML = roundTrip(html, extensions);
    const span = template.content.querySelector("span");
    expect(span.getAttribute("style")).toBe("color: red;");
    expect(span.getAttribute("class")).toBe("x");
    expect(span.getAttribute("dir")).toBe("ltr");
  });

  it("still drops a bare span", () => {
    expect(roundTrip("<p><span>a</span></p>", extensions)).toBe("<p>a</p>");
    expect(roundTripsCleanly("<p><span>a</span></p>", extensions)).toBe(true);
  });

  it("keeps a span round bold text in that order", () => {
    const html = '<p><span style="color: red;"><strong>a</strong></span></p>';
    expect(roundTrip(html, extensions)).toBe(html);
  });

  it("accepts bold round a span when moving the span outside looks the same", () => {
    expect(
      roundTripsCleanly(
        '<p><strong><span style="color: red;">a</span></strong></p>',
        extensions,
      ),
    ).toBe(true);
  });

  it("accepts the un-bolding span inside <strong>, which the editor writes without the <strong>", () => {
    const html =
      '<p><strong><span style="font-weight: 400;">a</span></strong></p>';
    expect(roundTrip(html, extensions)).toBe(
      '<p><span style="font-weight: 400;">a</span></p>',
    );
    expect(roundTripsCleanly(html, extensions)).toBe(true);
  });

  it("refuses a span that the editor would move inside bold text it changes", () => {
    // font-weight: normal un-bolds the text, but the editor keeps the bold and
    // puts it inside the span, where it wins.
    expect(
      roundTripsCleanly(
        '<p><strong><span style="font-weight: normal;">a</span></strong></p>',
        extensions,
      ),
    ).toBe(false);
  });

  it("refuses a coloured span round a link, which the editor would put inside the link", () => {
    expect(
      roundTripsCleanly(
        '<p><span style="color: red;"><a href="/x">a</a></span></p>',
        extensions,
      ),
    ).toBe(false);
    expect(
      roundTripsCleanly(
        '<p><a href="/x"><span style="color: red;">a</span></a></p>',
        extensions,
      ),
    ).toBe(true);
  });

  it("refuses a span nested in a span, whose styles the editor merges", () => {
    expect(
      roundTripsCleanly(
        '<p><span style="color: red;">a<span style="font-size: 2em;">b</span></span></p>',
        extensions,
      ),
    ).toBe(false);
  });
});

describe("normaliseHtml with styled spans", () => {
  it("lets a span's font weight inside <strong> win over the <strong>", () => {
    expect(
      normaliseHtml(
        '<p><strong><span style="font-weight: 400;">a</span></strong></p>',
      ),
    ).toBe('<p><span style="font-weight: 400;">a</span></p>');
  });

  it("keeps the weight of a bold span inside <strong>", () => {
    expect(
      normaliseHtml(
        '<p><strong><span style="font-weight: 700;">a</span></strong></p>',
      ),
    ).toBe('<p><span style="font-weight: 700;">a</span></p>');
  });

  it("lets <strong> inside a span win over the span's font weight", () => {
    expect(
      normaliseHtml(
        '<p><span style="color: red; font-weight: 400;"><strong>a</strong></span></p>',
      ),
    ).toBe(
      normaliseHtml(
        '<p><span style="color: red;"><strong>a</strong></span></p>',
      ),
    );
  });

  it("lets <em> and a link inside a span win over its font style and colour", () => {
    expect(
      normaliseHtml(
        '<p><span style="font-style: normal; color: red;"><em><a href="/x">a</a></em></span></p>',
      ),
    ).toBe(
      normaliseHtml('<p><span style=""><em><a href="/x">a</a></em></span></p>'),
    );
  });

  it("lets a span inside <em> win over the <em> for font style", () => {
    expect(
      normaliseHtml(
        '<p><em><span style="font-style: normal;">a</span></em></p>',
      ),
    ).toBe('<p><span style="font-style: normal;">a</span></p>');
  });

  it("ignores which side of a span formatting it does not compete with sits", () => {
    expect(
      normaliseHtml('<p><u><span style="color: red;">a</span></u></p>'),
    ).toBe(normaliseHtml('<p><span style="color: red;"><u>a</u></span></p>'));
  });
});

describe("an editor without tables", () => {
  const withoutTables = createSchemaExtensions({ tables: false });

  it("refuses a table, which it would flatten into paragraphs", () => {
    expect(
      roundTripsCleanly("<table><tr><td>a</td></tr></table>", withoutTables),
    ).toBe(false);
  });

  it("accepts everything else", () => {
    expect(roundTripsCleanly(GOVUK_STARTER_INTRO, withoutTables)).toBe(true);
    expect(
      roundTripsCleanly(
        "<ul><li>a</li></ul><blockquote>b</blockquote><hr>",
        withoutTables,
      ),
    ).toBe(true);
  });
});

describe("the real auto-replies", () => {
  const emailExtensions = createSchemaExtensions({
    images: false,
    tables: false,
  });
  const names = [
    "default_auto_reply",
    "google_docs_list_auto_reply",
    "unbolded_span_auto_reply",
    "plain_list_auto_reply",
    "coloured_text_auto_reply",
    "placeholder_template_auto_reply",
  ];

  it("covers every fixture file", () => {
    const files = readdirSync(AUTO_REPLY_FIXTURE_DIR)
      .filter((file) => file.endsWith(".html"))
      .map((file) => file.replace(/\.html$/, ""));
    expect(files.sort()).toEqual([...names].sort());
  });

  it.each(names)("%s round-trips cleanly in the email editor", (name) => {
    expect(roundTripsCleanly(autoReplyFixture(name), emailExtensions)).toBe(
      true,
    );
  });

  it.each(names)("%s keeps its text and link addresses", (name) => {
    const html = autoReplyFixture(name);
    expect(contentOf(roundTrip(html, emailExtensions))).toEqual(
      contentOf(html),
    );
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

describe("formatHtml", () => {
  it("leaves a single paragraph as it is", () => {
    expect(formatHtml("<p>Hello</p>")).toBe("<p>Hello</p>");
  });

  it("gives an empty intro back empty", () => {
    expect(formatHtml("")).toBe("");
  });

  it("puts each top-level block on its own line", () => {
    expect(formatHtml("<h1>Title</h1><h2>Sub</h2><p>Text</p><hr>")).toBe(
      "<h1>Title</h1>\n<h2>Sub</h2>\n<p>Text</p>\n<hr>",
    );
  });

  it("indents a nested list by its nesting", () => {
    const html =
      "<h1>Hi</h1><ul><li><p>One <strong>two</strong></p>" +
      "<ul><li><p>x</p></li></ul></li></ul><hr>";
    expect(formatHtml(html)).toBe(
      [
        "<h1>Hi</h1>",
        "<ul>",
        "  <li>",
        "    <p>One <strong>two</strong></p>",
        "    <ul>",
        "      <li>",
        "        <p>x</p>",
        "      </li>",
        "    </ul>",
        "  </li>",
        "</ul>",
        "<hr>",
      ].join("\n"),
    );
  });

  it("lays out a table of images", () => {
    const html =
      '<table><tbody><tr><td><p><img src="/a.png" alt="a"></p></td>' +
      '<td><p><img src="/b.png" alt="b"></p></td></tr></tbody></table>';
    expect(formatHtml(html)).toBe(
      [
        "<table>",
        "  <tbody>",
        "    <tr>",
        "      <td>",
        '        <p><img src="/a.png" alt="a"></p>',
        "      </td>",
        "      <td>",
        '        <p><img src="/b.png" alt="b"></p>',
        "      </td>",
        "    </tr>",
        "  </tbody>",
        "</table>",
      ].join("\n"),
    );
  });

  it("lays out the GOV.UK wrapper divs and a blockquote", () => {
    const html =
      '<div class="govuk-grid-row"><div class="govuk-grid-column-two-thirds">' +
      '<h1 class="govuk-heading-xl">{{ assembly_title }}</h1>' +
      "<blockquote><p>Quoted</p></blockquote></div></div>";
    expect(formatHtml(html)).toBe(
      [
        '<div class="govuk-grid-row">',
        '  <div class="govuk-grid-column-two-thirds">',
        '    <h1 class="govuk-heading-xl">{{ assembly_title }}</h1>',
        "    <blockquote>",
        "      <p>Quoted</p>",
        "    </blockquote>",
        "  </div>",
        "</div>",
      ].join("\n"),
    );
  });

  it("keeps inline content byte-for-byte on one line", () => {
    const html =
      '<p>Dear {{ name }},<br>see <a href="/x" target="_blank">this</a> ' +
      '<em>and <strong>that</strong></em><img src="/i.png" alt="i">.</p>';
    expect(formatHtml(html)).toBe(html);
  });

  it("prints a block that mixes text and blocks as given", () => {
    const html = "<div>loose text<p>a</p></div>";
    expect(formatHtml(`<p>x</p>${html}`)).toBe(`<p>x</p>\n${html}`);
  });

  it("gives HTML whose top level is not all blocks back unchanged", () => {
    const html = "{% if x %}<p>a</p>{% endif %}";
    expect(formatHtml(html)).toBe(html);
  });

  it("keeps attributes in their order and escaping", () => {
    const html =
      '<div style="margin: 0 auto;" class="x" dir="ltr">' +
      '<p dir="ltr" style="color: red;">a</p>' +
      '<p><img src="/i.png" alt="A &quot;quoted&quot; logo"></p></div>';
    expect(formatHtml(html)).toBe(
      [
        '<div style="margin: 0 auto;" class="x" dir="ltr">',
        '  <p dir="ltr" style="color: red;">a</p>',
        '  <p><img src="/i.png" alt="A &quot;quoted&quot; logo"></p>',
        "</div>",
      ].join("\n"),
    );
  });

  it("escapes nothing in an attribute that the DOM left alone", () => {
    const html = '<div><p><img src="/i.png" alt="{{ a > b }}"></p></div>';
    expect(formatHtml(html)).toContain('alt="{{ a > b }}"');
  });

  it("is unchanged by formatting its own output again", () => {
    const formatted = formatHtml(
      roundTrip(fixture("centred_image_intro"), extensions),
    );
    expect(formatHtml(formatted)).toBe(formatted);
  });

  it.each([
    ["the plain starter intro", PLAIN_STARTER_INTRO],
    ["the GOV.UK starter intro", GOVUK_STARTER_INTRO],
    [
      "a nested list",
      "<ul><li>a<ul><li>b</li></ul></li></ul><ol><li>c</li></ol>",
    ],
    ["a table", "<table><tr><th>a</th><td>b<br>c</td></tr></table>"],
    ["a quote and a rule", "<blockquote>q</blockquote><hr><p>a<br>b</p>"],
    ["inline_styles_intro", fixture("inline_styles_intro")],
    ["centred_image_intro", fixture("centred_image_intro")],
    ["layout_table_intro", fixture("layout_table_intro")],
  ])("loses nothing in the visual editor for %s", (_name, html) => {
    const visual = roundTrip(html, extensions);
    const formatted = formatHtml(visual);
    expect(formatted).not.toBe(visual);
    expect(roundTrip(formatted, extensions)).toBe(visual);
    expect(roundTripsCleanly(formatted, extensions)).toBe(true);
  });
});
