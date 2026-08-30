---
name: Maritime Soft
colors:
  surface: '#fdfae4'
  surface-dim: '#dedbc6'
  surface-bright: '#fdfae4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f7f4df'
  surface-container: '#f2efd9'
  surface-container-high: '#ece9d3'
  surface-container-highest: '#e6e3ce'
  on-surface: '#1c1c0f'
  on-surface-variant: '#484831'
  inverse-surface: '#323123'
  inverse-on-surface: '#f5f1dc'
  outline: '#79785f'
  outline-variant: '#cac8aa'
  surface-tint: '#626200'
  primary: '#626200'
  on-primary: '#ffffff'
  primary-container: '#ffff00'
  on-primary-container: '#757500'
  inverse-primary: '#cdcd00'
  secondary: '#5f5e5f'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfe0'
  on-secondary-container: '#636263'
  tertiary: '#5d5e66'
  on-tertiary: '#ffffff'
  tertiary-container: '#f8f6ff'
  on-tertiary-container: '#707079'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#eaea00'
  primary-fixed-dim: '#cdcd00'
  on-primary-fixed: '#1d1d00'
  on-primary-fixed-variant: '#494900'
  secondary-fixed: '#e5e2e3'
  secondary-fixed-dim: '#c8c6c7'
  on-secondary-fixed: '#1b1b1c'
  on-secondary-fixed-variant: '#474647'
  tertiary-fixed: '#e3e1ec'
  tertiary-fixed-dim: '#c6c5cf'
  on-tertiary-fixed: '#1a1b22'
  on-tertiary-fixed-variant: '#46464e'
  background: '#fdfae4'
  on-background: '#1c1c0f'
  surface-variant: '#e6e3ce'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  title-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '500'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: 0.02em
  label-xs:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: '1'
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  base: 8px
  container-padding: 24px
  gutter: 16px
  section-gap: 32px
  card-inner-padding: 24px
---

## Brand & Style

This design system is defined by a "tender" approach to enterprise UI, blending high-fidelity professionalism with an airy, approachable softness. It targets high-end SaaS and fintech platforms where clarity and trust are paramount.

The aesthetic direction is **Modern Corporate with a Soft Focus**. It leverages massive corner radii and generous whitespace to reduce cognitive load and visual tension. By combining a neutral, light-gray foundation with high-impact "Vibrant Yellow" accents, the system feels both technically precise and energetic. The overall mood is sophisticated, calm, and premium.

## Colors

The palette is anchored by a sophisticated grayscale hierarchy, punctuated by a singular, high-vibrancy accent.

- **Primary (Vibrant Yellow):** Used exclusively for high-priority CTAs, progress indicators, and critical status highlights. It should be paired with black text for maximum legibility.
- **Surface & Background:** The main canvas uses a cool light gray (`#F4F4F5`) to provide contrast for the "Pure White" card containers. This distinction creates a clear sense of depth without relying on heavy shadows.
- **Grayscale:** We use a range of grays for secondary actions and borders. Borders should never exceed `1px` and should maintain a low opacity (10-15%) to keep the interface feeling "light."
- **Feedback:** Use standard semantic colors (Green for success, Red for error) but apply them in a desaturated, professional tone to avoid clashing with the primary yellow.

## Typography

This design system utilizes **Inter** for all roles to maintain a systematic, utilitarian, and clean appearance. 

The typographic hierarchy is built on extreme contrast between large, bold display text and smaller, high-legibility functional labels. Tighten letter spacing on larger headlines to create a "compact" feel. For body text, ensure a generous line height (1.5x - 1.6x) to contribute to the "airy" layout philosophy. Use font-weight shifts rather than color shifts to denote importance where possible.

## Layout & Spacing

The layout philosophy follows a **Fluid Grid** model with a "tender" approach to density. We prioritize whitespace to allow components to breathe.

- **Grid:** Use a 12-column grid for desktop with 24px margins. Elements should span columns to create structured but flexible dashboard layouts.
- **Safe Zones:** Cards and containers must maintain a minimum internal padding of 24px (`card-inner-padding`) to reinforce the premium feel.
- **Responsiveness:** On mobile, collapse grids to a single column and reduce section gaps to 24px. Ensure that touch targets maintain a minimum of 44px height regardless of the visual "softness."

## Elevation & Depth

Depth is conveyed through **Tonal Layers** and **Ambient Shadows** rather than physical skeuomorphism or hard lines.

1.  **Level 0 (Base):** Light gray background surface.
2.  **Level 1 (Cards):** Pure white surfaces with a subtle, 1px border (`rgba(0,0,0,0.05)`) and a very soft, diffused shadow: `0px 4px 20px rgba(0, 0, 0, 0.03)`.
3.  **Level 2 (Active/Overlays):** For modals or active dropdowns, increase the shadow spread and blur to create a "lifted" effect: `0px 12px 40px rgba(0, 0, 0, 0.08)`.

Avoid using any black shadows. All shadows should be tinted slightly toward the neutral-gray secondary color to maintain a natural look.

## Shapes

The defining characteristic of this design system is its **Hyper-Roundedness**. All primary containers (cards, main buttons, inputs) use a base radius of `24px` or `rounded-xl` (`3rem` for specific larger sections). 

Small components like checkboxes or tags should use a proportionally high radius to maintain visual consistency—always lean toward "pill-shaped" rather than "rounded-square." This softness eliminates visual "sharpness" and contributes to the user's perception of ease-of-use.

## Components

- **Buttons:** 
    - *Primary:* Vibrant Yellow background, black text, 24px+ radius. No border.
    - *Secondary:* White background, 1px light gray border, black text.
- **Input Fields:** Pure white background, 24px radius, 1px border. On focus, the border transitions to a soft gray—do not use the primary yellow for focus rings unless the input is invalid.
- **Cards:** The workhorse of the design system. Pure white, 24px radius, subtle ambient shadow. Use for grouping all major data visualizations and lists.
- **Chips & Tags:** Use a fully pill-shaped design. For "Status" tags, use light tints of the semantic color (e.g., light green background with dark green text).
- **Data Visualization:** Lines and bars should have rounded caps. Use the Vibrant Yellow as the "Highlight" or "Current" data point to draw immediate focus.
- **Navigation:** Vertical or horizontal sidebars should use a clean, icon-heavy approach with generous vertical spacing between items.