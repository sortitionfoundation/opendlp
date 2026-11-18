# 775 — Home page content and the hero picture

Status: implemented. The public home page (`templates/public/home.html`) gets
the content team's second text pass and a hero that shows OpenDLP is a live web
tool, not a command line: a picture of the product. The hero has had three
pictures; the home page shows the last, and the design-system showcase keeps all
three in a Public pages tab.

Design references: the OpenDLP - UI Figma file, home page node `6524-18922`,
for the sections below the hero; the content doc's "Mock Up Text" tab for every
string; and infogram.com/features/interactive-content for the hero's shape,
text and calls to action on the left, the picture on the right, stacked
on a phone.

## The story

Hamish's redesigned page has been on main since 11-12. The marketing review of
it asked for three things: proof on the first screen that the software exists
and works, a section naming the problems practitioners face before the
"how it works" section, and that section retitled so problem and solution
match. The team first agreed not to show real screens of the product, which are
too dense for a first look, and to show the essence instead: the lottery. The
stakeholders found that drawing too abstract; a demo built from the product's
screens followed it, and the final choice is a static picture of the projects
screen.

## The hero

- **One macro**: `templates/public/_hero.html`'s `home_hero()` draws the hero
  with whatever its caller puts in the picture slot (`data-hero-visual`), so the
  home page and the showcase draw the same hero. `heading_tag` lets the
  showcase pass `h3` under its own `h1`.
- **Two columns from `lg`** (`grid-cols-[5fr_6fr]`): the heading, the new
  paragraph, the buttons and the two proof lines on the left, left-aligned; the
  picture on the right. Below `lg` they stack, text first. The header already
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

## The picture (in production)

- `templates/public/_hero_image.html` shows `static/img/home-hero.png`
  (2880×1720, from the design): the Your projects screen on a monitor, with a
  callout pointing at Create project, "Start creating your first assembly
  project". The image carries its width and height, so the page does not jump
  while it loads, and a translated alt text.
- The callout is part of the image, so it reads in English in every language.
- The picture has its own light pink background (#FAF3F5) on the hero's grey
  (neutral-100); its corners are rounded so the edge reads as a card.

## The earlier versions, in the showcase

The showcase (`/backoffice/showcase?tab=public`, staging and dev only) has a
Public pages tab with one section, Home Page Hero, that draws the hero three
times through `home_hero()`: with the picture, the demo and the drawing. The
demo's script is loaded there; a `ResizeObserver` sizes it when its tab opens,
since a hidden tab has no width.

### Version 1: the abstract drawing

`templates/public/_hero_animation.html`, restored from history with its
`.hero-draw` rules in `main.css`: an inline SVG animated in CSS, one 17 s loop.
Everyone invited appears as dots, targets fill, one click runs the lottery and
the chosen dots take their seats; ticks by the targets show the panel matches
them. Under reduced motion it shows the result at rest.

### Version 2: the product demo

A short demo built from the backoffice's own components, simplified.

- **Where**: `templates/public/_hero_demo.html` holds five screens; the
  `.hero-demo` rules in `main.css` style the frame; `src/js/hero-demo.js`
  (bundled to `static/js/hero-demo.js`, loaded under the page's CSP nonce)
  plays them.
- **What it shows**, one cursor, about thirty seconds a loop: *Your projects*
  with two project cards, the cursor clicks Create project; *Create project*,
  the title "Citizens' Assembly on Climate" and the panel size 30 typed in;
  *Targets*, the Gender card alone, Min and Max typed into each row, no tabs,
  no Edit or Save; *Select and replace*, Run Selection, the Task progress
  dialog with its bar and the success alert, then the green panel and a
  Completed row in Selection history; the *Dashboard*, Gender's Target,
  Respondents and Selected pie cards, the Selected pie the same shape as the
  Target one.
- **Real components**: button, card, input, page header, tag, the dialog's
  backdrop, positioner and header, alert, status badge and progress bar come
  from the design-system macros, so the demo is the app's markup and styles.
  The pie cards use the dashboard card's box with the pie drawn as a CSS
  conic gradient, so the home page does not load Chart.js.
- **How it plays**: the app layer is laid out at 800px and scaled to the
  column, so it reads as a desktop window at any width. The script finds each
  target by its `data-demo` name and reads what to type from `data-type`, so
  it carries no words and works in every language. A click is a small dip of
  the cursor and the target pressed. The loop pauses while the hero is off
  screen.
- **Fallbacks and accessibility**: the frame is `aria-hidden`; an `sr-only`
  paragraph tells the story. Under `prefers-reduced-motion`, or without
  JavaScript, the last screen shows at rest.

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
  proof lines, the picture in the hero with no demo or drawing on the page,
  and the slogan split with the new heading shape. The hero logo assertion now checks the full logo is gone and
  the footer's compact logo stays.
- Component (`tests/component/test_backoffice_general.py`): the showcase's
  Public pages tab draws the hero three times, with the picture, the drawing and
  the demo, the demo's five screens, its script, and every `data-demo` target as
  a real attribute.
- BDD (`features/home-page.feature`): the two "centred under the logo"
  scenarios are replaced by two layout scenarios, the picture to the right of
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
