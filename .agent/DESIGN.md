---
version: "alpha"
name: "Intelligence Core | Nexora Systems"
description: "Intelligence Core Feature Section is designed for highlighting product capabilities and value points. Key features include reusable structure, responsive behavior, and production-ready presentation. It is suitable for component libraries and responsive product interfaces."
colors:
  primary: "#22D3EE"
  secondary: "#06B6D4"
  tertiary: "#67E8F9"
  neutral: "#000000"
  background: "#22D3EE"
  surface: "#000000"
  text-primary: "#A1A1AA"
  text-secondary: "#22D3EE"
  border: "#22D3EE"
  accent: "#22D3EE"
typography:
  display-lg:
    fontFamily: "Inter"
    fontSize: "72px"
    fontWeight: 600
    lineHeight: "72px"
    letterSpacing: "-0.025em"
  body-md:
    fontFamily: "SFMono-Regular"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "16px"
    letterSpacing: "0.1em"
  label-md:
    fontFamily: "SFMono-Regular"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "16px"
    letterSpacing: "1.2px"
rounded:
  md: "6px"
spacing:
  base: "4px"
  sm: "2px"
  md: "4px"
  lg: "8px"
  xl: "10px"
  gap: "8px"
  card-padding: "13px"
  section-padding: "24px"
components:
  button-primary:
    textColor: "{colors.neutral}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: "14px"
  button-secondary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.tertiary}"
    rounded: "0px"
    padding: "10px"
  button-link:
    textColor: "{colors.text-primary}"
    rounded: "0px"
    padding: "0px"
  card:
    rounded: "0px"
    padding: "20px"
---

## Overview

- **Composition cues:**
  - Layout: Grid
  - Content Width: Full Bleed
  - Framing: Glassy
  - Grid: Strong

## Colors

The color system uses dark mode with #22D3EE as the main accent and #000000 as the neutral foundation.

- **Primary (#22D3EE):** Main accent and emphasis color.
- **Secondary (#06B6D4):** Supporting accent for secondary emphasis.
- **Tertiary (#67E8F9):** Reserved accent for supporting contrast moments.
- **Neutral (#000000):** Neutral foundation for backgrounds, surfaces, and supporting chrome.

- **Usage:** Background: #22D3EE; Surface: #000000; Text Primary: #A1A1AA; Text Secondary: #22D3EE; Border: #22D3EE; Accent: #22D3EE

## Typography

Typography pairs Inter for display hierarchy with SFMono-Regular for supporting content and interface copy.

- **Display (`display-lg`):** Inter, 72px, weight 600, line-height 72px, letter-spacing -0.025em.
- **Body (`body-md`):** SFMono-Regular, 12px, weight 400, line-height 16px, letter-spacing 0.1em.
- **Labels (`label-md`):** SFMono-Regular, 12px, weight 600, line-height 16px, letter-spacing 1.2px.

## Layout

Layout follows a grid composition with reusable spacing tokens. Preserve the grid, full bleed structural frame before changing ornament or component styling. Use 4px as the base rhythm and let larger gaps step up from that cadence instead of introducing unrelated spacing values.

Treat the page as a grid / full bleed composition, and keep that framing stable when adding or remixing sections.

- **Layout type:** Grid
- **Content width:** Full Bleed
- **Base unit:** 4px
- **Scale:** 2px, 4px, 8px, 10px, 14px, 16px, 20px, 24px
- **Section padding:** 24px
- **Card padding:** 13px, 20px
- **Gaps:** 8px, 12px, 16px, 32px

## Elevation & Depth

Depth is communicated through glass, border contrast, and reusable shadow or blur treatments. Keep those recipes consistent across hero panels, cards, and controls so the page reads as one material system.

Surfaces should read as glass first, with borders, shadows, and blur only reinforcing that material choice.

- **Surface style:** Glass
- **Borders:** 0.8px #22D3EE; 0.8px #06B6D4
- **Shadows:** rgb(34, 211, 238) 0px 0px 4px 0px; rgba(34, 211, 238, 0.2) 0px 0px 20px 0px inset, rgba(34, 211, 238, 0.1) 0px 0px 30px 0px; rgba(34, 211, 238, 0.4) 0px 0px 40px 0px inset, rgba(34, 211, 238, 0.3) 0px 0px 30px 0px
- **Blur:** 4px, 8px

### Techniques
- **Gradient border shell:** Use a thin gradient border shell around the main card. Wrap the surface in an outer shell with 0px padding and a 0px radius. Drive the shell with linear-gradient(rgba(34, 211, 238, 0.06) 1px, rgba(0, 0, 0, 0) 1px), linear-gradient(90deg, rgba(34, 211, 238, 0.06) 1px, rgba(0, 0, 0, 0) 1px) so the edge reads like premium depth instead of a flat stroke. Keep the actual stroke understated so the gradient shell remains the hero edge treatment. Inset the real content surface inside the wrapper with a slightly smaller radius so the gradient only appears as a hairline frame.

## Shapes

Shapes rely on a tight radius system anchored by 4px and scaled across cards, buttons, and supporting surfaces. Icon geometry should stay compatible with that soft-to-controlled silhouette.

Use the radius family intentionally: larger surfaces can open up, but controls and badges should stay within the same rounded DNA instead of inventing sharper or pill-only exceptions.

- **Corner radii:** 4px, 6px

## Components

Anchor interactions to the detected button styles. Reuse the existing card surface recipe for content blocks.

### Buttons
- **Primary:** text #000000, radius 6px, padding 14px, border 0px solid rgb(229, 231, 235).
- **Secondary:** background #22D3EE, text #67E8F9, radius 0px, padding 10px, border 0.8px solid rgba(34, 211, 238, 0.4).
- **Links:** text #A1A1AA, radius 0px, padding 0px, border 0px solid rgb(229, 231, 235).

### Cards and Surfaces
- **Card surface:** radius 0px, padding 20px, shadow none.

## Do's and Don'ts

Use these constraints to keep future generations aligned with the current system instead of drifting into adjacent styles.

### Do
- Do use the primary palette as the main accent for emphasis and action states.
- Do keep spacing aligned to the detected 4px rhythm.
- Do reuse the Glass surface treatment consistently across cards and controls.
- Do keep corner radii within the detected 4px, 6px family.

### Don't
- Don't introduce extra accent colors outside the core palette roles unless the page needs a new semantic state.
- Don't mix unrelated shadow or blur recipes that break the current depth system.
- Don't exceed the detected expressive motion intensity without a deliberate reason.

## Motion

Motion feels expressive but remains focused on interface, text, and layout transitions. Timing clusters around 300ms and 4000ms. Easing favors ease and linear. Hover behavior focuses on text changes. Scroll choreography uses Parallax for section reveals and pacing.

**Motion Level:** expressive

**Durations:** 300ms, 4000ms, 150ms, 2000ms, 18405ms, 12369ms

**Easings:** ease, linear, cubic-bezier(0.4, 0, 1), ease-in-out

**Hover Patterns:** text

**Scroll Patterns:** parallax
