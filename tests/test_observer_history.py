from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infra.observer_history import IncidentHistory, history, load


class ObserverHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.at = datetime.now(timezone.utc)

    def tearDown(self):self.temp.cleanup()
    def time(self, seconds=0):return (self.at + timedelta(seconds=seconds)).isoformat()
    def sample(self, api=True, frontend=True):return {'api_readiness': api, 'frontend_liveness': frontend}

    def test_outage_recovery_survives_writer_restart_without_repeating_steady_events(self):
        writer = IncidentHistory(self.root, 8090)
        writer.observe(self.time(), self.sample())
        writer.observe(self.time(1), self.sample(False))
        writer.observe(self.time(2), self.sample(False))
        restarted = IncidentHistory(self.root, 8090)
        restarted.observe(self.time(3), self.sample())
        record = history(self.root)
        self.assertEqual([e['state'] for e in record['events']], ['unavailable', 'recovered'])
        self.assertEqual(record['events_total'], 2)
        self.assertIn('not live health', record['scope'])

    def test_initial_failure_is_recorded_and_healthy_boot_does_not_invent_recovery(self):
        writer = IncidentHistory(self.root, 8090)
        writer.observe(self.time(), self.sample())
        self.assertEqual(history(self.root)['events'], [])
        writer.observe(self.time(1), self.sample(frontend=False))
        self.assertEqual(history(self.root)['events'][0]['component'], 'frontend_liveness')
        with tempfile.TemporaryDirectory() as other:
            writer = IncidentHistory(Path(other), 8092)
            writer.observe(self.time(), self.sample(False))
            self.assertEqual(history(Path(other))['events'][0]['state'], 'unavailable')

    def test_retention_is_bounded_and_discarded_event_count_is_explicit(self):
        writer = IncidentHistory(self.root, 8090)
        for i in range(125):writer.observe(self.time(i), self.sample(bool(i % 2)))
        record = history(self.root)
        self.assertEqual(len(record['events']), 100)
        self.assertEqual(record['events_total'], 125)
        self.assertEqual(record['events_dropped'], 25)
        self.assertEqual(record['events'][0]['sequence'], 26)

    def test_changed_target_and_backwards_clock_do_not_modify_existing_history(self):
        writer = IncidentHistory(self.root, 8090);writer.observe(self.time(), self.sample(False))
        before = (self.root / 'incidents.json').read_bytes()
        with self.assertRaises(ValueError):IncidentHistory(self.root, 8092)
        with self.assertRaises(ValueError):writer.observe(self.time(-1), self.sample())
        self.assertEqual((self.root / 'incidents.json').read_bytes(), before)

    def test_failed_atomic_write_preserves_last_committed_state(self):
        writer = IncidentHistory(self.root, 8090);writer.observe(self.time(), self.sample())
        before = (self.root / 'incidents.json').read_bytes()
        with patch('pathlib.Path.replace', side_effect=OSError('PRIVATE')):
            with self.assertRaises(OSError):writer.observe(self.time(1), self.sample(False))
        self.assertEqual((self.root / 'incidents.json').read_bytes(), before)
        self.assertEqual(writer.record['events_total'], 0)
        self.assertFalse(list(self.root.glob('.incidents-*.tmp')))

    def test_malformed_and_unknown_fields_fail_closed_without_exposing_contents(self):
        writer = IncidentHistory(self.root, 8090);writer.observe(self.time(), self.sample(False))
        original = load(self.root)
        for mutate in [lambda r:r.update(private='PRIVATE'), lambda r:r.update(events_total=True),
                       lambda r:r['events'][0].update(sequence=7), lambda r:r.update(last_observed_at='invalid')]:
            record = json.loads(json.dumps(original));mutate(record)
            (self.root / 'incidents.json').write_text(json.dumps(record))
            result = history(self.root)
            self.assertFalse(result['recorded']);self.assertNotIn('PRIVATE', json.dumps(result))
            with self.assertRaises(ValueError):IncidentHistory(self.root, 8090)

    def test_missing_history_read_is_read_only_and_separate_from_health(self):
        self.assertEqual(history(self.root)['state'], 'not_recorded')
        self.assertEqual(list(self.root.iterdir()), [])
        writer = IncidentHistory(self.root, 8090);writer.observe(self.time(), self.sample())
        self.assertFalse((self.root / 'health.json').exists())
