"""Replay-only Local browser rehearsal. Never starts servers or changes run mode.

Python Playwright 1.64.1 (P4 pin). Official references checked 2026-10-31:
https://playwright.dev/python/docs/locators
https://playwright.dev/python/docs/test-assertions
--preflight-only is read-only; a real run requires an exclusive human-reserved slot.
Missing testids are reported as CCRs, never replaced with text/CSS selectors.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import Page, Error as BrowserError, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('volume', 'skin_type', 'key_ingredients', 'notification_number', 'responsible_company')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def preflight(base: str, api: str) -> None:
    """Only GETs; fail before reset, browser startup or any scenario mutation."""
    try:
        with urlopen(base, timeout=5) as response:
            require(response.status == 200, 'frontend did not answer HTTP 200')
        with urlopen(api + '/health', timeout=5) as response:
            health = json.load(response)
        require(isinstance(health, dict), 'health must be an object')
        require(str(health.get('llm_mode', '')).lower() == 'replay',
                'Local backend must report LLM_MODE=replay')
        delay = health.get('demo_run_delay_s')
        require(isinstance(delay, (int, float)) and not isinstance(delay, bool)
                and math.isfinite(delay) and delay >= 2,
                'Local backend must report DEMO_RUN_DELAY_S >= 2')
    except (URLError, TimeoutError, ValueError, AssertionError) as error:
        raise AssertionError(f'{error}. Start Local Actions backend/frontend with replay, '
                             'delay >=2 and VITE_USE_MOCK=0; reserve an exclusive run slot.') from error


def self_test() -> int:
    """Offline boundary tests; replace only the external HTTP seam, never scene code."""
    import io
    import sys
    import unittest
    from unittest.mock import patch

    class Response(io.BytesIO):
        status = 200

    class PreflightTests(unittest.TestCase):
        def check_health(self, mode: str, delay: object, accepted: bool) -> None:
            def fetch(url: str, **kwargs: object) -> Response:
                body = {'llm_mode': mode, 'demo_run_delay_s': delay} if url.endswith('/health') else {}
                return Response(json.dumps(body).encode('utf-8'))
            with patch(__name__ + '.urlopen', side_effect=fetch) as http:
                if accepted:
                    preflight('http://local', 'http://local/api')
                else:
                    with self.assertRaises(AssertionError):
                        preflight('http://local', 'http://local/api')
                self.assertEqual(http.call_count, 2)

        def test_replay_threshold(self) -> None:
            self.check_health('replay', 2, True)

        def test_unrelated_delay_variant(self) -> None:
            self.check_health('REPLAY', 4.75, True)

        def test_fallback_rejected(self) -> None:
            self.check_health('fallback', 3, False)

        def test_live_rejected(self) -> None:
            self.check_health('live', 3, False)

        def test_short_delay_rejected(self) -> None:
            self.check_health('replay', 1.99, False)

        def test_missing_delay_rejected(self) -> None:
            self.check_health('replay', None, False)

        def test_string_delay_rejected(self) -> None:
            self.check_health('replay', '3', False)

        def test_infinite_delay_rejected(self) -> None:
            self.check_health('replay', float('inf'), False)

        def test_boolean_delay_rejected(self) -> None:
            self.check_health('replay', True, False)

        def test_malformed_health_rejected(self) -> None:
            with patch(__name__ + '.urlopen', side_effect=[Response(b'{}'), Response(b'[]')]):
                with self.assertRaisesRegex(AssertionError, 'health must be an object'):
                    preflight('http://local', 'http://local/api')

        def test_unreachable_frontend(self) -> None:
            with patch(__name__ + '.urlopen', side_effect=URLError('offline')) as http:
                with self.assertRaisesRegex(AssertionError, 'Start Local Actions'):
                    preflight('http://local', 'http://local/api')
                self.assertEqual(http.call_count, 1)

        def test_cli_preflight_success_exit_zero(self) -> None:
            with patch.object(sys, 'argv', ['e2e.py', '--preflight-only']), patch(
                __name__ + '.urlopen', side_effect=[Response(b'{}'), Response(
                    b'{"llm_mode":"replay","demo_run_delay_s":3}')]
            ):
                self.assertEqual(main(), 0)

        def test_cli_preflight_failure_exit_one(self) -> None:
            with patch.object(sys, 'argv', ['e2e.py', '--preflight-only']), patch(
                __name__ + '.urlopen', side_effect=URLError('offline')
            ):
                self.assertEqual(main(), 1)

        def test_cli_missing_slot_exits_before_browser(self) -> None:
            with patch.object(sys, 'argv', ['e2e.py']), patch(
                __name__ + '.urlopen', side_effect=[Response(b'{}'), Response(
                    b'{"llm_mode":"replay","demo_run_delay_s":3}')]
            ), patch(__name__ + '.sync_playwright') as browser:
                self.assertEqual(main(), 1)
                browser.assert_not_called()

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PreflightTests))
    return int(not result.wasSuccessful())


@dataclass
class Journey:
    page: Page
    base: str
    api: str
    out: Path
    timeout: int = 120_000
    shot: int = 0

    def request(self, path: str, *, reset: bool = False) -> object:
        headers = {'X-Demo-Role': 'OPERATOR', 'X-Demo-Actor': 'demo-operator'}
        response = (self.page.request.post if reset else self.page.request.get)(
            self.api + path, headers=headers)
        require(response.ok, f'{path}: HTTP {response.status}')
        return response.json()

    def open(self, path: str, role: str = 'OPERATOR') -> None:
        # Set the documented demo session before the app initializes; no role control bypass.
        self.page.context.clear_cookies()
        self.page.goto(self.base)
        self.page.evaluate('(role) => localStorage.setItem("ptp.demo-role", role)', role)
        self.page.goto(self.base + path)

    def capture(self, name: str) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self.shot += 1
        self.page.screenshot(path=str(self.out / f'{self.shot:02d}-{name}.png'), full_page=True)

    def reset(self) -> None:
        # A long rehearsal must stop if the human restarts Local in another mode.
        preflight(self.base, self.api)
        self.request('/internal/demo/reset', reset=True)
        self.open('/')

    def fire(self, number: int, *, stale: bool = False) -> str:
        catalog = self.request('/internal/events/catalog')
        require(isinstance(catalog, list), 'catalog must be an array')
        # Resolve full fixture names from the catalog, including renamed descriptive suffixes.
        matches = [row for row in catalog if row['name'].startswith(f'{number:02d}-')]
        require(len(matches) == 1, f'event {number:02d}: missing/ambiguous catalog entry')
        event = matches[0]
        product = str(event['product_id'])
        self.open('/')
        with self.page.expect_response(lambda r: r.url.endswith('/internal/demo/fire/' + event['name'])) as pending:
            self.page.get_by_test_id('event-btn-' + event['name']).click()
        response = pending.value
        require(response.ok, f'event {number}: HTTP {response.status}')
        admitted = response.json()
        require(admitted.get('outcome') == 'ADMITTED', f'event {number} was not admitted')
        if stale:
            # Operator embeds the buyer rows; observe the delay without losing it on navigation.
            for field in ('notification_number', 'responsible_company'):
                expect(self.page.get_by_test_id('field-label-' + field)).to_have_text('Stale', timeout=1900)
            expect(self.page.get_by_test_id('field-label-volume')).not_to_have_text('Stale')
            self.capture('revoke-stale')
        deadline = time.monotonic() + self.timeout / 1000
        while True:
            runs = self.request('/internal/runs')
            require(isinstance(runs, list), 'runs must be an array')
            run = next((r for r in runs if r['trigger_event_id'] == admitted['event_id']), None)
            if run and run['status'] not in ('QUEUED', 'RUNNING'):
                require(run['status'] == 'COMPLETED', f"event {number}: {run['status']} / {run.get('stop_reason')}")
                require(run['llm_mode'] == 'REPLAY', 'run was not REPLAY')
                break
            require(time.monotonic() < deadline, f'event {number}: run deadline exceeded')
            # Synchronize with the existing UI polling response; no fixed sleeps.
            with self.page.expect_response(lambda r: r.url.endswith('/internal/runs'), timeout=10_000):
                pass
        expect(self.page.get_by_test_id('run-status')).to_have_text('COMPLETED', timeout=10_000)
        self.labels(product)
        self.capture(f'event-{number:02d}')
        print(f'PASS event-{number:02d}: completed replay; five field labels', flush=True)
        return product

    def labels(self, product: str) -> None:
        passport = self.request('/products/' + quote(product, safe='') + '/passport')
        require(isinstance(passport, dict), 'passport must be an object')
        fields = {row['field_key']: row for row in passport['fields']}
        require(set(fields) == set(FIELDS), 'passport must contain the five fields')
        self.open('/buyer/' + quote(product, safe=''), 'BUYER')
        for key in FIELDS:
            # Transport/UI projection check; scene-specific semantic assertions are independent below.
            expect(self.page.get_by_test_id('field-label-' + key)).to_have_text(fields[key]['label'], timeout=10_000)
        expect(self.page.get_by_test_id('badge-mode').first).to_have_text('REPLAY')

    def counter(self) -> str:
        self.open('/')
        locator = self.page.get_by_test_id('model-calls-counter')
        expect(locator).to_have_text(re.compile(r'^\d+$'))
        return locator.inner_text()


def scene_1(j: Journey) -> None:
    j.open('/')
    expect(j.page.get_by_test_id('event-btn-01-bootstrap-demo')).to_be_visible()


def scene_2(j: Journey) -> None:
    j.reset()
    j.fire(1)
    for key in FIELDS:
        expect(j.page.get_by_test_id('field-label-' + key)).to_have_text(
            'Single source' if key == 'skin_type' else 'Consistent')


def scene_3(j: Journey) -> None:
    j.reset()
    product = j.fire(15)
    j.page.get_by_test_id('evidence-open-skin_type').click()
    j.capture('real-evidence')
    before = j.counter()
    j.open('/buyer/' + quote(product, safe=''), 'BUYER')
    for _ in range(3):
        j.page.reload()
        expect(j.page.get_by_test_id('field-label-skin_type')).to_be_visible()
    require(j.counter() == before, 'three buyer refreshes changed model calls')


def scene_4(j: Journey) -> None:
    j.reset()
    product = j.fire(14)
    expect(j.page.get_by_test_id('field-label-skin_type')).to_have_text('Conflict in source')
    j.page.get_by_test_id('why-open-skin_type').click()
    j.capture('source-conflict-why')
    j.open('/buyer/' + quote(product, safe=''), 'BUYER')
    j.page.get_by_test_id('evidence-open-key_ingredients').click()


def scene_5(j: Journey) -> None:
    j.reset()
    j.fire(1)
    j.fire(5, stale=True)
    for key in ('notification_number', 'responsible_company'):
        expect(j.page.get_by_test_id('field-label-' + key)).to_have_text('Not verified')
    expect(j.page.get_by_test_id('field-label-volume')).to_have_text('Consistent')


def scene_6(j: Journey) -> None:
    j.reset()
    j.fire(1)
    j.fire(9)
    j.open('/')
    expect(j.page.get_by_test_id('agent-panel')).to_contain_text(
        re.compile(r'verified by code \(anchor:|No change recorded\.'), timeout=10_000)


def scene_7(j: Journey) -> None:
    j.reset()
    product = j.fire(14)
    # Keep the requested product selected within the SPA when opening its control room.
    # CCR P3 Local/P4: add operator-nav to the existing Operator navigation link.
    j.open('/buyer/' + quote(product, safe=''), 'OPERATOR')
    expect(j.page.get_by_test_id('field-label-skin_type')).to_be_visible()
    j.page.get_by_test_id('operator-nav').click()
    # CCR P3 Local/P4: expose a semantic snapshot count on the existing web-audit testid.
    expect(j.page.get_by_test_id('web-audit')).to_have_attribute(
        'data-snapshot-count', re.compile(r'^[1-9]\d*$'), timeout=10_000)


def scene_8(j: Journey) -> None:
    j.reset()
    j.fire(13)
    j.open('/reviewer', 'REVIEWER')
    tasks = j.page.get_by_test_id(re.compile(r'^review-task-claim:'))
    expect(tasks.first).to_be_visible()
    tasks.first.click()


def scene_9(j: Journey) -> None:
    j.reset()
    j.fire(1)
    product = j.fire(4)
    expect(j.page.get_by_test_id('field-label-volume')).to_have_text('Conflicting')
    j.open('/reviewer', 'REVIEWER')
    j.page.get_by_test_id('review-task-volume').click()
    # CCR P3 Local/P4: review-reason is absent from S3; fail instead of a fragile selector.
    j.page.get_by_test_id('review-reason').fill('Reviewed the cited passages for this revision.')
    j.page.get_by_test_id('review-approve').click()
    expect(j.page.get_by_test_id(re.compile(r'^review-decision-')).filter(
        has_text='Reviewed the cited passages for this revision.')).to_contain_text('APPROVE')
    j.capture('durable-review')
    j.open('/buyer/' + quote(product, safe=''), 'BUYER')
    j.page.get_by_test_id('buy-button').click()
    j.page.wait_for_url('**/orders/*')
    receipt = j.page.url
    j.fire(7)
    j.open(receipt.removeprefix(j.base), 'BUYER')
    expect(j.page.get_by_test_id('receipt-diff')).to_contain_text(re.compile('changed since purchase', re.I))


SCENES: tuple[Callable[[Journey], None], ...] = (
    scene_1, scene_2, scene_3, scene_4, scene_5, scene_6, scene_7, scene_8, scene_9)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--base', default='http://127.0.0.1:5173')
    result.add_argument('--api', default='http://127.0.0.1:8000/api')
    result.add_argument('--out', type=Path, default=ROOT / 'scripts/demo/out/e2e')
    result.add_argument('--preflight-only', action='store_true')
    result.add_argument('--self-test', action='store_true', help='Offline preflight boundary checks; no servers')
    result.add_argument('--exclusive-slot', action='store_true', help='Human has reserved the Local servers for this run')
    result.add_argument('--headed', action='store_true')
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        return self_test()
    try:
        preflight(args.base, args.api)
        print('PASS preflight: Local replay and delay >=2')
        if args.preflight_only:
            return 0
        require(args.exclusive_slot, 'Reserve the Local run slot, then pass --exclusive-slot; no reset performed')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = context.new_page()
            page.set_default_timeout(10_000)
            journey = Journey(page, args.base.rstrip('/'), args.api.rstrip('/'), args.out / uuid4().hex)
            failures = 0
            try:
                for scene in SCENES:
                    try:
                        scene(journey)
                        journey.capture(scene.__name__)
                        print(f'PASS {scene.__name__}', flush=True)
                    except (AssertionError, BrowserError, KeyError, TypeError, ValueError) as error:
                        failures += 1
                        print(f'FAIL {scene.__name__}: {error}', flush=True)
                        try:
                            journey.capture(scene.__name__ + '-FAIL')
                        except (BrowserError, OSError) as capture_error:
                            print(f'FAIL {scene.__name__} screenshot: {capture_error}', flush=True)
            finally:
                context.close()
                browser.close()
            return int(failures > 0)
    except (AssertionError, BrowserError) as error:
        print(f'FAIL preflight: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
