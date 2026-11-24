# 775 — A pause button for the hero demo

Status: implemented. The home page hero's product demo (see
`docs/agent/775-home-page/plan.md`) starts by itself and loops for as long as
the page is open, beside the page's text. It now has a button that pauses it
where it is and plays it on from there.

## Why

- **WCAG 2.2.2 Pause, Stop, Hide (level A).** Moving content that starts
  automatically, lasts more than five seconds and is shown alongside other
  content needs a way for the visitor to pause, stop or hide it. The demo is
  all three.
- **Hamish asked for it** in his comment on the story (11-17): he does not
  like endlessly looping animations, and asked for a pause button, or for the
  animation to stop after three runs. This change builds the pause button.
  Stopping after three runs is not done: it is not enough for 2.2.2 on its
  own, which asks for a control.

## Where it sits

Under the demo's frame, at its right corner: a 44px round icon button on the
frame's white, with the frame's border and shadow, so it reads as the demo's
control (`.hero-demo__toggle` in `static/backoffice/src/main.css`). It is in
the normal flow under the frame, so it never covers anything the demo points
at, and it works the same at 390px as at 1440px. It is the design system's
icon button (`button(variant="icon")` in `components/button.html`), with
Lucide's pause and play from `components/icons.html`.

It sits outside the frame because the frame is `aria-hidden`: inside it the
button would be hidden from screen readers. In the tab order it comes after
the hero's Create account and Contact us.

## How it behaves

- **A toggle with a constant name.** The button is named "Pause the demo"
  (`aria-label`, translated) and carries `aria-pressed`: `false` while the
  demo plays, `true` while it is paused. The icon follows `aria-pressed` in
  the stylesheet — pause while it plays, play while it is paused — so the
  icon and the state cannot disagree. This is the toggle pattern the
  component accessibility guide asks for: the label does not change,
  `aria-pressed` does. Space and Enter work, as on any `<button>`; the focus
  ring is the browser's own, as on every design-system button.
- **It freezes the demo where it is.** Every wait in the timeline is a wait
  on one pausable clock (`src/js/lib/pausable-clock.js`). Pausing holds the
  clock, so the screen, the text being typed and the cursor stay put, and it
  pauses the animations already running in the frame — a move of the cursor,
  a click, the progress bar, the pies drawing, the fade between loops — with
  `getAnimations({ subtree: true })`. `pause()` alone lands a frame or more
  late, once the compositor catches up, and the cursor would drift a few
  pixels after the press; so the script also sets each animation's current
  time to what it was when the button was pressed, which completes the pause
  at once. Playing releases the clock and plays those animations on, so the
  demo carries on from where it stopped rather than starting again.
- **Off screen is a separate hold.** The demo already paused while the hero
  was off screen. That is now the clock's second reason to hold, beside the
  visitor's. Releasing one leaves the other, so scrolling the hero back into
  view never undoes the visitor's pause, and playing it while it is off
  screen waits until it is back. Off screen it now stops where it is, rather
  than at the end of its loop.
- **Not remembered.** The pause lasts for the page view: reloading the page,
  or coming back later, plays the demo again (or, for a visitor who prefers
  reduced motion, rests it as before). Remembering the choice would mean
  storing it in the browser, and `docs/personal-data.md` lists any use of
  `localStorage`, `sessionStorage` or `document.cookie` under "What would
  change the answer": the site has no cookie banner, so a new store needs a
  decision of its own, and the published cookies page updated, not a commit.
- **Without JavaScript, and under `prefers-reduced-motion`**, the demo already
  rests on its last screen, the dashboard, and nothing moves. There is nothing
  to pause, so the button is rendered `hidden` and only the script unhides
  it, once the demo actually plays. Under reduced motion the script sizes the
  window and stops there, before the button.
- **CSP.** The script stays in the esbuild bundle (`js/hero-demo.js`), loaded
  under the page's nonce. The button is wired with `addEventListener`; there
  is no inline handler.

## The frame is inert

The frame's screens are built from real components, so its buttons — Create
project, Cancel, Run Selection, whichever the screen shows — took focus even
though `aria-hidden` hides them from screen readers. A keyboard user tabbing
to the pause button passed through controls that do nothing and that a
screen reader says are not there. The frame is now `inert` as well as
`aria-hidden`: nothing in it takes focus or a click. The script still drives
it.

## Code

- `templates/public/_hero_demo.html`: the button, after the frame; the frame
  gains `inert`.
- `src/js/init/hero-demo.js`: the player, moved from the entry point so the
  tests can import it; `src/js/hero-demo.js` only calls `initHeroDemos()`.
- `src/js/lib/pausable-clock.js`: `sleep(ms)` counts only the time the clock
  runs; `hold(reason)` and `release(reason)`; `onChange(running)` for the
  animations.
- `templates/backoffice/components/icons.html`: `icon_pause`, `icon_play`
  (Lucide 0.555), listed in the showcase's icons section.

## Tests

- Vitest: `src/js/lib/pausable-clock.test.js` (waits count only running
  time, holds for separate reasons, the stop and start callbacks) and
  `src/js/init/hero-demo.test.js` (the button shown once the demo plays and
  hidden under reduced motion, pausing holds the screen, the typing and the
  cursor, playing goes on with the time that was left, the off-screen hold
  beside the visitor's, running animations paused where they were and played
  on).
- Component (`tests/component/test_home_page.py`): the button's markup —
  named "Pause the demo", not pressed, hidden, inside the demo, outside the
  `aria-hidden` frame, both icons drawn — and the frame carrying
  `aria-hidden` and `inert`. The showcase draws the button once.
- BDD (`features/home-page.feature`): a visitor tabs to the button (focus
  never landing inside the frame), pauses the demo with Space, and it holds
  still for three seconds; Enter plays it and it moves on. Under reduced
  motion there is no button.

## Translations

One new string, "Pause the demo". The Hungarian proposal, flagged fuzzy, is
"Bemutató szüneteltetése": the noun form `translations/styleguide-hu.md`
asks of buttons, which also sits with the home page's informal register,
and "bemutató" as the demo's description already has it.
