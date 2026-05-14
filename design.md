# Design: IBM Carbon Enterprise UI

## Purpose

This document defines the default visual direction for future Codex CLI design work in this workspace. Use it when the task involves static HTML, dashboards, admin consoles, infographics, data-heavy layouts, or design-system flavored UI work and the user does not name another style.

## Core Direction

- Follow IBM Carbon's enterprise bias: structured, dense, legible, and operational.
- Make alignment, grouping, and state clarity more important than visual decoration.
- Prefer interfaces that look production-oriented rather than marketing-oriented.
- If a choice is ambiguous, choose the stricter, squarer, more systematic option.

## Official Reference Intent

The target feel should stay aligned with these Carbon ideas:

- 2x Grid rhythm and disciplined spacing
- IBM Plex typography
- token-based layers, borders, text, and support colors
- square or near-square surfaces
- data-first layout patterns
- explicit AI labeling instead of magical or ornamental AI treatment

## Layout System

- Build primary layouts on 8px increments.
- Treat 16px as the default inner padding unit.
- Use 24px or 32px section gaps for major blocks.
- Prefer 16-column thinking on wide screens, even when the final CSS uses flexible tracks.
- Keep headers, side navigation, content regions, tables, and utility panels clearly separated.
- On desktop, favor multi-panel layouts such as:
  - header + side nav + main content
  - main table + detail panel
  - metrics row + table + log or properties panel
- On smaller screens, collapse side nav, stack panels vertically, and keep tables inside horizontal overflow containers.

## Visual Language

- Use flat layers and border-driven separation instead of deep shadows.
- Keep radius at 0px to 2px by default.
- Use keylines, layer contrast, and spacing to create hierarchy.
- Avoid soft glassmorphism, floating cards, pastel fog, and hero-page theatrics.
- Use restrained accent color. Blue should carry primary action, links, focus, and selected state.

## Typography

- Primary font stack: `IBM Plex Sans`, `Noto Sans KR`, `Helvetica Neue`, `Arial`, `sans-serif`
- Monospace stack: `IBM Plex Mono`, `Menlo`, `DejaVu Sans Mono`, `monospace`
- Use a compact scale:
  - page title: 28-32px
  - section title: 20-24px
  - card or panel title: 16-18px
  - body: 14px with generous line-height
  - meta label: 12px
- Keep labels terse and systematic.
- Render metrics, identifiers, timestamps, logs, and code in mono or tabular numerals where useful.

## Color And Surfaces

- Separate color roles clearly:
  - app background
  - layer or tile background
  - field background
  - border
  - primary text
  - secondary text
  - support colors for error, warning, success, and info
  - focus
- Prefer neutral grays for most of the canvas.
- Use accent colors sparingly and with semantic meaning.
- Support both bright and dark Carbon-like themes when reasonable, but do not add a theme switch unless the task calls for it.
- AI-related output must be labeled with text or tags, not only by glow or illustration.

## Component Guidance

### Shell

- Use a distinct top bar and, when appropriate, a side navigation rail or panel.
- Shell regions should feel architectural and consistent across the page.

### Tiles And Panels

- Panels should be rectangular, tightly aligned, and content-first.
- Each panel should have a clear title and a single dominant purpose.
- Do not mix multiple unrelated visual metaphors inside one panel.

### Tables

- Prefer dense tables for comparison-heavy or operational content.
- Use sortable headers, compact rows, zebra or hover states only when they improve scanning.
- Support pagination, filters, or batch actions when the scenario implies real usage.
- Keep numeric columns right-aligned when it improves comparison.

### Tags And Status

- Use tags for status, category, environment, risk, or AI markers.
- Keep tag shapes compact and systematic.
- Status meaning should also be obvious from nearby text, not color alone.

### Notifications

- Use inline notifications for important system feedback.
- Keep banners and alerts rectangular and concise.
- Distinguish warning, error, success, and informational states clearly.

### Logs, Code, And Diagnostics

- Present logs in mono text blocks with fixed-height containers.
- Use subtle borders and internal padding.
- Preserve column alignment and timestamp readability.

## Interaction

- Motion should be restrained and purposeful.
- Use 120ms to 180ms transitions for panel reveal, expand-collapse, toast entry, and selection feedback.
- Avoid decorative parallax, elastic hover movement, and ambient looping animation.
- Focus indicators must be obvious and high contrast.

## Accessibility

- Preserve strong contrast between text and background.
- Ensure keyboard focus is visible on all interactive controls.
- Avoid using color alone to encode state.
- Keep hit targets practical on touch layouts, even in dense views.
- When tables compress on mobile, switch to stacked cards or scoped horizontal scrolling instead of unreadably tiny text.

## Implementation Guidance For HTML/CSS

- Define CSS variables for spacing, layer colors, borders, text colors, support colors, and focus color before styling components.
- Keep component classes explicit and operational: `shell`, `side-nav`, `data-table`, `panel`, `status-tag`, `inline-notice`, `log-panel`.
- Favor CSS grid for page structure and flex only for local alignment tasks.
- Use borders and background layers before introducing box-shadow.
- Keep visual decisions deterministic across pages so multiple generated screens feel like one product family.

## Preferred Content Shapes

- KPI strip with concise labels and sober emphasis
- operational summary tiles
- data table with row actions
- detail side panel
- properties or metadata list
- activity log or audit trail
- status banner or inline notice
- AI result panel with explicit label and rationale area

## Do Not Do

- Rounded SaaS cards with heavy blur or large drop shadows
- gradient hero backgrounds
- oversized empty whitespace that lowers information density
- playful illustration-first composition
- floating glass panels
- neon AI effects or mystical AI framing
- inconsistent spacing that breaks the grid
- mixing multiple unrelated design systems in one page

## Fallback Rule

If a task provides limited visual direction, generate the page as if it were an internal enterprise tool built with Carbon principles: rigorous grid, compact typography, rectangular panels, explicit states, and data-first composition.
