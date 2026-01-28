# Sortition Foundation Website Color Palette Analysis

## Current Colors (Your Understanding)
- Orange: #D7764E (Primary)
- Brown: #501D43 (Secondary - headings, logo)
- Brown: #841E40 (Tertiary - backgrounds)
- Light Gray: #F7F7F7 (Background)
- Black: Background alternative
- White: Text on dark backgrounds

## Detailed Color Analysis

### Color Verification & Characteristics

**#D7764E** - Primary Orange
- RGB: rgb(215, 118, 78)
- HSL: hsl(17, 63%, 57%)
- Warm, coral-like orange
- Good contrast on light backgrounds
- Accessible for text at sufficient sizes

**#501D43** - Deep Purple-Brown
- RGB: rgb(80, 29, 67)
- HSL: hsl(315, 47%, 21%)
- Actually more purple than brown (magenta undertones)
- Very dark, good for headings
- Creates strong hierarchy

**#841E40** - Burgundy Red-Brown
- RGB: rgb(132, 30, 64)
- HSL: hsl(340, 63%, 32%)
- Deep burgundy with red undertones
- Medium-dark, suitable for backgrounds
- More saturated than #501D43

**#F7F7F7** - Light Neutral Gray
- RGB: rgb(247, 247, 247)
- HSL: hsl(0, 0%, 97%)
- Near-white, subtle background
- Reduces eye strain vs pure white

## Proposed Design System Tokens

### Primitive Color Tokens
```css
/* Primary Colors */
--color-orange-500: #D7764E;
--color-orange-400: #E18F6F; /* lighter variant */
--color-orange-600: #C66639; /* darker variant */

/* Secondary Colors - Purple-Brown Family */
--color-plum-900: #501D43;
--color-plum-800: #6B2858;
--color-plum-700: #841E40; /* This could be seen as darker shade */

/* Or if treating as separate: */
--color-burgundy-700: #841E40;
--color-burgundy-800: #6B1A35;

/* Neutrals */
--color-gray-50: #F7F7F7;
--color-gray-900: #000000;
--color-white: #FFFFFF;
```

### Semantic Color Tokens
```css
/* Brand Identity */
--color-brand-primary: var(--color-orange-500);
--color-brand-secondary: var(--color-plum-900);
--color-brand-accent: var(--color-burgundy-700);

/* Text */
--color-text-primary: var(--color-plum-900); /* headings */
--color-text-body: var(--color-gray-900); /* or a dark gray */
--color-text-on-dark: var(--color-white);
--color-text-link: var(--color-orange-500);
--color-text-link-hover: var(--color-orange-600);

/* Backgrounds */
--color-bg-primary: var(--color-white);
--color-bg-secondary: var(--color-gray-50);
--color-bg-tertiary: var(--color-burgundy-700);
--color-bg-dark: var(--color-gray-900);
--color-bg-brand: var(--color-plum-900);

/* Interactive Elements */
--color-button-primary-bg: var(--color-orange-500);
--color-button-primary-text: var(--color-white);
--color-button-secondary-bg: var(--color-plum-900);
--color-button-secondary-text: var(--color-white);

/* Borders & Dividers */
--color-border-light: #E0E0E0;
--color-border-medium: #CCCCCC;
--color-divider: var(--color-gray-50);
```

## Color Relationships & Usage Recommendations

### Hierarchy Pattern
1. **Primary (Orange #D7764E)**: Call-to-action buttons, links, key highlights
2. **Secondary (Deep Plum #501D43)**: Headings, logo, navigation
3. **Tertiary (Burgundy #841E40)**: Section backgrounds, secondary elements
4. **Neutral Light (#F7F7F7)**: Page backgrounds, cards
5. **Neutral Dark (Black)**: Alternative sections, footer

### Color Harmony Analysis
The palette creates a warm, authoritative feel:
- Orange provides energy and approachability
- Purple-brown conveys wisdom and depth
- Burgundy adds sophistication
- The colors share warm undertones, creating cohesion

### Accessibility Considerations

**Contrast Ratios (WCAG 2.1)**:
- #D7764E on #FFFFFF: 3.5:1 (AA for large text only)
- #501D43 on #FFFFFF: 12.4:1 (AAA for all text)
- #841E40 on #FFFFFF: 6.8:1 (AA for all text)
- #FFFFFF on #501D43: 12.4:1 (AAA for all text)
- #FFFFFF on #841E40: 6.8:1 (AA for all text)
- #FFFFFF on #000000: 21:1 (AAA for all text)

**Recommendations**:
- Orange (#D7764E) should be used for larger text (18px+ or 14px+ bold) on white
- For smaller body text on white, use #501D43 or black
- All dark colors work well for text on light backgrounds
- White text works excellently on all dark backgrounds

### Extended Palette Suggestions

You might benefit from having intermediate shades:

```css
/* Tints (lighter versions for hovers, disabled states) */
--color-orange-100: #F8E5DC;
--color-orange-200: #F0CBBA;
--color-plum-100: #E8D9E4;
--color-plum-200: #D1B3C9;

/* Shades (darker versions) */
--color-orange-700: #B54F2A;
--color-orange-800: #8F3D20;
--color-plum-950: #3D1632;

/* Functional colors (if needed) */
--color-success: #2D7A4F;
--color-warning: #D7764E; /* could reuse orange */
--color-error: #C1272D;
--color-info: #0077B6;
```

## Implementation Notes

1. **Logo Colors**: The logo likely uses both #D7764E (orange) and #501D43 (deep plum)

2. **Background Alternation**:
   - Primary content: white or #F7F7F7
   - Alternating sections: #841E40 or black
   - Creates rhythm and visual interest

3. **Text on Colored Backgrounds**:
   - On #841E40: Use white text
   - On black: Use white text
   - On #F7F7F7: Use #501D43 or black

4. **Interactive States**:
   - Hover: Darken by 10-15% or use -600 variants
   - Active: Darken by 20% or use -700 variants
   - Disabled: Use 50% opacity or -200 tints
