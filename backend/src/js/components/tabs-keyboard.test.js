// ABOUTME: Unit tests for the tabsKeyboard Alpine component
// ABOUTME: Covers arrow-key wrapping, Home/End, disabled tabs and manual vs automatic activation

import { beforeEach, describe, expect, it, vi } from "vitest";

import { tabsKeyboard } from "./tabs-keyboard.js";

function buildTablist({ disabledIndex = -1 } = {}) {
  document.body.innerHTML = `
    <ul role="tablist">
      <li role="presentation"><a role="tab" href="?tab=one" tabindex="0">One</a></li>
      <li role="presentation"><a role="tab" href="?tab=two" tabindex="0">Two</a></li>
      <li role="presentation"><a role="tab" href="?tab=three" tabindex="0">Three</a></li>
    </ul>
  `;
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  if (disabledIndex >= 0) {
    tabs[disabledIndex].setAttribute("aria-disabled", "true");
  }
  tabs.forEach((tab) => {
    tab.click = vi.fn();
  });
  return { tablist: document.querySelector('[role="tablist"]'), tabs };
}

function keyEvent(key, tablist) {
  return { key, currentTarget: tablist, preventDefault: vi.fn() };
}

describe("tabsKeyboard arrow navigation", () => {
  let tablist;
  let tabs;

  beforeEach(() => {
    ({ tablist, tabs } = buildTablist());
  });

  it("moves focus to the next tab on ArrowRight", () => {
    tabs[0].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowRight", tablist));
    expect(document.activeElement).toBe(tabs[1]);
  });

  it("wraps from the last tab to the first on ArrowRight", () => {
    tabs[2].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowRight", tablist));
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("moves focus to the previous tab on ArrowLeft", () => {
    tabs[1].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowLeft", tablist));
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("wraps from the first tab to the last on ArrowLeft", () => {
    tabs[0].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowLeft", tablist));
    expect(document.activeElement).toBe(tabs[2]);
  });

  it("jumps to the first tab on Home", () => {
    tabs[2].focus();
    tabsKeyboard().handleKeydown(keyEvent("Home", tablist));
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("jumps to the last tab on End", () => {
    tabs[0].focus();
    tabsKeyboard().handleKeydown(keyEvent("End", tablist));
    expect(document.activeElement).toBe(tabs[2]);
  });

  it("ignores keys it does not handle", () => {
    tabs[0].focus();
    const event = keyEvent("ArrowDown", tablist);
    tabsKeyboard().handleKeydown(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(tabs[0]);
  });

  it("does nothing when focus is outside the tablist", () => {
    document.body.focus();
    const event = keyEvent("ArrowRight", tablist);
    tabsKeyboard().handleKeydown(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("does not move when Home is pressed on the first tab", () => {
    tabs[0].focus();
    const event = keyEvent("Home", tablist);
    tabsKeyboard().handleKeydown(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});

describe("tabsKeyboard disabled tabs", () => {
  it("skips over a tab marked aria-disabled", () => {
    const { tablist, tabs } = buildTablist({ disabledIndex: 1 });
    tabs[0].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowRight", tablist));
    expect(document.activeElement).toBe(tabs[2]);
  });
});

describe("tabsKeyboard activation modes", () => {
  it("clicks the newly focused tab in automatic mode", () => {
    const { tablist, tabs } = buildTablist();
    tabs[0].focus();
    tabsKeyboard().handleKeydown(keyEvent("ArrowRight", tablist));
    expect(tabs[1].click).toHaveBeenCalledOnce();
  });

  it("only moves focus in manual mode", () => {
    const { tablist, tabs } = buildTablist();
    tabs[0].focus();
    tabsKeyboard({ activation: "manual" }).handleKeydown(
      keyEvent("ArrowRight", tablist),
    );
    expect(document.activeElement).toBe(tabs[1]);
    expect(tabs[1].click).not.toHaveBeenCalled();
  });

  it("treats an unrecognised activation value as automatic", () => {
    const { tablist, tabs } = buildTablist();
    tabs[0].focus();
    tabsKeyboard({ activation: "sideways" }).handleKeydown(
      keyEvent("ArrowRight", tablist),
    );
    expect(tabs[1].click).toHaveBeenCalledOnce();
  });
});
