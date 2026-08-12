// ABOUTME: Alpine magic $confirm and directive x-preserve-scroll-on-submit for form submissions
// ABOUTME: Confirms before submitting and optionally carries the scroll position into the reload

import { urlSetParam } from "../lib/url-utils.js";

/**
 * Add the current scroll position to a form's action URL.
 *
 * @param {HTMLFormElement} formElement - the form about to be submitted
 */
export function addScrollToFormAction(formElement) {
  var action = formElement.getAttribute("action") || window.location.href;
  var scrollPos = Math.round(window.scrollY);
  formElement.setAttribute(
    "action",
    urlSetParam(action, "scroll", scrollPos.toString()),
  );
}

/**
 * Register the confirmation magic and the scroll-preserving submit directive.
 *
 * Call from an alpine:init listener.
 */
export function registerFormConfirm() {
  /**
   * Confirmation magic helper for form submissions
   *
   * Shows a confirmation dialog before submitting a form. Designed for CSP-safe
   * Alpine.js usage. Supports scroll preservation via data-preserve-scroll attribute.
   *
   * Usage:
   *   <form x-data @submit.prevent="$confirm('Are you sure?', $el)">
   *
   *   With scroll preservation:
   *   <form x-data data-preserve-scroll @submit.prevent="$confirm('Are you sure?', $el)">
   */
  Alpine.magic("confirm", function () {
    return function (message, formElement) {
      if (confirm(message)) {
        // Check if scroll preservation is requested
        if (formElement.hasAttribute("data-preserve-scroll")) {
          addScrollToFormAction(formElement);
        }
        formElement.submit();
      }
    };
  });

  /**
   * Scroll preservation directive for form submissions
   *
   * Automatically adds scroll position to form action URL on submit.
   * Use this for forms that don't use confirmation dialogs.
   *
   * Usage:
   *   <form method="post" action="..." x-data x-preserve-scroll-on-submit>
   */
  Alpine.directive("preserve-scroll-on-submit", function (el) {
    el.addEventListener("submit", function () {
      addScrollToFormAction(el);
    });
  });
}
