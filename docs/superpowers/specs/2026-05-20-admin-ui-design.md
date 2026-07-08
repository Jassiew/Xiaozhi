# Admin UI Redesign Spec

**Date:** 2026-05-20
**Status:** approved

## Goals

Rebuild all 3 frontend pages with custom CSS (removing Pico CSS) to achieve a professional admin panel look:
- Dark sidebar + dark top bar + light content area (gray-blue palette)
- Filter bar on dashboard by device, status, and metric thresholds
- Multi-device overview with expandable detail view
- Redesigned session detail page with visual timeline
- Polished login page

## Layout Architecture

```
┌──────────────────────────────────────────────┐
│  Top Bar: system name + user info    #1e293b │
├────────┬─────────────────────────────────────┤
│ Sidebar│  Content Area              #f8fafc  │
│#0f172a │  ┌─ Filter Bar ──────────────────┐  │
│        │  │ device | status | threshold    │  │
│  nav   │  └───────────────────────────────┘  │
│  items │  ┌─ Stats Row (4 cards) ─────────┐  │
│        │  └───────────────────────────────┘  │
│ device │  ┌─ Device Cards Grid ───────────┐  │
│  list  │  │ card | card | card             │  │
│        │  └───────────────────────────────┘  │
│        │  ┌─ Detail Panel (expandable) ────┐  │
│        │  │ trend chart + session link     │  │
│        │  └───────────────────────────────┘  │
└────────┴─────────────────────────────────────┘
```

## Color System

| Role | Color | Usage |
|------|-------|-------|
| Sidebar bg | `#0f172a` | Navigation background |
| Top bar bg | `#1e293b` | Header background |
| Content bg | `#f8fafc` | Main area background |
| Card bg | `#ffffff` | Cards, panels |
| Card border | `#e2e8f0` | Subtle borders |
| Primary | `#3b82f6` | Buttons, links, active nav |
| Danger | `#dc2626` | Alert values (>0.5 threshold) |
| Warning | `#d97706` | Warning values |
| Success | `#10b981` | Online indicator |
| Muted | `#94a3b8` / `#64748b` | Offline, secondary text |

Design principle: numbers stay neutral (dark) unless they cross a threshold. Color = alert, not decoration.

## Pages

### 1. Login (`login.html`)
- Centered card, 400px max-width, shadow
- Blue logo mark at top
- Two input fields, full-width submit button
- Bottom version text

### 2. Dashboard (`dashboard.html`)
- **Stats row**: online count, active alerts count, today sessions, total frames — 4 small cards
- **Filter bar**: inline selects for device (all/list), status (all/online/offline), fatigue threshold (all/>0.5/>0.7), distraction threshold (all/>0.5/>0.7). Query button + reset link.
- **Device cards grid**: 3-column auto-fill. Each card has colored left border (green=online, gray=offline), device name + dot, 3 metrics, action/gaze status line. Cards with alert-level values get colored numbers.
- **Detail panel**: expands below cards when a device is clicked. Shows a mini trend sparkline and "view full session" link.
- **Polling**: background 5s polling of all devices via `/api/realtime/{id}`. Updates dots, cards, and expanded detail.
- **Devices without data**: survive gracefully (no 404/error state).

### 3. Session Detail (`session.html`)
- Back link + title with device/date/status metadata
- 5 summary cards: frame count, avg fatigue, avg distraction, max difficulty, alert event count
- Trend chart (Chart.js): 3-line chart (fatigue/distraction/difficulty)
- Event timeline: vertical timeline with colored dots and event tags. Red=fatigue alert, orange=distraction alert, blue=difficulty spike, gray=action change. Load more button at bottom.

## Filter Behavior

- Filters are client-side URL params passed to existing `/api/realtime/{id}` calls
- Device filter: limits which cards are shown in overview
- Status filter: online = has active session, offline = no active session
- Threshold filters: highlight/filter cards where the metric exceeds the chosen value
- Reset clears all filters

## Implementation Notes

- Remove Pico CSS CDN link from all 3 HTML files
- Remove all Pico CSS class usage
- All CSS inlined in `<style>` tags (no build step)
- Chart.js CDN retained for trend charts
- Token auth flow unchanged (localStorage + Authorization header)
- No new API endpoints needed — existing endpoints sufficient
