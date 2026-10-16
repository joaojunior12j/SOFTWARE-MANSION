"""Civil-time calendar, bounded PIR sensitivity and read-only API tests."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.core.risk_calendar import RiskCalendar
from backend.simulator.engine import SimulationEngine
from backend.simulator.scenarios.rf_jammer import build_rf_jammer
from backend.simulator.scenarios.wall_jump import build_wall_jump
from backend.simulator.sensors.pir import PIRSensor
from tests.test_api import FakeAlarmRepository, SETTINGS as API_SETTINGS
from tests.test_rf_jammer import SETTINGS as RF_SETTINGS
from tests.test_wall_jump import SETTINGS as WALL_SETTINGS


CONFIG = {
    'enabled': True, 'timezone': 'America/Sao_Paulo',
    'pir_alpha_multiplier': 1.5,
    'high_risk_times': [{'weekday': 6, 'hour': 23}],
    'high_risk_holidays': ['2027-01-01'],
}
START = datetime(2026, 10, 19, 2, tzinfo=timezone.utc)  # Sunday 23:00 local.


class RiskCalendarTests(unittest.TestCase):
    """Verify civil boundaries using aware clocks, not wall-clock sleeps."""

    def setUp(self):
        self.calendar = RiskCalendar(CONFIG)

    def test_hour_boundaries_utc_conversion_and_week_rollover(self):
        for delta, mode in ((-0.000001, 'STANDARD'), (0, 'ELEVATED'),
                            (3599.999999, 'ELEVATED'), (3600, 'STANDARD')):
            with self.subTest(delta=delta):
                result = self.calendar.evaluate(
                    START + timedelta(seconds=delta))
                self.assertEqual(result.mode, mode)
                self.assertEqual(result.pir_alpha_multiplier,
                                 1.5 if mode == 'ELEVATED' else 1.0)
        self.assertEqual(self.calendar.evaluate(START).local_time.weekday(), 6)
        self.assertEqual(self.calendar.evaluate(START).local_time.hour, 23)

    def test_entire_date_year_boundary_and_overlap_never_stack(self):
        start = datetime(2027, 1, 1, 3, tzinfo=timezone.utc)
        for delta, mode in ((-0.000001, 'STANDARD'), (0, 'ELEVATED'),
                            (86399.999999, 'ELEVATED'), (86400, 'STANDARD')):
            self.assertEqual(self.calendar.evaluate(
                start + timedelta(seconds=delta)).mode, mode)
        overlap = RiskCalendar({
            **CONFIG, 'high_risk_holidays': ['2026-10-18']})
        result = overlap.evaluate(START)
        self.assertEqual(result.reason, 'configured_date')
        self.assertEqual(result.pir_alpha_multiplier, 1.5)

    def test_disabled_missing_and_empty_schedules(self):
        for calendar in (RiskCalendar({**CONFIG, 'enabled': False}),
                         RiskCalendar.from_settings({})):
            result = calendar.evaluate(START)
            self.assertEqual((result.mode, result.reason,
                              result.pir_alpha_multiplier),
                             ('DISABLED', 'disabled', 1))
        self.assertEqual(RiskCalendar({}).evaluate(START).mode, 'STANDARD')

    def test_equivalent_offsets_and_naive_clock_rejection(self):
        local = START.astimezone(timezone(timedelta(hours=-3)))
        self.assertEqual(self.calendar.evaluate(local),
                         self.calendar.evaluate(START))
        with self.assertRaises(ValueError):
            self.calendar.evaluate(datetime(2026, 10, 18, 23))
        self.assertIsNotNone(self.calendar.evaluate().evaluated_at.tzinfo)

    def test_dst_fall_both_repeated_hours_and_spring_nonexistent_hour(self):
        calendar = RiskCalendar({**CONFIG, 'timezone': 'America/New_York',
                                 'high_risk_times': [
                                     {'weekday': 6, 'hour': 1}]})
        for hour in (5, 6):  # Both occurrences of Sunday 01:30.
            instant = datetime(2026, 11, 1, hour, 30, tzinfo=timezone.utc)
            self.assertEqual(calendar.evaluate(instant).mode, 'ELEVATED')
        spring = RiskCalendar({**CONFIG, 'timezone': 'America/New_York',
                               'high_risk_times': [{'weekday': 6, 'hour': 2}]})
        for hour in (6, 7):  # Jumps from 01:30 to 03:30: no invented 02:30.
            instant = datetime(2026, 3, 8, hour, 30, tzinfo=timezone.utc)
            self.assertEqual(spring.evaluate(instant).mode, 'STANDARD')

    def test_reject_invalid_configuration(self):
        for config in (None, [], {'typo': True}, {'enabled': 1},
                       {'timezone': 'Invalid/Zone'}, {'timezone': None},
                       {'pir_alpha_multiplier': True},
                       {'pir_alpha_multiplier': '1.5'},
                       {'pir_alpha_multiplier': 0.99},
                       {'pir_alpha_multiplier': 3.01},
                       {'pir_alpha_multiplier': math.inf},
                       {'high_risk_times': None},
                       {'high_risk_holidays': '2027-01-01'}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                RiskCalendar(config)
        for item in (None, {}, {'weekday': 7, 'hour': 1},
                     {'weekday': -1, 'hour': 1}, {'weekday': True, 'hour': 1},
                     {'weekday': 1, 'hour': 24}, {'weekday': 1, 'hour': -1},
                     {'weekday': 1, 'hour': True},
                     {'weekday': 1, 'hour': 1, 'extra': 1}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                RiskCalendar({'high_risk_times': [item]})
        for item in (None, 20270101, '2027-02-29', '20270101', '2027-1-1'):
            with self.subTest(item=item), self.assertRaises(ValueError):
                RiskCalendar({'high_risk_holidays': [item]})

    def test_leap_date_and_multiplier_bounds(self):
        calendar = RiskCalendar({'high_risk_holidays': ['2028-02-29']})
        instant = datetime(2028, 2, 29, 3, tzinfo=timezone.utc)
        self.assertEqual(calendar.evaluate(instant).mode, 'ELEVATED')
        for factor in (1, 3):
            self.assertEqual(RiskCalendar({**CONFIG,
                             'pir_alpha_multiplier': factor}).evaluate(
                                 START).pir_alpha_multiplier, factor)


class RiskPIRTests(unittest.TestCase):
    """Check actual detection changes, reversion and simulated event time."""

    def settings(self):
        return {**deepcopy(WALL_SETTINGS), 'risk_calendar': deepcopy(CONFIG)}

    def test_recalculates_same_sensor_without_mutating_or_stacking(self):
        current = [START - timedelta(seconds=1)]
        sensor = PIRSensor.from_settings(self.settings(),
                                         now_factory=lambda: current[0])
        baseline = sensor.detection_probability(35.5)
        current[0] = START
        elevated = sensor.detection_probability(35.5)
        self.assertGreater(elevated, baseline)
        self.assertAlmostEqual(elevated, .97 * (1 - math.exp(-.35 * 1.5)))
        self.assertEqual(sensor.detection_probability(35.5), elevated)
        self.assertEqual(sensor.alpha, .35)
        self.assertEqual(sensor.p_base, .97)
        current[0] = START + timedelta(hours=1)
        self.assertEqual(sensor.detection_probability(35.5), baseline)

    def test_detection_bounds_zero_contrast_and_effect_on_sampling(self):
        sensor = PIRSensor.from_settings(self.settings(), rng=Mock())
        for temperature in (-200, 0, 35.5, 36.5, 37.5, 200):
            probability = sensor.detection_probability(temperature, at=START)
            self.assertTrue(0 <= probability <= sensor.p_base)
        self.assertEqual(sensor.detection_probability(36.5, at=START), 0)
        sensor.rng.random.return_value = .34
        self.assertFalse(sensor.detect(35.5, at=START - timedelta(seconds=1)))
        self.assertTrue(sensor.detect(35.5, at=START))

    def test_legacy_without_calendar_matches_base_formula(self):
        sensor = PIRSensor.from_settings(WALL_SETTINGS)
        self.assertAlmostEqual(sensor.detection_probability(35.5, at=START),
                               .97 * (1 - math.exp(-.35)))

    def test_scenarios_use_event_time_independent_of_acceleration(self):
        settings = self.settings()
        settings['simulator']['scenarios'].update(
            deepcopy(RF_SETTINGS['simulator']['scenarios']))
        settings['correlation_engine'] = RF_SETTINGS['correlation_engine']
        start = START - timedelta(seconds=2)
        for build, name, offset in ((build_wall_jump, 'wall_jump', 4),
                                    (build_rf_jammer, 'rf_jammer', 10)):
            for speed in (1, 10):
                with self.subTest(name=name, speed=speed):
                    scenario = build(settings, now_factory=lambda: start)
                    with patch.object(PIRSensor, 'detect',
                                      return_value=True) as detect:
                        result = SimulationEngine({name: scenario}).run(
                            name, '1234', speed)
                    expected = start + timedelta(seconds=offset)
                    detect.assert_called_once_with(at=expected)
                    self.assertEqual(next(e.timestamp for e in result.events
                                          if e.device_hardware_id.startswith(
                                              'PIR-')), expected)


class RiskAPITests(unittest.TestCase):
    """Separate HTTP status contract with a controlled server-side clock."""

    def test_modes_follow_server_clock_and_ignore_client_override(self):
        current = [START - timedelta(seconds=1)]
        app = create_app({**API_SETTINGS, 'risk_calendar': CONFIG},
                         alarm_repository=FakeAlarmRepository(),
                         start_services=False, risk_clock=lambda: current[0])
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/risco').json()['mode'],
                             'STANDARD')
            current[0] = START
            response = client.get('/api/risco?at=2000-01-01')
            self.assertEqual(response.status_code, 200)
            value = response.json()
            self.assertEqual(value['mode'], 'ELEVATED')
            self.assertEqual(value['scope'], 'SIMULATOR_PIR')
            self.assertEqual(value['timezone'], 'America/Sao_Paulo')
            self.assertEqual(value['pir_alpha_multiplier'], 1.5)
            self.assertTrue(value['local_time'].endswith('-03:00'))
            current[0] += timedelta(hours=1)
            self.assertEqual(client.get('/api/risco').json()['mode'],
                             'STANDARD')
            self.assertIn('/api/risco',
                          client.get('/openapi.json').json()['paths'])

    def test_missing_calendar_is_disabled_and_invalid_settings_fail_fast(self):
        app = create_app(API_SETTINGS, alarm_repository=FakeAlarmRepository(),
                         start_services=False, risk_clock=lambda: START)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/risco').json()['mode'],
                             'DISABLED')
        with self.assertRaises(ValueError):
            create_app({**API_SETTINGS, 'risk_calendar': {'timezone': 'bad'}},
                       alarm_repository=FakeAlarmRepository(),
                       start_services=False)
