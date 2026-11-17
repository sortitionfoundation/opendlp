# 775 — Home page content and the lottery animation

Status: implemented. The public home page (`templates/public/home.html`) gets
the content team's second text pass and a hero that shows OpenDLP is a live web
tool, not a command line: an animated drawing of a democratic lottery.

Design references: the OpenDLP - UI Figma file, home page node `6524-18922`,
for the sections below the hero; the content doc's "Mock Up Text" tab for every
string; and infogram.com/features/interactive-content for the hero's shape,
text and calls to action on the left, the moving picture on the right, stacked
on a phone.

## The story

Hamish's redesigned page has been on main since 11-12. The marketing review of
it asked for three things: proof on the first screen that the software exists
and works, a section naming the problems practitioners face before the
"how it works" section, and that section retitled so problem and solution
match. The team agreed not to show real screens of the product, which are too
dense for a first look, and to show the essence instead: the lottery.

## The hero

- **Two columns from `lg`** (`grid-cols-[5fr_6fr]`): the heading, the new
  paragraph, the buttons and the two proof lines on the left, left-aligned; the
  animation on the right. Below `lg` they stack, text first. The header already
  carries the logo, so the hero no longer repeats the full logo above the
  heading.
- **Heading** "Bringing Simplicity to Sortition", capitalised as the content doc
  has it, with "Simplicity" highlighted as before. The msgid keeps its
  `%(highlight)s` placeholder and the template still splits the translation at
  it, so a translation can put the word anywhere in the sentence; the heading
  is now one line of text around one `<span>` rather than three spans, and the
  component test's `slogan_parts` helper reads it that way.
- **Buttons**: Create account first and primary, Contact us second and
  secondary, so the eye lands on the one the page is for.
- **Proof lines**: "300+ democratic lotteries delivered by Sortition Foundation
  and Sortition Europe" and "30+ lotteries already run in OpenDLP" (the doc says
  "already ran"; the grammar is fixed here and flagged to the author). The
  figures sit outside the translated strings.

## The animation

`templates/public/_hero_animation.html`, an inline SVG; its motion is the
`.hero-draw` rules in `static/backoffice/src/main.css`. No image file, no
JavaScript, no library.

- **Why SVG and CSS, not a gif**: crisp at any size and pixel density, a few
  kilobytes instead of megabytes, colours from the design tokens, the captions
  translatable through the catalogue like any other string, a seamless loop, and
  an honest `prefers-reduced-motion` fallback. A gif can do none of those; a
  Lottie file would need a design tool to author and a runtime to play.
- **What it shows**, in an abstract browser window, one loop of 17 seconds:
  everyone invited appears as 64 dots in three groups (plum, red, orange: half,
  a third, a fifth of the people); a Targets card slides in and its three bars
  fill; a cursor moves to Select and clicks it; the chosen dots are picked out
  and fly to their seats in an assembly semicircle, the arch of the OpenDLP
  logo; a green tick appears by each target bar, the panel matches the
  targets. The panel keeps the population's proportions (10 / 6 / 4), which is
  the point of the drawing. A caption under the drawing names each beat.
- **How it is built**: every element's keyframes are expressed as percentages of
  the same 17 s clock, so nothing drifts. Each dot carries its own appearance
  delay (`--d`); a chosen dot also carries the offset to its seat (`--dx`,
  `--dy`), used by one shared `transform: translate(var(--dx), var(--dy))`
  keyframe. The seat outlines are drawn before the dots so the dots cover them.
  The geometry came from a one-off script; the file is plain markup and is
  edited by hand from here.
- **Accessibility**: the SVG has `role="img"` with a title and a description
  that tell the story in words. Under `prefers-reduced-motion: reduce` every
  animation is off and the drawing shows its result: the panel seated, the
  targets met, the last caption.
- **Colours**: the dots use `--color-brand-500` and `--color-brand-300`, plus
  the logo orange `#FB5732`, which has no token (see the note at the top of
  `home.html`). Text and the button use the neutral, brand and success tokens.

## "Sortition is complicated"

A new section between the hero and "how it works", on the page background with
its three cards on `--color-neutral-100`: the intro sentence pair, "But doing
it well is hard." as a line of its own, three cards (Stitched together by hand,
Easy to get wrong, Few places to learn), and "We are changing that with
OpenDLP." to close. The four sentences that were the hero's intro now live
here, two of them joined in the third card as the doc has them.

## "OpenDLP makes it simple"

The "how it works" section keeps everything but its title, which was "How does
OpenDLP work?". The footer's "How it works" link still points at
`#how-it-works`.

## Translations

`just translate-regen` picked up the new strings; the Hungarian catalogue has a
proposal for each new or changed home page string, flagged fuzzy for the team's
translator, following `translations/styleguide-hu.md` (target → célszám,
assembly → közösségi gyűlés, buttons in the noun form). `just translate-check`
passes.

## Tests

- Component (`tests/component/test_home_page.py`): the new titles, the problem
  section, Create account before Contact us with the two button variants, the
  proof lines, the animation's presence, and the slogan split with the new
  heading shape. The hero logo assertion now checks the full logo is gone and
  the footer's compact logo stays.
- BDD (`features/home-page.feature`): the two "centred under the logo"
  scenarios are replaced by two layout scenarios, the animation to the right of
  the heading at 1440 and below it at 375, plus the existing phone-width and
  sign-in scenarios.
- Two older component tests, the footer and header help links, fail on this
  worktree before and after this change: the local `.env` sets a different
  help-site address. They are not touched.

## Not in this change

The teaser on sortitionfoundation.org, the redirect from
sortitionfoundation.org/opendlp, the sign-up page's final wording and the beta
notice (sc-1305) are the story's other items and stay open. "In Europe" versus
"in the EU" in Keeps your data secure is an open comment on the content doc.
