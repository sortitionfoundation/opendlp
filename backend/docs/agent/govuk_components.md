# GOV.UK Component Usage

## Common Layout Structure

```html
<div class="govuk-width-container">
  <div class="govuk-grid-row">
    <div class="govuk-grid-column-full">
      <!-- Content -->
    </div>
  </div>
</div>
```

## Grid System

- `govuk-grid-column-full` - Full width
- `govuk-grid-column-two-thirds` - 2/3 width
- `govuk-grid-column-one-third` - 1/3 width
- `govuk-grid-column-one-half` - 1/2 width

## Typography

- `govuk-heading-xl` - Extra large heading
- `govuk-heading-l` - Large heading
- `govuk-heading-m` - Medium heading
- `govuk-heading-s` - Small heading
- `govuk-body` - Body text
- `govuk-body-l` - Large body text
- `govuk-body-s` - Small body text

## Buttons

- `govuk-button` - Primary button
- `govuk-button--secondary` - Secondary button
- `govuk-button--start` - Start button with arrow icon
- `govuk-button--white` - Custom white button (Sortition styling)

## Navigation

- Mobile-responsive navigation handled by GOV.UK Frontend JavaScript
- Custom styling for Sortition Foundation branding in `application.scss`
- Mobile menu button becomes visible on screens < 48.0625em
- Cross-browser compatibility (Chrome/Firefox differences handled)

## Tags and Status

```html
<strong class="govuk-tag govuk-tag--green">Status</strong>
<strong class="govuk-tag govuk-tag--blue">Role</strong>
<strong class="govuk-tag govuk-tag--red">Alert</strong>
```

## Summary Lists (for key-value data)

```html
<dl class="govuk-summary-list">
  <div class="govuk-summary-list__row">
    <dt class="govuk-summary-list__key">Label</dt>
    <dd class="govuk-summary-list__value">Value</dd>
  </div>
</dl>
```

## Custom Components

### Assembly Cards

```html
<div class="assembly-card">
  <h3 class="govuk-heading-m">Title</h3>
  <p class="govuk-body-s">Description</p>
  <dl class="govuk-summary-list">
    <!-- Summary list content -->
  </dl>
</div>
```

### Feature Cards (front page)

```html
<div class="feature-card">
  <h3 class="govuk-heading-m">Feature Title</h3>
  <p class="govuk-body">Feature description</p>
</div>
```

### Key Details Bars (dashboard)

```html
<div class="dwp-key-details-bar">
  <div class="dwp-key-details-bar__key-details">
    <dt class="govuk-heading-s">Label</dt>
    <dd class="dwp-key-details-bar__primary">Value</dd>
  </div>
</div>
```

### Hero Section

```html
<div class="hero-section govuk-!-padding-top-6 govuk-!-padding-bottom-6">
  <!-- Hero content with burnt-orange background -->
</div>
```
