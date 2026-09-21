# DESIGN.md — AI Knowledge Assistant

## 1. Visual Theme & Atmosphere

Build a dark-first AI productivity interface for document question answering. The product should feel precise, calm, technical, and trustworthy rather than flashy.

Design inspiration:
- 60% Linear: dense, precise, product-focused, dark surfaces, restrained accent color
- 25% Claude: comfortable long-form reading, warm and clear answer presentation
- 15% Vercel: simple developer-tool structure and minimal chrome

Core principles:
- Let the document workflow and generated answer be the visual focus.
- Use one primary chromatic accent only.
- Prefer hierarchy through spacing, surfaces, borders, and typography instead of gradients or heavy shadows.
- Retrieval metadata should feel technical but readable.
- Citation/source information must be visually prominent and easy to inspect.

## 2. Color Palette & Roles

```yaml
colors:
  canvas: "#0b0b0d"
  surface-1: "#111216"
  surface-2: "#17181d"
  surface-3: "#1d1f25"
  border: "#292b33"
  border-strong: "#383b46"

  text-primary: "#f5f5f7"
  text-secondary: "#c7c9d1"
  text-muted: "#8d919c"

  primary: "#7c83ff"
  primary-hover: "#9298ff"
  primary-soft: "#20223a"

  success: "#46b86b"
  warning: "#d6a84b"
  danger: "#e06464"
```

Rules:
- `primary` is reserved for primary actions, focus states, selected items, and important links.
- Do not introduce additional decorative accent colors.
- Use semantic colors only for real semantic states such as indexing success, warning, and errors.

## 3. Typography Rules

Use a clean modern sans-serif stack:

```css
font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

Use monospace for retrieval metadata, scores, IDs, filenames when appropriate:

```css
font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
```

Type scale:

| Token | Size | Weight | Use |
|---|---:|---:|---|
| Display | 36px | 600 | Empty-state / welcome heading |
| H1 | 28px | 600 | Page title |
| H2 | 20px | 600 | Section heading |
| H3 | 16px | 600 | Card title |
| Body | 15px | 400 | Default text |
| Body Small | 13px | 400 | Secondary text |
| Caption | 12px | 400 | Metadata |
| Mono | 12px | 400 | Retrieval metadata |

Use slightly tighter letter spacing for large headings. Long generated answers should prioritize comfortable line height (1.6–1.7).

## 4. Spacing & Shape Tokens

```yaml
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 48px

radius:
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  pill: 9999px
```

Rules:
- Default component radius: 8–12px.
- Avoid oversized 20–30px rounded cards.
- Use 1px borders for separation before using shadows.
- Keep layout compact enough for a developer productivity tool.

## 5. Layout Principles

Desktop application layout:

```text
┌────────────────────────────────────────────────────────────┐
│ Top Bar                                                    │
├────────────────┬───────────────────────────────────────────┤
│ Document       │ Main Workspace                            │
│ Sidebar        │                                           │
│                │ Question / Answer                         │
│ Upload         │                                           │
│ Documents      │ Sources                                   │
│                │                                           │
│                │ Retrieval Inspector                       │
└────────────────┴───────────────────────────────────────────┘
```

Recommended dimensions:
- Sidebar: 260–300px desktop
- Main content max width for reading: 900–1000px
- Top bar: 52–60px
- Answer text line length: approximately 70–85 characters

Responsive behavior:
- Under tablet width, collapse the document sidebar into a drawer.
- Stack source and retrieval cards vertically.
- Keep primary question input accessible without horizontal scrolling.
- Minimum interactive target: 40px.

## 6. Component Styling

### Top Navigation
- Dark canvas background.
- Thin bottom border.
- Product name left.
- Status / settings controls right.
- Avoid oversized marketing-style navigation.

### Document Sidebar
- Surface-1 background.
- Document rows should include filename and indexing state.
- Selected document uses `primary-soft` background and primary-colored indicator.
- Delete action should remain visually secondary until hover.

### Upload Dropzone
- Dashed or subtle solid border.
- Clear drag-and-drop affordance.
- Primary accent only when dragging or focused.
- Show supported type: PDF.

### Question Composer
- Large single input / textarea with subtle border.
- Send button uses primary accent.
- Focus ring uses primary color.
- Composer should feel similar to an AI assistant input, not a generic form.

### Answer Panel
- Do not place the entire answer inside an overly decorative card.
- Favor a readable document-like surface with generous vertical spacing.
- Render Markdown cleanly.
- Keep generated answer visually dominant.

### Citation Cards
Each citation should show:
- filename
- page number
- optional chunk index
- optional relevance score

Use compact surface-2 cards with 1px borders. Citation cards should be interactive when possible.

### Retrieval Inspector
Each retrieved chunk should display:
- rank (`#1`, `#2`, ...)
- source filename
- page number
- similarity or distance score when available
- text preview

Use monospace for score / metadata and normal body typography for content.

### Status Badges
Examples:
- Indexed
- Processing
- Error

Use compact pill badges only for status, never for normal buttons or cards.

## 7. Depth & Elevation

Prefer surface hierarchy:

```text
canvas → surface-1 → surface-2 → surface-3
```

Use shadows sparingly. Most cards should rely on subtle borders and contrast between surfaces.

Recommended shadow only for floating menus or dialogs:

```css
box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
```

## 8. Interaction & Motion

- Hover transitions: 120–180ms.
- Avoid large animated gradients or decorative motion.
- Loading states should communicate retrieval / generation progress clearly.
- Use skeletons or subtle progress indicators for document indexing.
- Retrieval results may expand/collapse with restrained animation.

## 9. Do's and Don'ts

### Do
- Keep the UI technical, calm, and focused.
- Make citations easy to inspect.
- Surface retrieval behavior instead of hiding it completely.
- Preserve whitespace around generated answers.
- Use consistent spacing and design tokens.
- Prioritize accessibility and contrast.

### Don't
- Do not use multiple accent colors.
- Do not use glassmorphism as the primary visual language.
- Do not use large decorative gradients.
- Do not make every element a rounded card.
- Do not hide filenames, page numbers, or retrieval metadata.
- Do not turn the application into a marketing landing page.
- Do not sacrifice readability for visual effects.

## 10. Product-Specific Screens

### Empty State
Show:
- short product explanation
- upload call-to-action
- 2–3 example questions

### Active QA State
Show:
- document context
- question composer
- generated answer
- source citations
- retrieval inspector

### Document Management State
Show:
- filename
- indexing state
- chunk count when available
- delete / re-index controls

## 11. Agent Implementation Guide

When generating or modifying frontend code:

1. Follow this file before inventing new visual rules.
2. Reuse tokens instead of hard-coding one-off spacing, colors, or radii.
3. Preserve existing RAG functionality.
4. Treat citations and retrieval metadata as first-class product features.
5. Prefer reusable components such as:
   - `DocumentSidebar`
   - `UploadDropzone`
   - `QuestionComposer`
   - `AnswerView`
   - `CitationCard`
   - `RetrievalInspector`
   - `StatusBadge`
6. If using Tailwind, map these tokens into CSS variables / Tailwind theme values.
7. If using shadcn/ui, restyle components to match this design rather than keeping default styling.

## 12. Reference Prompt

Use this prompt when asking a coding agent to build or redesign the frontend:

> Read `DESIGN.md` first and follow it strictly. Build a dark-first AI document knowledge assistant. Preserve the existing RAG workflow. The interface should include document upload and management, a question composer, readable generated answers, citation cards, and a retrieval inspector. Use the design tokens and guardrails in `DESIGN.md`; do not introduce additional visual styles without justification.
