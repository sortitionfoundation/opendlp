// ABOUTME: Entry point registering the Alpine components used on public pages
// ABOUTME: Registration only - the components themselves live under components/

import { registrationMethod } from "./components/registration-method.js";
import { teamSelector } from "./components/team-selector.js";

document.addEventListener("alpine:init", () => {
  Alpine.data("teamSelector", teamSelector);
  Alpine.data("registrationMethod", registrationMethod);
});
