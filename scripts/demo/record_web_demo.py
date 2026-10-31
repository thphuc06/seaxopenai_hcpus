"""Record one real web-search request through the existing operator API.

No UI button is fabricated: the opening callout discloses the API trigger.
Original video/database/results are retained; every call uses the live server.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from playwright.sync_api import expect

from record_live_demo import API, STATE, K, admitted_run_id, check_current_take, get, hold_until, open_product, preflight, save, style

CASE = 'REAL-CASE-R2'


def validate_web(detail: dict, audit: dict) -> None:
    """A partial fetch can be shown honestly; replay, fallback and invented sources cannot."""
    if detail['run']['llm_mode'] != 'LIVE':
        raise ValueError('Web run is not LIVE')
    if detail['run']['status'] not in ('COMPLETED','WAITING_REVIEW','WAITING_EVIDENCE','PARTIAL'):
        raise ValueError('Web receipt has no presentable terminal state')
    steps = detail['steps']
    if any(step.get('detail', {}).get('mode') in ('FALLBACK','REPLAY') or
           step.get('detail', {}).get('replayed') is True for step in steps):
        raise ValueError('Web run contains fallback/replay')
    searches = [step for step in steps if step['step'] == 'web:search' and
                step['actor'] == 'llm' and step['detail'].get('replayed') is False and not step.get('error')]
    if not searches or not audit['queries'] or any(query['mode'] != 'LIVE' for query in audit['queries']):
        raise ValueError('Actual live search evidence is missing')
    stored = {step['detail']['source_version_id'] for step in steps if step['step'] == 'web:snapshot'}
    if not audit['snapshots']:
        raise ValueError('No newly stored web snapshots')
    for snapshot in audit['snapshots']:
        if (snapshot['source_version_id'] not in stored or snapshot['dataset_origin'] != 'REAL'
                or not snapshot['identity_verified'] or not snapshot['passages']):
            raise ValueError('Snapshot has no current-run identity/passage evidence')


def record_web(out: Path) -> None:
    health = preflight()
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'health.json', health)
    save(out / 'passport-before.json', get('/products/REAL-PROD-R2/passport', 'BUYER'))
    save(out / 'audit-before.json', get('/cases/' + CASE + '/web-search'))
    with sqlite3.connect((STATE / 'passport.db').as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(out / 'before.db') as backup:
            source.backup(backup)

    def discovery(seg: K.Segment) -> None:
        page = seg.page
        open_product(page, 'OPERATOR')
        page.get_by_test_id('operator-nav').click()
        expect(page.get_by_test_id('web-audit')).to_be_visible()
        page.get_by_test_id('web-audit').scroll_into_view_if_needed()
        page.add_style_tag(content='[data-testid="web-audit"] {font-size:18px!important;line-height:1.45!important}')
        seg.trim_start()
        seg.chip('Gửi yêu cầu Web Search LIVE qua API')
        seg.hold(2)
        response = page.request.post(API + '/cases/' + CASE + '/web-search',
            headers={'X-Demo-Role':'OPERATOR', 'X-Demo-Actor':'demo-operator'}, timeout=180000)
        if not response.ok:
            raise RuntimeError('Web request returned HTTP' + str(response.status))
        admission = response.json()
        save(out / 'admission.json', admission)
        if admission['outcome'] != 'ADMITTED':
            raise RuntimeError('Web request did not create a run: ' + admission['outcome'])
        seg.chip('Đang tìm và kiểm tra nguồn · Đoạn chờ tua nhanh')
        waiting = seg.now()
        deadline = time.monotonic() + 160
        run = None
        while time.monotonic() < deadline:
            run_id = admitted_run_id(admission['event_id'], get('/internal/events/log'))
            if run_id:
                run = get('/internal/runs/' + run_id)
                if run['run']['status'] not in ('QUEUED','RUNNING'):
                    break
            page.wait_for_timeout(750)
        seg.fast_forward(waiting, to=3)
        if run is None:
            raise RuntimeError('No persisted web run')
        if run['run']['status'] in ('QUEUED','RUNNING'):
            raise TimeoutError('Web run is still active after the recording deadline')
        save(out / 'first-web-run.json', run)
        save(out / 'audit-after.json', get('/cases/' + CASE + '/web-search'))
        save(out / 'passport-after.json', get('/products/REAL-PROD-R2/passport', 'BUYER'))
        print(json.dumps({'run':run['run'], 'queries':len(get('/cases/' + CASE + '/web-search')['queries']),
                         'snapshots':len(get('/cases/' + CASE + '/web-search')['snapshots'])}, ensure_ascii=False), flush=True)
        seg.chip('Kết quả tìm nguồn được lưu trong Web audit')
        # Let the existing audit's polling settle; read-only HTTP polling makes no new search.
        page.wait_for_timeout(11000)
        page.get_by_test_id('web-audit').scroll_into_view_if_needed()
        seg.hold(8)
        seg.end_here(tail=0)

    K.record_segment('07-web-live', {}, discovery, out / 'segments')
    K.assemble(['07-web-live'], out / 'segments', out / 'web-discovery.mp4', size=(1280,720))
    print('WEB_TAKE ' + str(out), flush=True)


def assemble_web_cut(web_take: Path, initial: Path) -> None:
    detail = json.loads((web_take / 'first-web-run.json').read_text(encoding='utf-8'))
    audit = json.loads((web_take / 'audit-after.json').read_text(encoding='utf-8'))
    passport_after = json.loads((web_take / 'passport-after.json').read_text(encoding='utf-8'))
    validate_web(detail, audit)
    check_current_take(detail, passport_after, audit)
    out = web_take / 'final'
    segments = out / 'segments'
    segments.mkdir(parents=True, exist_ok=False)
    before = get('/internal/metrics')

    # Reuse actual original click footage. Only timing metadata is copied/trimmed.
    for name, seconds in (('01-product',5), ('02-live',8), ('02-result',4)):
        info = json.loads((initial / 'segments' / (name + '.json')).read_text(encoding='utf-8'))
        if name == '02-live':
            a,b,_ = info['speedups'][0]
            normal = info['end_s'] - info['start_s'] - (b-a)
            info['speedups'][0][2] = (b-a)/(seconds-normal)
        else:
            info['end_s'] = info['start_s'] + seconds
        save(segments / (name + '.json'), info)
    trigger = json.loads((web_take / 'segments/07-web-live.json').read_text(encoding='utf-8'))
    a,b,_ = trigger['speedups'][0]
    trigger['end_s'] = b
    trigger['speedups'][0][2] = (b-a)/(5-(a-trigger['start_s']))
    save(segments / '07-web-live.json', trigger)

    def audit_scene(seg: K.Segment) -> None:
        page = seg.page
        open_product(page, 'OPERATOR')
        page.get_by_test_id('operator-nav').click()
        panel = page.get_by_test_id('web-audit')
        expect(panel).to_be_visible()
        page.add_style_tag(content='[data-testid="web-audit"] {font-size:17px!important;line-height:1.45!important}')
        panel.locator('h3').evaluate('(e)=>e.scrollIntoView({block:"start"})')
        seg.trim_start(); start = seg.now()
        seg.chip('Web Search LIVE · Query và quyết định chọn nguồn')
        seg.hold(4)
        panel.locator('.audit-results').last.locator('li').last.scroll_into_view_if_needed()
        blocked = {result['url'] for query in audit['queries'] for result in query['results']
                   if result.get('reason') == 'HTTP_STATUS_403'}
        seg.chip(f'{len(blocked)} trang bị chặn HTTP 403 · Ghi rõ trong audit' if blocked
                 else 'Audit ghi rõ nguồn được chọn và nguồn bỏ qua')
        seg.hold(5)
        panel.locator('.audit-snapshot').first.evaluate('(e)=>e.scrollIntoView({block:"start"})')
        seg.chip(f'Đã fetch và lưu {len(audit["snapshots"])} snapshot REAL mới')
        seg.hold(5)
        panel.locator('.audit-snapshot').last.locator('summary').click()
        passages = audit['snapshots'][-1]['passages']
        index = next(i for i,p in enumerate(passages) if 'Đối tượng sử dụng' in p['text'])
        panel.locator('.audit-snapshot').last.locator('blockquote').nth(index).scroll_into_view_if_needed()
        seg.chip('Đọc nguyên văn trang vừa tải · Không lấy snippet làm bằng chứng')
        hold_until(seg,start,20)

    def passport(seg: K.Segment) -> None:
        open_product(seg.page)
        style(seg.page)
        seg.trim_start(); start=seg.now()
        seg.chip('Passport sau khi đối chiếu với nguồn web mới')
        seg.hold(5)
        seg.page.get_by_test_id('field-row-responsible_company').scroll_into_view_if_needed()
        seg.chip('Giữ nguyên trường thiếu bằng chứng và cần duyệt')
        hold_until(seg,start,10)

    def evidence(seg: K.Segment) -> None:
        open_product(seg.page)
        style(seg.page)
        seg.page.get_by_test_id('evidence-open-skin_type').scroll_into_view_if_needed()
        seg.trim_start(); start=seg.now()
        seg.chip('Bằng chứng có thêm trang web vừa được lưu')
        seg.click('[data-testid="evidence-open-skin_type"]')
        expect(seg.page.locator('.evidence-passage').first).to_be_visible()
        seg.hold(8)
        seg.page.locator('.evidence-group').nth(1).locator('header').evaluate('(e)=>e.scrollIntoView({block:"start",behavior:"smooth"})')
        hold_until(seg,start,18)

    def why(seg: K.Segment) -> None:
        open_product(seg.page,'OPERATOR')
        style(seg.page)
        seg.page.get_by_test_id('why-open-skin_type').scroll_into_view_if_needed()
        seg.trim_start(); start=seg.now()
        seg.chip('Why? · Code đếm nhóm nguồn và kiểm tra trích dẫn')
        seg.click('[data-testid="why-open-skin_type"]')
        expect(seg.page.locator('.decision-trail')).to_be_visible()
        seg.page.locator('.decision-trail li').nth(3).evaluate('(e)=>e.scrollIntoView({block:"start"})')
        hold_until(seg,start,10)

    def trace(seg: K.Segment) -> None:
        open_product(seg.page,'OPERATOR')
        seg.page.get_by_test_id('operator-nav').click()
        expect(seg.page.get_by_test_id('run-status')).to_have_text(detail['run']['status'])
        seg.page.add_style_tag(content='.trace-table {font-size:16px!important} .run-summary {font-size:17px!important}')
        seg.page.locator('.run-summary').evaluate('(e)=>e.scrollIntoView({block:"start"})')
        seg.trim_start(); start=seg.now()
        seg.chip(f'LIVE · {detail["run"]["status"]} · {detail["run"].get("stop_reason") or "Đã xử lý"}')
        seg.hold(5)
        seg.page.locator('.trace-row').filter(has_text='web:snapshot').first.scroll_into_view_if_needed()
        seg.chip('Trace: tìm kiếm → fetch → lưu snapshot → đối chiếu')
        hold_until(seg,start,10)

    new_names = ['08-web-audit','09-passport','10-evidence','11-why','12-web-trace']
    for name, body in zip(new_names,(audit_scene,passport,evidence,why,trace)):
        K.record_segment(name,{},body,segments)
    after=get('/internal/metrics')
    if any(before[key] != after[key] for key in ('model_calls','runs','jobs','events')):
        raise ValueError('Read-only recut created new activity')
    check_current_take(detail, passport_after, audit)
    save(out/'read-check.json',{'before':before,'after':after})
    for field in ('volume','skin_type','key_ingredients','notification_number','responsible_company'):
        evidence_data=get('/products/REAL-PROD-R2/fields/'+field+'/evidence','BUYER')
        if any(citation['excerpt'] not in citation['text'] for citation in evidence_data['citations']):
            raise ValueError('Unlocated published excerpt')
        save(out/('evidence-'+field+'.json'),evidence_data)
    names=['01-product','02-live','02-result','07-web-live']+new_names
    K.assemble(names,segments,out/'demo.mp4',size=(1280,720))
    K.contact_sheet(out/'demo.mp4',[3,10,15,19,25,30,36,45,56,66,75,85],out/'contact-sheet.png')
    print('FINAL '+str(out/'demo.mp4'),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--assemble', type=Path)
    parser.add_argument('--initial', type=Path, default=STATE/'take-b375bf49')
    args = parser.parse_args()
    if args.assemble:
        assemble_web_cut(args.assemble,args.initial)
    else:
        record_web(args.out or STATE / ('web-' + uuid4().hex[:8]))
