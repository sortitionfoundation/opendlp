// ABOUTME: DOM helpers shared by the bulk targets editor's form and category components
// ABOUTME: Placeholder substitution in cloned markup, and re-issuing category sort order

// Categories are ten apart, matching SORT_ORDER_STEP in service_layer/constants.py,
// so a later drag-and-drop reorder can slot between two without renumbering.
export var SORT_ORDER_STEP = 10;

/**
 * Replace a placeholder in every name and id beneath a cloned element.
 *
 * Descends into nested `<template>` elements too: a cloned category block
 * carries the template its own rows are cloned from, and that template's markup
 * needs the same substitution or the rows it produces are named for a category
 * that never existed.
 *
 * @param {Element} root - the cloned element to rewrite in place
 * @param {string} placeholder - the text to replace, e.g. "__ID__"
 * @param {string} value - what to put in its place
 */
export function applyPlaceholder(root, placeholder, value) {
  rewrite(root, placeholder, value);
  root.querySelectorAll("[name], [id], [for]").forEach(function (el) {
    rewrite(el, placeholder, value);
  });
  root.querySelectorAll("template").forEach(function (template) {
    Array.prototype.slice
      .call(template.content.children)
      .forEach(function (child) {
        applyPlaceholder(child, placeholder, value);
      });
  });
}

/**
 * Substitute the placeholder in one element's own name, id and label target.
 *
 * `for` is rewritten alongside the others: a cloned block whose labels still
 * point at the placeholder id names nothing, which costs screen reader users
 * the field label and everyone the click-the-label target.
 *
 * @param {Element} el - the element to rewrite
 * @param {string} placeholder - the text to replace
 * @param {string} value - what to put in its place
 */
function rewrite(el, placeholder, value) {
  if (el.name) el.name = el.name.replace(placeholder, value);
  if (el.id) el.id = el.id.replace(placeholder, value);
  if (el.htmlFor) el.htmlFor = el.htmlFor.replace(placeholder, value);
}

/**
 * Re-issue sort_order across every category block in a container.
 *
 * Sent for all of them because `reorder_target_categories` requires the
 * complete set - a partial ordering would let a stale block drift.
 *
 * @param {Element} container - the element holding the category blocks
 */
export function renumberSortOrder(container) {
  if (!container) return;
  var blocks = container.children;
  for (var i = 0; i < blocks.length; i++) {
    var field = blocks[i].querySelector("[data-sort-order]");
    if (field) field.value = String((i + 1) * SORT_ORDER_STEP);
  }
}
