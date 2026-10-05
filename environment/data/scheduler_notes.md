# Scheduler ring snapshot

The crash collector also copied the in-page async scheduler ring used by this application build. The copy is not a logical export: `/app/data/scheduler_ring.bin` is a bag of fixed-size 1024-byte pages from several process/segment rings. The bag includes stale pages from older ring generations and a few torn pages. File order has no meaning.

`scheduler_manifest.csv` records the committed tail for each `(process, segment)`: `page_count` is the number of committed pages retained in that ring at the crash and `tail_page_hash` is the 8-byte hash of the last committed page, written as lowercase hex. A committed ring starts with an all-zero `prev_page_hash`; following page hashes from that start to the manifest tail yields exactly `page_count` pages. A page that merely has a larger generation or a valid checksum is not necessarily committed.

Every page is little-endian and exactly 1024 bytes. Its 48-byte header is:

| offset | size | field |
| --- | ---: | --- |
| 0 | 4 | ASCII magic `SRG3` |
| 4 | 1 | format version, `3` |
| 5 | 1 | process code: 0 rendererA, 1 rendererB, 2 workerA, 3 workerB |
| 6 | 1 | segment code: 0 s0, 1 s1 |
| 7 | 1 | ring slot |
| 8 | 4 | page sequence |
| 12 | 4 | ring generation |
| 16 | 2 | record count |
| 18 | 2 | body length |
| 20 | 8 | previous committed page hash |
| 28 | 8 | this page hash |
| 36 | 4 | CRC32 of the body |
| 40 | 8 | reserved, zero in committed pages |

The page hash is the first 8 bytes of BLAKE2s (digest size 8) over the header with bytes 28-35 zeroed, followed by the `body length` bytes of body. Ignore pages whose magic/version, body length, body CRC, or page hash is invalid.

The body is a sequence of records. Each record begins with a little-endian uint16 byte count for the remainder of that record; the next byte is the record type. The payloads are:

- `1 ALLOC`: uint8 task token, uint8 queue code.
- `2 LINK`: uint8 child token, uint8 parent token, uint8 `parent_back`.
- `3 MARK`: uint8 task token, uint16 event tag, int64 collector timestamp in microseconds.
- `4 FINISH`: uint8 task token.
- `5 CANCEL`: uint8 task token.
- `6 YIELD`: uint8 task token.
- `7 RESUME`: uint8 task token.
- `8 CHECK`: uint32 allocation count, uint32 mark count. These are diagnostics only.
- `9 AWAIT`: uint8 child token, uint16 promise id. The current child task inherits its scheduler parent through the promise heap described below.

Queue codes are 0 user, 1 message, 2 microtask, 3 timer, 4 render, 5 worker, 6 continuation, and 7 background.

Task tokens are deliberately reused. Within a recovered committed stream, the first `ALLOC` of a token is occurrence 1, the next is occurrence 2, and so on. A task uid is written as `<process>/<segment>/t<token>.<occurrence>`. `FINISH` and `CANCEL` close the current occurrence; `YIELD` and `RESUME` do not create a new one. A `LINK` always names the current occurrence of its child token. For the parent token, `parent_back=0` means its most recently allocated occurrence at that point in the stream, `1` means the preceding occurrence, and so on. The parent may already have finished. A LINK contributes a scheduler-parent edge from child task to parent task.

## Promise continuation heap

The same crash copy contains `/app/data/promise_heap.bin`, a shuffled collection of 40-byte promise-continuation records. Invalid records and older versions are still present. `promise_manifest.csv` gives the uint16 snapshot serial for each process/segment. Each valid record uses this little-endian layout:

| offset | size | field |
| --- | ---: | --- |
| 0 | 4 | ASCII magic `PRH2` |
| 4 | 1 | version `2` |
| 5 | 1 | process code, same table as the ring |
| 6 | 1 | segment code, same table as the ring |
| 7 | 1 | kind: `1` direct creator, `2` forwarding record |
| 8 | 2 | promise id |
| 10 | 2 | forwarding target promise id, zero for a direct record |
| 12 | 1 | creator task token for a direct record |
| 13 | 1 | reserved |
| 14 | 2 | creator task occurrence for a direct record |
| 16 | 2 | born serial |
| 18 | 2 | dead serial; `65535` means still live |
| 20 | 2 | entry sequence, used only to identify duplicate physical rows |
| 22 | 4 | CRC32 of the complete 40-byte record with these four CRC bytes zeroed |
| 26 | 14 | reserved |

Serials use normal uint16 wraparound ordering: `a` precedes `b` when `0 < ((b-a) & 65535) < 32768`. All version lifetimes in this capture are shorter than half the serial space. A record is visible at the stream snapshot when its born serial is equal to or precedes the snapshot and its dead serial is `65535` or the snapshot strictly precedes the dead serial. Exactly one valid version of a referenced promise id is visible. Kind `2` records forward to another promise id and may chain; resolve forwarding until a visible kind `1` record names the creator task.

For `AWAIT`, the creator task recovered from the visible promise record is the scheduler parent of the current child task. A promise creator may already have finished by the time the continuation runs.

MARK records intentionally do not contain event ids. `scheduler_events.csv` gives the privacy tag carried by each row in `async_events.csv`. For a MARK and async event to correspond, their process, segment, and tag must agree, and the absolute difference between the MARK's collector timestamp and the event's calibrated capture timestamp must be at most 1.200 ms. Within each process/segment, MARK-to-event correspondence preserves order. The retained capture is defined so the intended correspondence maximizes the number of matched rows and, among those correspondences, minimizes the total absolute timestamp residual. Extra MARK records are collector noise and remain unmatched.

The scheduler ancestry and MessagePort ledger describe different edges of the same execution. When tracing a task backward, follow a scheduler-parent edge when one exists, whether it came from LINK or AWAIT. If a task has no scheduler parent and its matched event is a `message_recv`, continue at the task matched to that receive's selected `message_send` from the reconciled message ledger. Every incident error reaches exactly one `interaction` task under those rules. Unmarked intermediate scheduler tasks are part of the path and must not be skipped.
