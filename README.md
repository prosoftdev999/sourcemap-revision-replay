# Source Map Revision Replay

A frontend production-debugging and source-map reconstruction challenge focused on recovering the correct historical JavaScript revision behind runtime observations and translating generated code locations back to their original source.

Modern frontend deployments frequently contain many related artifacts:

- application source
- transpiled JavaScript
- bundled chunks
- minified output
- source maps
- hot-reload revisions
- deployment manifests
- runtime stack traces
- historical build metadata

A generated line and column are only meaningful when interpreted against the correct bundle revision and corresponding source map.

Source Map Revision Replay reconstructs that historical relationship.

## Overview

A production error may report a location such as:

```text
app.8f31c2.js:1:18472
```

That coordinate alone does not identify the original application code.

The correct answer can depend on:

```text
runtime event
      ↓
active deployment revision
      ↓
generated bundle
      ↓
matching source map
      ↓
mapping segment
      ↓
original source
      ↓
original line / column
```

Using a source map from the wrong revision can produce a perfectly valid but completely incorrect source location.

## Repository Structure

```text
sourcemap-revision-replay/
├── environment/
├── solution/
├── tests/
├── instruction.md
└── task.toml
```

### `instruction.md`

Defines the reconstruction problem, input evidence, source-map conventions, and required output.

### `environment/`

Contains the reproducible runtime and solver-visible deployment/debugging evidence.

### `solution/`

Contains the reference reconstruction implementation.

### `tests/`

Contains the independent verifier.

### `task.toml`

Defines task metadata and execution configuration.

## The Revision Problem

Production systems often retain evidence from several application revisions.

For example:

```text
revision r17
    └── app.js
        └── app.js.map

revision r18
    └── app.js
        └── app.js.map

revision r19
    └── app.js
        └── app.js.map
```

A runtime observation captured while `r18` was active must not be decoded using the map from `r17` or `r19`.

The first challenge is therefore historical revision recovery.

## Historical Deployment State

The active revision can change over time through mechanisms such as:

- deployments
- chunk replacement
- hot updates
- rollback
- cache refresh
- worker updates
- page navigation
- long-lived sessions

A later manifest does not necessarily describe the code that executed for an earlier runtime event.

The project therefore treats revision identity as historical state.

## Generated vs Original Source

Bundlers and compilers transform application code.

A source file may pass through several stages:

```text
TypeScript / JSX
       ↓
transpilation
       ↓
module transformation
       ↓
bundling
       ↓
minification
       ↓
generated JavaScript
```

Production telemetry typically reports the generated position.

Source maps provide the relationship back toward the authored code.

## Source-Map Mapping

A source map associates generated positions with original locations.

Conceptually:

```text
generated line / column
          ↓
mapping lookup
          ↓
source file
original line
original column
optional symbol name
```

The mapping is not generally a simple arithmetic offset.

Mappings are encoded as ordered segments, and generated columns need to be interpreted according to source-map semantics.

## VLQ Encodings

Standard JavaScript source maps commonly encode mappings using Base64 VLQ.

Those mappings represent deltas between successive values rather than storing every coordinate directly.

A decoder conceptually reconstructs fields such as:

```text
generated column
source index
original line
original column
name index
```

while preserving state across mapping segments as required by the format.

## Revision Replay

The project goes beyond parsing one `.map` file.

The intended reconstruction is historical:

```text
deployment evidence
        ↓
recover revision timeline
        ↓
associate runtime event with revision
        ↓
select generated artifact
        ↓
select matching source map
        ↓
resolve generated position
        ↓
recover original source location
```

Each result therefore depends on both mapping correctness and revision correctness.

## Chunk Identity

Applications are frequently split into multiple chunks.

For example:

```text
runtime.js
vendor.js
main.js
editor.js
settings.js
```

Chunk filenames may also include hashes:

```text
main.a81f7c2.js
main.d932ea1.js
```

A runtime location must be associated with the exact artifact that existed in the corresponding deployment state.

Filename similarity is not enough.

## Cached and Stale Artifacts

Browsers, service workers, CDNs, and long-lived pages can retain older application resources.

This means:

```text
current server revision
```

may differ from:

```text
revision executing in the affected browser
```

Historical reconstruction should therefore follow captured evidence rather than assuming that the newest deployment is always active.

## Hot Reload and Incremental Revision Changes

Development and some production-like systems can update only part of an application.

Conceptually:

```text
base revision
     ↓
chunk update A
     ↓
chunk update B
     ↓
runtime observation
```

The runtime may then contain artifacts originating from several revision events.

Where applicable, replay must preserve the correct artifact lifetime.

## Stack Trace Reconstruction

A stack frame might initially look like:

```text
at a (bundle.js:1:38192)
```

After revision and source-map reconstruction it can become something conceptually like:

```text
src/components/Editor.tsx
line 214
column 17
```

The purpose of the project is to derive that relationship from evidence, rather than guessing from current source.

## Common Failure Modes

### Using the newest source map

The newest map may belong to a later deployment.

### Matching only by filename

Several revisions can contain identically named chunks.

### Ignoring historical runtime lifetime

A page may continue running old code after a new deployment occurs.

### Treating mappings as simple offsets

Source-map mapping segments must be decoded correctly.

### Ignoring generated columns

Line-only mapping can resolve to the wrong original expression.

### Mixing source maps between chunks

Every generated artifact needs its corresponding map.

### Assuming stack traces contain original coordinates

Runtime traces normally reference generated code unless another system has already symbolicated them.

## Reconstruction Pipeline

A robust implementation can be viewed as:

```text
runtime observations
        +
revision evidence
        +
build artifacts
        +
source maps
        ↓
reconstruct deployment history
        ↓
resolve active artifact revision
        ↓
identify matching chunk
        ↓
decode source map
        ↓
map generated position
        ↓
recover original source
        ↓
emit required artifact
```

## Technical Areas

This project exercises:

- JavaScript
- frontend debugging
- source maps
- Base64 VLQ
- bundlers
- transpilation
- minification
- stack traces
- historical revision tracking
- deployment reconstruction
- browser caching
- artifact identity
- event replay
- production incident analysis
- deterministic data processing

## Validation

A correct implementation should preserve the relationship between:

```text
runtime event
revision
generated artifact
source map
original source
```

rather than treating source-map resolution as an isolated file-parsing problem.

The authoritative input semantics, output schema, ordering rules, and paths are defined in:

```text
instruction.md
```

## Goal

The goal of Source Map Revision Replay is to determine what source code actually produced a historical runtime observation.

The central principle is:

> A generated position is only meaningful when paired with the exact artifact revision that produced it.

## License

No license is currently specified.
