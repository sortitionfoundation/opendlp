// ABOUTME: Decides whether HTML can go through the visual editor without losing anything.
// ABOUTME: Compares the HTML with its round trip after normalising both, and lays out the HTML it saves.
import { generateHTML, generateJSON } from "@tiptap/core";

const BLOCK_TAGS = [
  "address",
  "article",
  "aside",
  "blockquote",
  "caption",
  "col",
  "colgroup",
  "dd",
  "div",
  "dl",
  "dt",
  "figure",
  "footer",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "header",
  "hr",
  "li",
  "ol",
  "p",
  "section",
  "table",
  "tbody",
  "td",
  "tfoot",
  "th",
  "thead",
  "tr",
  "ul",
];
const VOID_TAGS = new Set(["br", "col", "hr", "img", "wbr"]);
const SAME_AS = { b: "strong", i: "em", del: "s", strike: "s" };
// The editor wraps the text of these in a <p>, since their content is blocks.
const WRAPS_TEXT_IN_PARAGRAPH = new Set(["li", "td", "th", "blockquote"]);
const DROPPED_WHEN_EMPTY = new Set(["strong", "em", "span"]);
const BLOCK_EDGE_SPACE = new RegExp(
  ` ?(</?(?:${BLOCK_TAGS.join("|")})(?: [^>]*)?>) ?`,
  "g",
);

function escapeText(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\u00a0/g, "&nbsp;");
}

function escapeAttribute(value) {
  return escapeText(value).replace(/"/g, "&quot;");
}

function canonicalStyle(value) {
  const probe = document.createElement("span");
  probe.setAttribute("style", value);
  return probe.style.cssText;
}

function serialiseAttributes(element) {
  return Array.from(element.attributes)
    .map(({ name, value }) => [
      name,
      name === "style" ? canonicalStyle(value) : value,
    ])
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, value]) => ` ${name}="${escapeAttribute(value)}"`)
    .join("");
}

function isBlock(node) {
  return (
    node.nodeType === Node.ELEMENT_NODE &&
    BLOCK_TAGS.includes(node.tagName.toLowerCase())
  );
}

function canonicalTag(element) {
  const raw = element.tagName.toLowerCase();
  return SAME_AS[raw] || raw;
}

function firstMeaningfulChild(element) {
  return Array.from(element.childNodes).find(
    (child) =>
      child.nodeType !== Node.TEXT_NODE || child.textContent.trim() !== "",
  );
}

function blockContent(element, tag) {
  const children = Array.from(element.childNodes);
  const first = firstMeaningfulChild(element);
  if (
    WRAPS_TEXT_IN_PARAGRAPH.has(tag) &&
    first &&
    first.nodeType === Node.ELEMENT_NODE &&
    first.tagName === "P" &&
    first.attributes.length === 0
  ) {
    return children.flatMap((child) =>
      child === first ? Array.from(child.childNodes) : [child],
    );
  }
  return children;
}

function serialiseBlock(element) {
  const tag = canonicalTag(element);
  const attributes = serialiseAttributes(element);
  if (VOID_TAGS.has(tag)) {
    return `<${tag}${attributes}>`;
  }
  return `<${tag}${attributes}>${serialiseFlow(blockContent(element, tag))}</${tag}>`;
}

// Inline content becomes runs of {content, marks}, so the nesting order of
// formatting (<strong><a> versus <a><strong>) makes no difference.
function collectRuns(node, marks, runs) {
  if (node.nodeType === Node.TEXT_NODE) {
    runs.push({
      text: escapeText(node.textContent.replace(/[ \t\n\r\f]+/g, " ")),
      marks,
    });
    return;
  }
  if (node.nodeType === Node.COMMENT_NODE) {
    runs.push({ atom: `<!--${node.textContent}-->`, marks });
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }
  const tag = canonicalTag(node);
  const attributes = serialiseAttributes(node);
  if (isBlock(node)) {
    runs.push({ atom: serialiseBlock(node), marks });
  } else if (VOID_TAGS.has(tag)) {
    runs.push({ atom: `<${tag}${attributes}>`, marks });
  } else {
    const inner =
      tag === "span" && !attributes
        ? marks
        : [...marks, { open: `<${tag}${attributes}>`, close: `</${tag}>` }];
    const before = runs.length;
    node.childNodes.forEach((child) => collectRuns(child, inner, runs));
    if (runs.length === before && !DROPPED_WHEN_EMPTY.has(tag)) {
      runs.push({ atom: `<${tag}${attributes}></${tag}>`, marks });
    }
  }
}

