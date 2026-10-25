# Progress

Spec: [specs.md](specs.md). Frontend is built one feature at a time (section 13), on mock data until the API exists.

| # | Feature | Status | Spec |
|---|---|---|---|
| 1 | Vite + React + TS scaffold, repo layout | Done | FE23 |
| 2 | Flat US map, 10 hub nodes, red-to-green by absorbable surplus, quality outlines | Done | FE2, FE4-FE7, FE25 |
| 3 | Globe view + Globe/Flat toggle (choice remembered) | Done | FE2, FE3, FE24, FE26 |
| 4 | Light green land, light blue water | Done | FE28 (tokens) |
| 5a | Left panel dashboard (all 7 sections + footer, quality badges, click a node to set the forecast chart's grid) | Done, mock data | FE9 |
| 5b | Left panel node detail (select a node, Escape to go back) | Next | FE9 |
| 6 | Time scrubber | Todo | FE8 |
| 7 | Chat, job flow, pop-up | Todo | FE10, FE11, FE13-FE22 |
| 8 | Arc animation | Todo | FE12 |
| 9 | Starfield, reduce-motion, colorblind palette, states (loading, stale, API down) | Todo | FE1, FE6, FE30 |

Known gaps: dashboard "same at the scrubbed hour" waits for the scrubber (6); quality outlines (FE7) show on flat only; selection/time not yet shared between views; globe dashed arcs unverified.

Run: `cd frontend && npm install && npm run dev`
