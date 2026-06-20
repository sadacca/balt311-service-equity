# Navigation Alternatives — design options for the dashboard nav

## Why this exists

The `st.navigation` multipage reorg moved the view list into Streamlit's **sidebar**,
which (a) hid the fact that the Within-Baltimore frame is a six-step *story* beyond the
landing page, and (b) was awkward on mobile. The editorial **masthead** band also took up
roughly half the viewport on every screen.

This document records four navigation patterns that were reviewed, so we can try the
others later without re-deriving them. **All four share:**

- A **single-line header** (slim title + tagline), replacing the tall masthead band.
- The **two frames always visible** — `🏙 Within Baltimore` vs `🌐 Compare cities`.
- The **views within the active frame** surfaced (6 for Within, 3 for Compare).
- `st.navigation(position="hidden")` underneath, so only the active page runs (the
  per-page performance win is preserved) and each view keeps its own URL.

**Implemented:** Option A — the **Story stepper**.

---

## Option A — Compact frame + view bar *(implemented)*

```
Baltimore 311 · Service Equity        Does your block change the wait?
─────────────────────────────────────────────────────────────────────
[ Within Baltimore | Compare cities ]
[ Operations · Services · Areas · Equity · Service Equity · Mix-Adjusted ]
─────────────────────────────────────────────────────────────────────
          (active view renders here)
```

- Two horizontal `st.segmented_control`s — **frame on one line, views on the next** —
  so the nav stays ~two lines (the whole point: the old sidebar/stepper ate a full mobile
  screen because `st.columns` stack full-width on narrow screens; segmented controls
  **wrap** instead, using the width).
- Order is the story order (left→right), so the sequence is implied without numbering.
  Numbers, icons, and Prev/Next were dropped, and the long titles trimmed (`Area Service
  Usage`→`Areas`, `Mix-Adjusted Equity`→`Mix-Adjusted`) with small text, to fit the width.
- Keys are scoped per page (`nav_frame::<url_path>`): each page renders a fresh control
  seeded (`default=`) to the active selection with `required=True`, so there's no stale
  widget state to fight — a plain body-level `st.switch_page` on change is enough.
- **Cross-city nuance:** the view control simply lists the three Compare views (Service
  Delivery · Service Equity · Maturity) — no numbering / sequence metaphor, which only
  fits the six-step Within-Baltimore frame.
- **Pros:** compact, width-efficient, mobile-friendly; both frames always clear. **Cons:**
  the sequence is only implied by order (no explicit step affordance); on a phone the six
  views may wrap to two lines.

  *(An earlier take used a numbered `st.page_link` stepper with Prev/Next in `st.columns`;
  it read well on desktop but the columns stacked into a full-screen vertical list on
  mobile — hence the segmented-control rework.)*

---

## Option B — Original two-row tabs

```
Baltimore 311 · Service Equity                                  Year ▾
─────────────────────────────────────────────────────────────────────
[ 🏙 Within Baltimore | 🌐 Compare cities ]
 Operations  Services  Areas  Equity  Service Equity  Mix-Adjusted
─────────────────────────────────────────────────────────────────────
```

The pre-multipage layout: a frame `segmented_control` above a horizontal view tab-strip
(`st.tabs` or a second `segmented_control` with if/elif gating). Familiar; both frames
clear. **Cons:** the six view tabs wrap awkwardly on mobile, and the linear story is only
*implied* by left-to-right order. (This is what the app used before the multipage reorg —
see commit `e90b962` for the gated-`segmented_control` form.)

---

## Option C — Compact toggle + dropdown (most mobile-first)

```
Baltimore 311 · Service Equity                                  Year ▾
─────────────────────────────────────────────────────────────────────
[ 🏙 Within | 🌐 Compare ]      ◀   ▌ Equity ▾ ▐   ▶     Step 4 of 6
─────────────────────────────────────────────────────────────────────
```

Frame toggle + a single view **dropdown** with Prev/Next story arrows and a "Step 4 of 6"
counter. Very compact and scales to any number of views. **Cons:** the full list of views
isn't visible at a glance (hidden in the dropdown). Good candidate for a responsive
*mobile fallback* of Option A.

---

## Option D — Contents rail (in-page left column)

```
Baltimore 311 · Service Equity                                  Year ▾
──────────────┬──────────────────────────────────────────────────────
🏙 WITHIN     │
  Operations  │
  Services    │        (active view renders here)
  Areas       │
  Equity  ◀   │
  …           │
🌐 COMPARE    │
  Delivery    │
  …           │
```

A slim in-page left column (`st.columns`, **not** Streamlit's sidebar) listing **both**
frames and all their views as a clickable outline — the whole structure is always visible
(best discoverability). **Cons:** eats horizontal width on desktop; needs a dropdown
fallback on mobile; more layout work.

---

## How to switch options later

- The slim header is `.app-header` CSS in `app/components/theme.py` + the
  `st.markdown("<div class='app-header'>…")` block in `app/app.py`. The old tall masthead
  is still available as `theme.masthead(kicker, title, tagline)` if a bolder header is
  wanted again.
- The nav itself is the two-`segmented_control` block after
  `pg = st.navigation(..., position="hidden")` in `app/app.py`. Swapping in Option B/C/D
  means replacing that block; the page definitions, the `within_active = pg in
  within_pages` gate, and `pg.run()` stay the same.
- Nav (compact segmented-control) styling lives under the "Top nav" comment in `theme.py`'s
  `_GLOBAL_CSS`.