function marksKey(marks) {
  return marks
    .map((mark) => mark.open)
    .sort()
    .join("");
}

function serialiseRuns(runs) {
  const merged = [];
  for (const run of runs) {
    const previous = merged[merged.length - 1];
    if (
      previous &&
      run.text !== undefined &&
      previous.text !== undefined &&
      marksKey(previous.marks) === marksKey(run.marks)
    ) {
      previous.text += run.text;
    } else {
      merged.push({ ...run });
    }
  }
  return merged
    .filter((run) => run.atom !== undefined || run.text !== "")
    .map((run) => {
      const marks = [...run.marks].sort((a, b) => a.open.localeCompare(b.open));
      const opens = marks.map((mark) => mark.open).join("");
      const closes = marks
        .map((mark) => mark.close)
        .reverse()
        .join("");
      return `${opens}${run.atom !== undefined ? run.atom : run.text}${closes}`;
    })
    .join("");
}

function serialiseFlow(nodes) {
  let output = "";
  let inline = [];
  const flush = () => {
    const runs = [];
    inline.forEach((node) => collectRuns(node, [], runs));
    output += serialiseRuns(runs);
    inline = [];
  };
  for (const node of nodes) {
    if (isBlock(node)) {
      flush();
      output += serialiseBlock(node);
    } else {
      inline.push(node);
    }
  }
  flush();
  return output;
}

/**
 * A canonical form of `html` in which differences that render the same are
 * erased: attribute order, style spelling, whitespace between blocks, `<b>`
 * for `<strong>`, `<del>` for `<s>`, attribute-less `<span>`s, empty
 * `<strong>`/`<em>`, and the text of a list item, table cell or blockquote
 * being wrapped in a `<p>`.
 */
export function normaliseHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  return serialiseFlow(Array.from(template.content.childNodes))
    .replace(/ +/g, " ")
    .replace(BLOCK_EDGE_SPACE, "$1")
    .trim();
}

function isWhitespaceText(node) {
  return node.nodeType === Node.TEXT_NODE && node.textContent.trim() === "";
}

function startTag(element) {
  const shell = element.cloneNode(false).outerHTML;
  return shell.slice(0, shell.lastIndexOf("</"));
}

function formatBlock(element, depth) {
  const indent = "  ".repeat(depth);
  const children = Array.from(element.childNodes).filter(
    (child) => !isWhitespaceText(child),
  );
  if (
    VOID_TAGS.has(element.tagName.toLowerCase()) ||
    children.length === 0 ||
    !children.every(isBlock)
  ) {
    return [indent + element.outerHTML];
  }
  const tag = element.tagName.toLowerCase();
  return [
    indent + startTag(element),
    ...children.flatMap((child) => formatBlock(child, depth + 1)),
    `${indent}</${tag}>`,
  ];
}

/**
 * `html` laid out one block per line, indented by nesting. A block holding
 * inline content keeps that content exactly as given, on one line; so does a
 * block that mixes inline content and blocks. HTML whose top level is not all
 * blocks comes back unchanged.
 */
export function formatHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const nodes = Array.from(template.content.childNodes).filter(
    (node) => !isWhitespaceText(node),
  );
  if (!nodes.every(isBlock)) {
    return html;
  }
  return nodes.flatMap((node) => formatBlock(node, 0)).join("\n");
}

/** `html` as the visual editor would hand it back, before any editing. */
export function roundTrip(html, extensions) {
  return generateHTML(generateJSON(html, extensions), extensions);
}

/** True when `html` survives a trip through the visual editor unchanged (once normalised). */
export function roundTripsCleanly(html, extensions) {
  if (html.trim() === "") {
    return true;
  }
  return normaliseHtml(html) === normaliseHtml(roundTrip(html, extensions));
}
