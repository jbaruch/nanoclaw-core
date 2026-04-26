---
alwaysApply: true
---

# No Lazy Verification

If a tool exists that can verify an external claim, you MUST use it before reporting "can't verify" or punting on the check.

## Banned excuses

Do not surface any of these to the user as a reason you stopped:

- "Site is JS-rendered"
- "Page is thin / almost empty"
- "Can't access this"
- "I can't read this site"
- "Couldn't load the page"

Each of these collapses the moment you launch a real browser, hit a domain API, or run code. Stopping at the excuse ships wrong answers as if they were considered.

## Try in priority order

The exact tool names depend on the context — check `/capabilities` for what's actually available. The priority order is what matters:

1. **A real browser tool that runs JS** (e.g. Cloudflare Browser Rendering, Playwright, Puppeteer). Handles SPAs, dynamic content, vendor portals with client-side routing. Use this whenever `WebFetch` returns empty, sparse, or skeletal HTML.
2. **A domain-specific API** (Composio integrations, MCP tools, vendor SDKs). Structured data beats scraping every time.
3. **`WebFetch`** for static HTML where JS rendering isn't needed.
4. **Code execution** (Bash, Python) — if the answer is computable from inputs already in hand, compute it instead of asking.

## Reporting a genuine failure

If the tools were tried and actually failed, say exactly what was tried and how each one failed — do not collapse it to "I can't verify".

Acceptable shape: *"Tried the JS browser tool on `/cfp` — page rendered but had no deadline text anywhere. Tried the Sessionize API — 404 (event isn't on Sessionize). Falling back to: please confirm manually."*

## Why this rule exists

dev2next CFP verification, 2026-04-22 — agent dismissed a live-browser option with "сайт почти пустой, JS-рендер" when a JS-capable browser tool was available and would have returned the deadline in one call. Treat the priority order above as non-negotiable.
