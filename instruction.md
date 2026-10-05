During the service-worker rollout investigation, the source locations turned out to be only half of the problem. The same capture also contains renderer and worker traces from the failures, and those traces disagree about time because several processes restarted while the collector was running. Some MessagePort records are missing as well. The crash copy also includes the application scheduler ring and promise-continuation heap, which are the only surviving record of several unmarked continuation tasks between those trace events. I need one reconciled artifact that ties the mapped stack locations back to the user interactions that actually initiated the failing async work and preserves the runtime task ancestry that led there.

The browser/build evidence is under `/app/data`. The timestamp, cache-key, source-map, line/column, and mapping conventions in `/app/data/capture_notes.md` remain authoritative for the original stack frames. `/app/data/trace_notes.md` describes the clock samples, asynchronous event records, FIFO message semantics, and causal rules for the second part of the capture. `/app/data/scheduler_notes.md` documents the raw scheduler and promise snapshots taken at the same crash point. Treat all three notes as part of the incident record. The existing `/app/reconcile.py` is still only a placeholder; repair it or replace it as needed.

Write `/app/result.json` as a JSON object with exactly these eight top-level arrays: `map_choices`, `frames`, `incidents`, `async_frames`, `message_pairs`, `causal_roots`, `task_bindings`, and `task_paths`.

Each `map_choices` row must contain exactly `revision`, `chunk`, and `candidate`. Emit one row for every revision/chunk pair present in `map_index.csv`, using the candidate that is consistent with the trusted canary evidence.

Each `frames` row must contain exactly:

- `frame_id`: the id from `frames.csv`;
- `revision`: the revision of the asset bytes actually used by that frame's `load_id`;
- `source`: the final original source path after following the supplied mapping chain until the path begins with `src/`;
- `line`: one-based original source line;
- `column`: zero-based original source column;
- `name`: the final mapped symbol name, or an empty string only when the final mapping has no name.

Emit one row for every row in `frames.csv`.

For every row in `incidents.csv`, emit one `incidents` row containing exactly `incident_id`, `root_frame_id`, and `signature`. The actionable stack root is the lowest `stack_order` frame in that incident whose resolved source begins with `src/` but not `src/telemetry/`. `signature` is `<source>:<name>` from that resolved frame.

Each row in `async_frames` must contain exactly `frame_id`, `event_id`, `revision`, `source`, `line`, `column`, and `name`. Emit one row for every row in `async_frames.csv`, using the same asset-revision and source-map conventions as the ordinary stack frames.

`message_pairs` is the reconciled cross-process message ledger. Emit one row for every selected send/receive pair under the rules in `trace_notes.md`, and no row for an unmatched log record. Each row contains exactly:

- `channel`;
- `direction`;
- `send_event_id`;
- `recv_event_id`;
- `transit_ms`: calibrated receive time minus calibrated send time, in milliseconds, rounded to three decimal places.

For each `error` event in `async_events.csv` carrying an `incident_id`, emit one `causal_roots` row with exactly:

- `incident_id`;
- `trigger_event_id`: the unique upstream `interaction` after the asynchronous message history is reconciled;
- `trigger_frame_id`: the async frame attached to that interaction;
- `signature`: `<source>:<name>` from the resolved trigger frame;
- `latency_ms`: calibrated error time minus calibrated trigger time, in milliseconds, rounded to three decimal places.

The scheduler snapshot is a separate view of the same execution. Every row in `async_events.csv` has one committed scheduler marker after the ring, promise heap, and marker correspondence are reconciled. Emit one `task_bindings` row for every event, with exactly:

- `event_id`;
- `task_uid`: the runtime task uid defined in `scheduler_notes.md`;
- `queue`: the queue name represented by that task's allocation record;
- `marker_error_ms`: scheduler MARK collector time minus the event's calibrated capture time, in milliseconds, rounded to three decimal places. This value is signed.

For each incident error, also emit one `task_paths` row containing exactly `incident_id`, `trigger_event_id`, `handoff_count`, and `tasks`. `tasks` is the complete scheduler task ancestry from the triggering interaction task through the error task, in that order. Include unmarked intermediate tasks. `handoff_count` is the number of cross-process MessagePort jumps used while following that ancestry. The `trigger_event_id` must be the interaction reached by that task path.

Array order is not significant. Do not add summary fields, alternate matches, diagnostics, or rows for unmatched message logs. Any frame that cannot be reconciled through the supplied evidence is an error rather than a reason to omit it.

You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
