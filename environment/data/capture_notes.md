# Capture conventions

The stable script URLs in this capture are `/assets/shell.js` and `/assets/editor.js`. Query strings and fragments are not part of the service-worker cache key. Rows in `sw_events.csv` are processed by `(ts_ms, seq)` order.

`controller` assigns the named worker to a client. A `cache_put` stores the network revision that was current for that chunk at that event time. `cache_delete` removes that normalized URL from the worker cache. On `script_load`, a controlling worker serves its cached entry when one exists; otherwise the browser receives the network revision current at that time and the controlling worker stores that revision. An uncontrolled client loads from the network and does not populate a worker cache. The revision used by a stack frame is the revision served by the `load_id` named in `frames.csv`.

`deployments.csv` is authoritative for network revision changes. Its timestamps are inclusive.

`asset_offset_bytes` is a zero-based byte offset into the exact UTF-8 asset for the served revision. Source-map generated columns are zero-based UTF-16 code-unit offsets from the start of the generated line; generated lines are zero-based. Original source lines in the requested output are one-based and original source columns are zero-based. For a generated position, use the mapping segment on that line with the greatest generated column not exceeding the position. A line with no such segment is unmapped.

The files under `maps/` are Source Map v3 indexed maps. Section offsets follow the v3 convention: a section's line and column offset apply to the first generated line of that section, and later lines start at column zero. `map_index.csv` lists the candidate bundle maps that survived the release-artifact upload race. `anchors.csv` contains trusted canary locations captured from the same revision and chunk.

A bundle map can resolve to a path under `compiled/`. `module_map_index.csv` gives the Source Map v3 map for that compiler output. Continue mapping that intermediate line/column through the module map; the final location is the first mapped source whose path begins with `src/`.
