# Nexusflow Website Development Requirements

# Critical UI Requirement

Every website change MUST support both desktop and mobile browsers.

Before completing any UI task:
- verify desktop layout at 1440px
- verify mobile layout at 375px
- verify there is no horizontal overflow
- ensure navigation remains usable
- ensure text, cards, images, and buttons resize or stack correctly

A change is not complete if it only works on desktop.

## Responsive Design
All changes must work correctly on both desktop and mobile browsers.

Requirements:
- Design desktop-first, but always verify responsive behaviour.
- Support common mobile widths down to 320px.
- Avoid horizontal scrolling.
- Navigation must remain usable on small screens.
- Cards, columns, and grids must stack or resize appropriately.
- Text must remain readable without zooming.
- Buttons and links must remain easy to tap.
- Images must scale within their containers.
- Do not use fixed widths that break mobile layouts.
- Prefer responsive CSS using:
  - flexbox
  - CSS grid
  - `max-width`
  - relative units
  - media queries where necessary

## Desktop Layout
- Target desktop widths around 1280–1920px.
- Important pages should fit naturally within the viewport where practical.
- Avoid excessively wide text lines.
- Preserve clear spacing and alignment.

## Mobile Layout
- Test approximately:
  - 320px
  - 375px
  - 430px
- Convert multi-column sections to a single column where appropriate.
- Reduce large headings and spacing proportionally.
- Ensure footer and navigation do not overflow.

## Shared Header and Top Navigation
The site header and top menu must be consistent across every page, including Home, About, Services, Contact, and any utility pages.

Requirements:
- Use the approved contact-page header layout as the visual reference when aligning the site headers.
- Use the same logo asset, displayed size, home link, header height, container width, spacing, fonts, colors, and alignment at each responsive breakpoint.
- Keep the same navigation labels, order, and destinations on every page:
  - Home: `index.html` (`data-nav="home"`)
  - About: `about.html` (`data-nav="about"`)
  - Services: `services.html` (`data-nav="services"`)
  - Contact: `contact.html` (`data-nav="contact"`)
- Only the current-page indicator may differ. Use a consistent active style and `aria-current="page"`; utility pages must not incorrectly highlight Home.
- Keep any header call to action consistent across all pages. Do not add, remove, or rename it on just one page, or duplicate the Contact menu link unnecessarily.
- Define shared header styles in `styles.css` and shared navigation behaviour in `script.js`. Avoid page-specific header overrides that cause visual differences.
- Keep the header markup in `lib/header.html` and include it in each root HTML page with `<!-- include:site-header -->`. Never add a separate header copy to a page.
- `lib/site.py` renders the shared header for both `build.py` and `dev_server.py`. Use `python3 build.py` to generate `dist/`; Docker builds run this automatically. Do not edit generated files or introduce a framework solely for navigation consistency.
- Use `3_preview.sh` for source previews, or serve the built `dist/` directory. Source HTML includes are expanded by the build or preview server.
- Preserve semantic `<header>` and `<nav aria-label="Primary">` elements, descriptive logo alternative text, visible keyboard focus, and accessible link touch targets.
- Use the same responsive menu behaviour on every page, with no horizontal overflow down to 320px.
- When changing the header, logo sizing, navigation, or shared header styles, inspect all pages and verify desktop and mobile consistency before finishing.
- Verify menu alignment with native desktop scrollbars visible, including taller windows where Contact fits but other pages scroll. Preserve the shared stable scrollbar gutter; hidden scrollbars can mask navigation shifts. `tests/check_navigation.py` checks this regression.

## Before Finishing
For every UI change:
1. Check desktop layout.
2. Check mobile layout.
3. Check for horizontal overflow.
4. Check that navigation and interactive elements still work.
5. If the header or navigation changed, compare every page at the same desktop and mobile widths, check all menu links, and confirm the correct active-page indicator.
6. Do not consider the task complete until both layouts are usable.

## Existing Site
Preserve the existing Nexusflow visual identity unless specifically asked to redesign it.
Do not unnecessarily rewrite unrelated HTML, CSS, or JavaScript.
