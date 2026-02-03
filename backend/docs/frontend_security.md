# Frontend Security and CSP Guidelines

## Overview

OpenDLP enforces a strict Content Security Policy (CSP) to protect against XSS attacks.
This guide explains how to write frontend code that complies with our security headers.

## Content Security Policy

Our CSP uses `'strict-dynamic'` which provides strong XSS protection:

**How it works:**
- All `<script>` tags in HTML **must** have a `nonce="{{ csp_nonce }}"` attribute
- Scripts loaded by trusted scripts (e.g., dynamically via `createElement`) are automatically trusted
- Allowlists like `https://cdn.jsdelivr.net` are **ignored** (for backwards compatibility only)

**Blocked:**
- ❌ Any `<script>` tag without a valid nonce
- ❌ eval() and Function() constructors (prevents code injection)
- ❌ Inline event handlers (onclick, onsubmit, etc.)

**Allowed:**
- ✅ `<script nonce="{{ csp_nonce }}">` inline scripts
- ✅ `<script nonce="{{ csp_nonce }}" src="...">` external scripts
- ✅ Scripts dynamically loaded by already-trusted scripts

## Adding JavaScript

### External JavaScript Files (Preferred)

**Always prefer external files over inline scripts.**

1. Create file in `static/js/`
2. Add to `base.html` with **nonce and cache busting**:
   ```html
   <script nonce="{{ csp_nonce }}"
           src="{{ url_for('static', filename='js/utilities.js', v=util_js_hash) }}"></script>
   ```

**Important:** With `'strict-dynamic'` CSP, ALL `<script>` tags (even external ones) need the `nonce` attribute.

### Inline Scripts (Minimal Use)

Only for critical functionality that must run before external scripts load.

**Requirements:**

- Must include `nonce="{{ csp_nonce }}"` attribute
- Keep minimal - externalize if possible

```html
<script nonce="{{ csp_nonce }}">
  // Critical initialization code only
  document.body.className += " js-enabled";
</script>
```

### Event Handlers

**Don't use inline event handlers.** Use data attributes and event delegation:

```html
<!-- ❌ WRONG - violates CSP -->
<form onsubmit="return confirm('Are you sure?')">
  <!-- ✅ CORRECT - use data attributes -->
  <form data-confirm="Are you sure?"></form>
</form>
```

Implement handler in external JS:

```javascript
document.addEventListener("submit", function (e) {
  const msg = e.target.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});
```

## Alpine.js Usage

**Use the CSP-compatible build:** `@alpinejs/csp`

```html
<script
  defer
  src="https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.x.x/dist/cdn.min.js"
></script>
```

### Supported Alpine.js Features

✅ Simple expressions:

- Object literals: `x-data="{ open: false }"`
- Property access: `x-show="open"`
- Comparisons: `x-show="count > 5"`
- Method calls: `@click="toggle()"`

❌ Not supported (requires regular Alpine.js with unsafe-eval):

- Arrow functions: `() => {}`
- Template literals: `` `Hello ${name}` ``
- Destructuring: `{ foo, bar } = obj`
- Global objects: `console.log()`, `Math.random()`

### Best Practice

For complex logic, use `Alpine.data()` components in external JS:

```javascript
// static/js/alpine-components.js
document.addEventListener("alpine:init", () => {
  Alpine.data("teamSelector", (initial) => ({
    selectedTeam: initial || "other",
    isOther() {
      return this.selectedTeam === "other";
    },
  }));
});
```

```html
<div x-data="teamSelector('{{ form.team.data }}')">
  <select x-model="selectedTeam">
    ...
  </select>
  <div x-show="isOther()">...</div>
</div>
```

## Styling

### CSS/SCSS (Preferred)

**Always use SCSS classes instead of inline styles.**

1. Add utility classes to `src/scss/_utilities.scss`:

   ```scss
   .my-utility {
     display: inline;
     padding: 10px;
   }
   ```

2. Build CSS:
   ```bash
   npm run build:sass
   ```

### Inline Styles (Minimal Use)

Inline styles are allowed (unsafe-inline in style-src) but discouraged.

**Only use for:**

- Dynamic runtime values: `style="background-color: {{ site_banner_colour }}"`
- Email templates (email clients require inline styles)

**Don't use for:**

- Static styling (use SCSS classes)
- Repeated patterns (create utility classes)

## Cache Busting

Static assets use query parameter versioning:

```html
<!-- CSS (automatic via base.html) -->
<link
  rel="stylesheet"
  href="{{ url_for('static', filename='css/application.css', v=css_hash) }}"
/>

<!-- JavaScript -->
<script src="{{ url_for('static', filename='js/utilities.js', v=util_js_hash) }}"></script>
```

When files change, hashes change → new URL → cache bypass. Note a new JS file needs a new hash in the context processor.

**Don't manually version files** - the hash system handles it.

## Security Checklist

Before adding frontend code, verify:

- [ ] No inline event handlers (onclick, onsubmit, etc.)
- [ ] Inline scripts have `nonce="{{ csp_nonce }}"` attribute
- [ ] Alpine.js uses CSP-compatible features only
- [ ] Styling uses SCSS classes (not inline styles)
- [ ] External JS/CSS referenced with cache busting (`v=util_js_hash` / `v=css_hash`)
- [ ] No use of eval(), Function(), or similar
- [ ] All scripts from trusted CDNs only

## Testing CSP Compliance

1. Load page in browser with DevTools open
2. Check Console for CSP violation errors
3. Check Network tab → Headers → Content-Security-Policy header
4. Verify nonce values match between header and script tags

## Further Reading

- [MDN: Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [Alpine.js CSP Build](https://alpinejs.dev/advanced/csp)
- [OWASP: Cross Site Scripting Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
