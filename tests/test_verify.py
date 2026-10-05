import json
import math
from pathlib import Path

ARTIFACT = Path('/app/result.json')
EXPECTED = Path('/tests/expected.json')
TIME_TOL_MS = 0.150


def load_candidate():
    if not ARTIFACT.is_file():
        raise AssertionError('missing /app/result.json')
    try:
        obj = json.loads(ARTIFACT.read_text())
    except Exception as exc:
        raise AssertionError(f'invalid JSON: {exc}')

    assert isinstance(obj, dict)
    assert set(obj) == {'map_choices', 'frames', 'incidents', 'async_frames', 'message_pairs', 'causal_roots', 'task_bindings', 'task_paths'}
    for key in obj:
        assert isinstance(obj[key], list)

    for row in obj['map_choices']:
        assert isinstance(row, dict) and set(row) == {'revision', 'chunk', 'candidate'}
        assert all(isinstance(row[k], str) for k in row)

    for row in obj['frames']:
        assert isinstance(row, dict) and set(row) == {'frame_id', 'revision', 'source', 'line', 'column', 'name'}
        assert all(isinstance(row[k], str) for k in ('frame_id', 'revision', 'source', 'name'))
        assert type(row['line']) is int and row['line'] >= 1
        assert type(row['column']) is int and row['column'] >= 0

    for row in obj['incidents']:
        assert isinstance(row, dict) and set(row) == {'incident_id', 'root_frame_id', 'signature'}
        assert all(isinstance(row[k], str) for k in row)

    for row in obj['async_frames']:
        assert isinstance(row, dict) and set(row) == {'frame_id', 'event_id', 'revision', 'source', 'line', 'column', 'name'}
        assert all(isinstance(row[k], str) for k in ('frame_id', 'event_id', 'revision', 'source', 'name'))
        assert type(row['line']) is int and row['line'] >= 1
        assert type(row['column']) is int and row['column'] >= 0

    for row in obj['message_pairs']:
        assert isinstance(row, dict) and set(row) == {'channel', 'direction', 'send_event_id', 'recv_event_id', 'transit_ms'}
        assert all(isinstance(row[k], str) for k in ('channel', 'direction', 'send_event_id', 'recv_event_id'))
        assert type(row['transit_ms']) in (int, float) and math.isfinite(row['transit_ms']) and row['transit_ms'] >= 0

    for row in obj['causal_roots']:
        assert isinstance(row, dict) and set(row) == {'incident_id', 'trigger_event_id', 'trigger_frame_id', 'signature', 'latency_ms'}
        assert all(isinstance(row[k], str) for k in ('incident_id', 'trigger_event_id', 'trigger_frame_id', 'signature'))
        assert type(row['latency_ms']) in (int, float) and math.isfinite(row['latency_ms']) and row['latency_ms'] >= 0

    for row in obj['task_bindings']:
        assert isinstance(row, dict) and set(row) == {'event_id', 'task_uid', 'queue', 'marker_error_ms'}
        assert all(isinstance(row[k], str) for k in ('event_id', 'task_uid', 'queue'))
        assert type(row['marker_error_ms']) in (int, float) and math.isfinite(row['marker_error_ms'])

    for row in obj['task_paths']:
        assert isinstance(row, dict) and set(row) == {'incident_id', 'trigger_event_id', 'handoff_count', 'tasks'}
        assert isinstance(row['incident_id'], str) and isinstance(row['trigger_event_id'], str)
        assert type(row['handoff_count']) is int and row['handoff_count'] >= 0
        assert isinstance(row['tasks'], list) and row['tasks'] and all(isinstance(x, str) for x in row['tasks'])
    return obj


def canon(rows, keys):
    return sorted(rows, key=lambda row: tuple(row[k] for k in keys))


def test_schema_and_cardinality():
    got = load_candidate()
    exp = json.loads(EXPECTED.read_text())
    for key in ('map_choices', 'frames', 'incidents', 'async_frames', 'message_pairs', 'causal_roots', 'task_bindings', 'task_paths'):
        assert len(got[key]) == len(exp[key])
    assert len({r['frame_id'] for r in got['frames']}) == len(got['frames'])
    assert len({r['frame_id'] for r in got['async_frames']}) == len(got['async_frames'])
    assert len({r['incident_id'] for r in got['incidents']}) == len(got['incidents'])
    assert len({r['incident_id'] for r in got['causal_roots']}) == len(got['causal_roots'])
    assert len({(r['send_event_id'], r['recv_event_id']) for r in got['message_pairs']}) == len(got['message_pairs'])
    assert len({r['event_id'] for r in got['task_bindings']}) == len(got['task_bindings'])
    assert len({r['incident_id'] for r in got['task_paths']}) == len(got['task_paths'])


def test_source_reconstruction():
    got = load_candidate()
    exp = json.loads(EXPECTED.read_text())
    assert canon(got['map_choices'], ('revision', 'chunk')) == canon(exp['map_choices'], ('revision', 'chunk'))
    assert canon(got['frames'], ('frame_id',)) == canon(exp['frames'], ('frame_id',))
    assert canon(got['incidents'], ('incident_id',)) == canon(exp['incidents'], ('incident_id',))
    assert canon(got['async_frames'], ('frame_id',)) == canon(exp['async_frames'], ('frame_id',))


def test_message_reconciliation():
    got = load_candidate()
    exp = json.loads(EXPECTED.read_text())
    g = canon(got['message_pairs'], ('channel', 'direction', 'send_event_id', 'recv_event_id'))
    e = canon(exp['message_pairs'], ('channel', 'direction', 'send_event_id', 'recv_event_id'))
    assert [(r['channel'], r['direction'], r['send_event_id'], r['recv_event_id']) for r in g] == [
        (r['channel'], r['direction'], r['send_event_id'], r['recv_event_id']) for r in e
    ]
    for gr, er in zip(g, e):
        assert abs(float(gr['transit_ms']) - float(er['transit_ms'])) <= TIME_TOL_MS


def test_causal_roots():
    got = load_candidate()
    exp = json.loads(EXPECTED.read_text())
    g = canon(got['causal_roots'], ('incident_id',))
    e = canon(exp['causal_roots'], ('incident_id',))
    for gr, er in zip(g, e):
        assert gr['incident_id'] == er['incident_id']
        assert gr['trigger_event_id'] == er['trigger_event_id']
        assert gr['trigger_frame_id'] == er['trigger_frame_id']
        assert gr['signature'] == er['signature']
        assert abs(float(gr['latency_ms']) - float(er['latency_ms'])) <= TIME_TOL_MS

def test_scheduler_reconstruction():
    got = load_candidate()
    exp = json.loads(EXPECTED.read_text())
    g = canon(got['task_bindings'], ('event_id',))
    e = canon(exp['task_bindings'], ('event_id',))
    assert [(r['event_id'], r['task_uid'], r['queue']) for r in g] == [
        (r['event_id'], r['task_uid'], r['queue']) for r in e
    ]
    for gr, er in zip(g, e):
        assert abs(float(gr['marker_error_ms']) - float(er['marker_error_ms'])) <= TIME_TOL_MS

    gp = canon(got['task_paths'], ('incident_id',))
    ep = canon(exp['task_paths'], ('incident_id',))
    assert gp == ep

