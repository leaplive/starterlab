---
name: talk
type: experiment
display_name: "LEAP2 Lightning Talk"
description: "Lightning talk slides — SIGCSE TS 2026"
authors: "Sampad Mohanty"
organizations: "University of Southern California"
tags: [talk, slides, demo]
entry_point: slides.html
require_registration: false
pages:
  - {name: "Interact", file: "interact.html"}
  - {name: "Live", file: "live.html"}
---

# LEAP2 Lightning Talk

Slides for the 19th CCSC Southwestern conference lightning talk at UC Riverside (March 28, 2026).

## Features

### Live Audience Poll

The talk itself is a LEAP experiment. During the presentation:

1. **QR slide** — audience scans to open `interact.html` on their phones
2. **Interact page** — audience answers quick poll questions about LEAP
3. **Live dashboard** — presenter shows `live.html` with bar charts updating in real-time

### Slide Sync

The presenter (admin) controls audience slides. Non-admin viewers who open `slides.html` automatically follow along:

- **Admin**: every slide change pushes the current slide number to the server
- **Audience**: polls every 2.5 seconds and navigates to the presenter's slide
- A QR code on the title slide lets the audience scan and follow along

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `f` | Toggle fullscreen (remark built-in) |
| `t` | Toggle light/dark theme |
| `l` | Login as admin (or logout if already logged in) |

All shortcuts are suppressed while the login modal is open.

When logged in as admin, the title slide hints update to show "admin · syncing slides" with a logout shortcut.

### Theme Toggle

Press `t` during the presentation to switch between dark and light themes. The theme choice persists in `localStorage` and syncs into embedded iframes (e.g. `live.html`).

### KaTeX Math Rendering

Slides support inline (`$...$`) and display (`$$...$$`) math via KaTeX, rendered automatically on each slide transition.

## Pages

| Page | Description |
|------|-------------|
| `slides.html` | Remark-based slide deck (entry point) |
| `longertalk.html` | Extended version of the slides (full-length backup) |
| `interact.html` | Audience poll page (mobile-friendly) |
| `live.html` | Real-time bar charts of poll responses |

## Functions

| Function | Decorators | Description |
|----------|------------|-------------|
| `get_questions()` | `@nolog @noregcheck` | Get the list of poll questions |
| `submit_answer(question_id, answer)` | `@withctx @noregcheck` | Submit an answer to a poll question |
| `get_results()` | `@ratelimit(False) @nolog @noregcheck` | Get current poll results |
| `set_slide(n)` | `@adminonly @nolog @noregcheck` | Set the current slide number (presenter only) |
| `get_slide()` | `@ratelimit(False) @nolog @noregcheck` | Get the current slide number |

## Setup (day-of)

1. Both QR codes (title slide for follow-along, demo slide for interaction) are generated on the fly from `window.location.origin` — no configuration needed
2. Press `l` on the title slide to log in as admin and activate slide sync
3. Audience scans the title slide QR to follow along, or the demo slide QR to interact
