"""P4 silent LIVE recorder. Existing snapshots/results are never rewritten.

Uses the prepared demo kit; --inspect is read-only, --record admits one real
bootstrap, --resume reuses that take and records only stored-result views.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '_outside-repo/skills/mvp-demo/scripts'))
import demo_kit as K
from playwright.sync_api import Page, expect, sync_playwright

BASE = 'http://127.0.0.1:5173'
API = 'http://127.0.0.1:8000/api'
STATE = ROOT / 'scripts/demo/out/live-p4-20261031'
PRODUCT = 'REAL-PROD-R2'
EVENT = '15-bootstrap-real-foaming'
NAMES = ['01-product', '02-live', '02-result', '03-passport', '04-evidence', '05-why', '06-trace']


def get(path: str, role: str = 'OPERATOR') -> Any:
    request = Request(API + path, headers={'X-Demo-Role': role, 'X-Demo-Actor': 'demo-' + role.lower()})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def save(path: Path, data: Any) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def require_live(detail: dict[str, Any]) -> None:
    run, steps = detail['run'], detail['steps']
    if run['llm_mode'] != 'LIVE' or run['status'] not in ('COMPLETED', 'WAITING_REVIEW', 'WAITING_EVIDENCE'):
        raise ValueError(f"Unusable LIVE take: {run['status']} / {run.get('stop_reason')}")
    calls = [step for step in steps if step['actor'] == 'llm' and step['tokens_in'] > 0]
    if not calls or not all(step['detail'].get('replayed') is False for step in calls):
        raise ValueError('Provider token/replayed evidence missing')
    if any(step['detail'].get('replayed') is True or step['detail'].get('extractor') == 'FALLBACK'
           or step['detail'].get('mode') in ('FALLBACK','REPLAY') for step in steps):
        raise ValueError('Replay/fallback step cannot be presented as LIVE')


def require_saved_state(run: dict[str, Any], current_runs: list[dict[str, Any]],
                        saved_passport: dict[str, Any], current_passport: dict[str, Any], *,
                        saved_audit: dict[str, Any] | None = None,
                        current_audit: dict[str, Any] | None = None) -> None:
    """Reject stale takes before/after browser capture; never relabel a newer result."""
    case_runs = [row for row in current_runs if row['case_id'] == run['case_id']]
    current = next((row for row in case_runs if row['id'] == run['id']), None)
    keys = ('case_revision','status','stop_reason','llm_mode')
    if current is None or any(current.get(key) != run.get(key) for key in keys):
        raise ValueError('Saved run no longer matches server state')
    if any(row['id'] != run['id'] and row['case_revision'] >= run['case_revision'] for row in case_runs):
        raise ValueError('Case has a newer or competing run; preserve this take and record the new revision separately')
    if saved_passport != current_passport or saved_audit != current_audit:
        raise ValueError('Passport/audit changed since this take; refusing to mix revisions')


def check_current_take(detail: dict[str, Any], passport: dict[str, Any],
                       audit: dict[str, Any] | None = None) -> None:
    run = detail['run']
    current_audit = get('/cases/' + run['case_id'] + '/web-search') if audit is not None else None
    require_saved_state(run, get('/internal/runs'), passport,
                        get('/products/' + passport['product_id'] + '/passport', 'BUYER'),
                        saved_audit=audit, current_audit=current_audit)


def admitted_run_id(event_id: str, log: list[dict[str, Any]]) -> str | None:
    """Map external event identity to its run using the public event-log contract."""
    entry = next((row for row in log if row['event_id'] == event_id), None)
    return entry.get('run_id') if entry else None


def preflight() -> dict[str, Any]:
    health = get('/health')
    if health['llm_mode'] != 'live':
        raise ValueError('Expected actual server LLM_MODE=live')
    database = STATE / 'passport.db'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        local_ids = {row[0] for row in connection.execute('SELECT id FROM runs')}
    if {row['id'] for row in get('/internal/runs')} != local_ids:
        raise ValueError('API run state does not match isolated database')
    return health


def open_product(page: Page, role: str = 'BUYER') -> None:
    page.goto(BASE)
    page.evaluate('(role) => localStorage.setItem("ptp.demo-role", role)', role)
    page.goto(BASE + '/buyer/' + PRODUCT)
    expect(page.get_by_test_id('badge-origin')).to_have_text('REAL')
    if 'UI preview' in page.locator('body').inner_text():
        raise ValueError('Frontend mock transport is enabled')


def style(page: Page) -> None:
    # Presentation only: typography/spacing. No result text, badges or data changes.
    page.add_style_tag(content='''
      .purchase-bar {display:none!important}
      .product-image-wrap,.product-price,.shop-row {display:none!important}
      .product-note {margin-top:14px!important}
      .field-row {padding:12px 18px!important}
      .passport-heading {padding:20px!important}
      .field-description {margin:6px 0!important}
      .dialog {max-height:88vh!important}
      .dialog-body {font-size:18px!important}
      .evidence-passage blockquote {font-size:21px!important;line-height:1.55!important}
    ''')


def hold_until(seg: K.Segment, start: float, seconds: float) -> None:
    shortened = sum((end - begin) * (1 - 1 / factor) for begin, end, factor in seg.speedups)
    seg.hold(max(0, seconds - (seg.now() - start - shortened)))
    seg.end_here(tail=0)


def inspect() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    print(json.dumps(preflight(), ensure_ascii=False))
    with sync_playwright() as pw:
        browser = K.launch(pw)
        try:
            page = browser.new_page(viewport={'width':1280, 'height':720})
            open_product(page)
            style(page)
            page.screenshot(path=str(STATE / 'inspect.png'))
            print(page.locator('body').inner_text()[:6500])
        finally:
            browser.close()


def record(take: Path, resume: bool, refine: bool = False) -> None:
    health = preflight()
    if not resume:
        if any(run['case_id'] == 'REAL-CASE-R2' for run in get('/internal/runs')):
            raise ValueError('Case already has a run; use --resume with the original take')
        take.mkdir(parents=True, exist_ok=False)
        save(take / 'health-before.json', health)
    output = take / 'refined' if refine else take
    segments = output / 'segments'
    if refine:
        segments.mkdir(parents=True, exist_ok=False)
        for name in NAMES[:4]:
            shutil.copy2(take / 'segments' / (name + '.json'), segments / (name + '.json'))

    def product(seg: K.Segment) -> None:
        open_product(seg.page)
        style(seg.page)
        seg.trim_start(); start = seg.now()
        seg.chip('Sản phẩm REAL · Đối chiếu từng thông tin')
        seg.hold(5)
        seg.page.locator('.passport-card').scroll_into_view_if_needed()
        seg.chip('Nguồn đã chụp hôm nay · Chưa chạy đối chiếu')
        hold_until(seg, start, 10)

    def live(seg: K.Segment) -> None:
        page = seg.page
        open_product(page, 'OPERATOR')
        page.get_by_test_id('operator-nav').click()
        button = page.get_by_test_id('event-btn-' + EVENT)
        expect(button).to_be_visible()
        button.scroll_into_view_if_needed()
        seg.trim_start(); start = seg.now()
        seg.chip('Bắt đầu đối chiếu LIVE với OpenAI')
        seg.hold(2)
        with page.expect_response(lambda response: response.url.endswith('/internal/demo/fire/' + EVENT), timeout=180000) as pending:
            seg.click('[data-testid="event-btn-' + EVENT + '"]')
        response = pending.value
        if not response.ok:
            raise ValueError(f'Event failed: HTTP{response.status}')
        admitted = response.json()
        save(take / 'admission.json', admitted)
        if admitted['outcome'] != 'ADMITTED':
            raise ValueError('Event was not admitted')
        seg.chip('Đang xử lý LIVE · Đoạn chờ được tua nhanh')
        waiting = seg.now()
        deadline = time.monotonic() + 180
        while True:
            rows = get('/internal/runs')
            # Run trigger_event_id is a storage id, whereas admission returns the external event id.
            log = get('/internal/events/log')
            run_id = admitted_run_id(admitted['event_id'], log)
            run = next((row for row in rows if row['id'] == run_id), None)
            if run and run['status'] not in ('QUEUED', 'RUNNING'):
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Live run did not terminate')
            page.wait_for_timeout(700)
        seg.fast_forward(waiting, to=4)
        detail = get('/internal/runs/' + run['id'])
        save(take / 'first-run.json', detail)
        require_live(detail)
        seg.chip('Đã lưu kết quả LIVE · Xem từng trường')
        page.get_by_test_id('run-status').scroll_into_view_if_needed()
        expect(page.get_by_test_id('run-status')).to_have_text(run['status'], timeout=15000)
        hold_until(seg, start, 10)

    def result(seg: K.Segment) -> None:
        open_product(seg.page, 'OPERATOR')
        seg.page.get_by_test_id('operator-nav').click()
        expected_status = json.loads((take / 'first-run.json').read_text(encoding='utf-8'))['run']['status']
        expect(seg.page.get_by_test_id('run-status')).to_have_text(expected_status)
        seg.page.locator('.run-summary').scroll_into_view_if_needed()
        seg.trim_start(); start = seg.now()
        seg.chip('Kết quả LIVE đã lưu · Có trường cần người duyệt')
        hold_until(seg, start, 6)

    def passport(seg: K.Segment) -> None:
        open_product(seg.page)
        style(seg.page)
        seg.trim_start(); start = seg.now()
        seg.chip('Passport · Kết quả riêng cho từng trường')
        seg.hold(5)
        seg.page.get_by_test_id('field-row-responsible_company').scroll_into_view_if_needed()
        seg.chip('Thiếu bằng chứng vẫn được thể hiện rõ')
        hold_until(seg, start, 12)

    def evidence(seg: K.Segment) -> None:
        open_product(seg.page)
        style(seg.page)
        seg.page.get_by_test_id('evidence-open-skin_type').scroll_into_view_if_needed()
        seg.trim_start(); start = seg.now()
        seg.chip('Loại da · Mở đoạn trích đã lưu')
        seg.click('[data-testid="evidence-open-skin_type"]')
        expect(seg.page.locator('.evidence-passage').first).to_be_visible()
        seg.hold(11)
        groups = seg.page.locator('.evidence-group')
        if groups.count() > 1:
            groups.last.locator('header').evaluate('(element) => element.scrollIntoView({block:"start", behavior:"smooth"})')
        hold_until(seg, start, 24)

    def why(seg: K.Segment) -> None:
        open_product(seg.page, 'OPERATOR')
        style(seg.page)
        seg.page.get_by_test_id('why-open-skin_type').scroll_into_view_if_needed()
        seg.trim_start(); start = seg.now()
        seg.chip('Why? · Theo dõi luật đã áp dụng')
        seg.click('[data-testid="why-open-skin_type"]')
        expect(seg.page.locator('.decision-trail')).to_be_visible()
        seg.page.locator('.decision-trail li').nth(3).evaluate('(element) => element.scrollIntoView({block:"start"})')
        seg.hold(9)
        seg.page.locator('.decision-trail li').nth(4).scroll_into_view_if_needed()
        hold_until(seg, start, 14)

    def trace(seg: K.Segment) -> None:
        open_product(seg.page, 'OPERATOR')
        seg.page.get_by_test_id('operator-nav').click()
        expected_status = json.loads((take / 'first-run.json').read_text(encoding='utf-8'))['run']['status']
        expect(seg.page.get_by_test_id('run-status')).to_have_text(expected_status)
        seg.page.add_style_tag(content='.trace-table {font-size:16px!important} .run-summary {font-size:17px!important}')
        seg.page.locator('.run-summary').evaluate('(element) => element.scrollIntoView({block:"start"})')
        seg.trim_start(); start = seg.now()
        seg.chip('Trace thật · Model trích xuất, code quyết định')
        seg.hold(7)
        seg.page.locator('.metric-model').scroll_into_view_if_needed()
        seg.chip('Passport đọc kết quả đã lưu · Không gọi lại model')
        hold_until(seg, start, 14)

    if not resume:
        K.record_segment(NAMES[0], {}, product, segments)
        K.record_segment(NAMES[1], {}, live, segments)
    detail = json.loads((take / 'first-run.json').read_text(encoding='utf-8'))
    require_live(detail)
    saved_passport_path = take / 'passport.json'
    if not saved_passport_path.exists():
        save(saved_passport_path, get('/products/' + PRODUCT + '/passport', 'BUYER'))
    saved_passport = json.loads(saved_passport_path.read_text(encoding='utf-8'))
    check_current_take(detail, saved_passport)
    before = get('/internal/metrics')
    for name, body in zip(NAMES[2:], (result, passport, evidence, why, trace)):
        if not (segments / (name + '.json')).exists():
            K.record_segment(name, {}, body, segments)
    after = get('/internal/metrics')
    if any(before[key] != after[key] for key in ('model_calls', 'runs', 'jobs', 'events')):
        raise ValueError('Read-only video scenes created activity')
    check_current_take(detail, saved_passport)
    if not (output / 'read-check.json').exists():
        save(output / 'read-check.json', {'before':before, 'after':after})
    for field in ('volume', 'skin_type', 'key_ingredients', 'notification_number', 'responsible_company'):
        target = take / ('evidence-' + field + '.json')
        if not target.exists():
            data = get('/products/' + PRODUCT + '/fields/' + field + '/evidence', 'BUYER')
            for citation in data['citations']:
                if citation['excerpt'] not in citation['text']:
                    raise ValueError('Citation is not contained in stored passage')
            save(target, data)
    if not (take / 'passport.json').exists():
        save(take / 'passport.json', get('/products/' + PRODUCT + '/passport', 'BUYER'))
    K.assemble(NAMES, segments, output / 'demo.mp4', size=(1280,720))
    K.contact_sheet(output / 'demo.mp4', [3,12,23,31,42,54,66,78,86], output / 'contact-sheet.png')
    print('OUTPUT ' + str(output / 'demo.mp4'), flush=True)


def media_qa(folder: Path) -> None:
    video = folder / 'demo.mp4'
    K.run(['-i', str(video), '-f', 'null', '-'])
    result = subprocess.run([K.FF, '-i', str(video), '-af', 'volumedetect', '-f', 'null', '-'],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    (folder / 'media-qa.log').write_text(result.stderr, encoding='utf-8')
    print('DURATION ' + str(K.duration(video)))
    for line in result.stderr.splitlines():
        if 'Stream #' in line or 'max_volume:' in line:
            print(line)
    for index, start in enumerate((0,30,60), 1):
        K.contact_sheet(video, [start + n + .5 for n in range(0,30,2)],
                        folder / f'qa-{index}.png', width=480, cols=3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--audit-take', type=Path)
    parser.add_argument('--refine', type=Path)
    parser.add_argument('--qa', type=Path)
    args = parser.parse_args()
    if args.qa:
        media_qa(args.qa)
    elif args.refine:
        record(args.refine, True, refine=True)
    elif args.audit_take:
        take = args.audit_take
        admission = json.loads((take / 'admission.json').read_text(encoding='utf-8'))
        entry = next(row for row in get('/internal/events/log') if row['event_id'] == admission['event_id'])
        detail = get('/internal/runs/' + entry['run_id'])
        if not (take / 'first-run.json').exists():
            save(take / 'first-run.json', detail)
        require_live(detail)
        video = next((take / 'segments/02-live').glob('*.webm'))
        recovered = take / 'segments/02-live/recovered.mkv'
        if not recovered.exists():
            K.run(['-i', str(video), '-c', 'copy', str(recovered)])
        video = recovered
        print('RAW_DURATION ' + str(K.duration(video)))
        K.contact_sheet(video, [1,3,5,8,15,25,35,40,45,55], take / 'raw-live-sheet.png')
        print(json.dumps(detail['run'], ensure_ascii=False))
    elif args.inspect:
        inspect()
    elif args.record or args.resume:
        take = args.resume or STATE / ('take-' + uuid4().hex[:8])
        print('TAKE ' + str(take), flush=True)
        record(take, bool(args.resume))
    else:
        parser.error('Choose --inspect, --record or --resume TAKE')


if __name__ == '__main__':
    main()
