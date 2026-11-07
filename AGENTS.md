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

## Shared Footer

The footer must be consistent across Home, About, Services, Contact, and utility pages.

- Keep the footer markup in `lib/footer.html` and include it exactly once in every root HTML page with `<!-- include:site-footer -->`. Do not copy footer markup into individual pages.
- `lib/site.py` expands the footer for both the build and preview server, alongside the shared header.
- Use three desktop columns for company information, navigation, and Vancouver/international positioning with contact details. Stack the sections on mobile.
- Include the company description, Vancouver-based international positioning, email, phone, and LinkedIn on every page.
- Keep the Vancouver skyline graphic from `images/vancouver-sketch.svg` in a separate area above the legal row, without covering text.
- Keep the company/legal row at the bottom, including Vancouver, BC, Canada and BC Incorporation No. BC1535270. Use a subtle divider, smaller muted text, and graceful mobile wrapping.
- Keep the email link as `mailto:sales@nxflo.com` and the phone link as `tel:+16042609218`, displaying `+1 (604) 260-9218`.
- Define footer styles in `styles.css`. Do not add page-specific footer, logo, color, or spacing overrides.
- Preserve semantic footer/navigation/address elements, visible keyboard focus, and readable text. Keep footer links compact on desktop, with touch targets of at least 44px on mobile and touch devices.
- Verify identical footer content and layout at the same desktop and mobile widths, with no horizontal overflow down to 320px.

## VM Deployment Requirement

This repository runs on a VM. The user reviews changes at `https://www.nxflo.com/` and cannot access a localhost-only preview.

- After adding or updating a website feature, fix, content, or visual design, always build and deploy the changes before reporting the task complete.
- Deployment is authorized as part of these website changes; do not ask for separate deployment confirmation unless the user explicitly requests otherwise.
- Complete the relevant tests and desktop/mobile verification first, then run `bash 1_build_docker.sh` followed by `bash 2_deploy_docker.sh`. Deploy only after the build succeeds.
- Verify the deployed site at `https://www.nxflo.com/`, including the changed pages and assets. Use `PYTHONPATH=. python3 tests/check_deployment.py --url https://www.nxflo.com/` to check that the live pages match the current source.
- Include the live URL and deployment verification result in the completion message.
- If deployment fails or is blocked, report that clearly; do not describe the changes as live or leave the user with only a localhost preview.

## Before Finishing
For every UI change:
1. Check desktop layout.
2. Check mobile layout.
3. Check for horizontal overflow.
4. Check that navigation and interactive elements still work.
5. If the header or navigation changed, compare every page at the same desktop and mobile widths, check all menu links, and confirm the correct active-page indicator.
6. Do not consider the task complete until both layouts are usable.
7. When changing the shared footer, compare it across every page and verify the email, phone, navigation, and Vancouver artwork.

## Existing Site
Preserve the existing Nexusflow visual identity unless specifically asked to redesign it.
Do not unnecessarily rewrite unrelated HTML, CSS, or JavaScript.
