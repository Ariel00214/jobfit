"""Real-browser regression for long JD screenshots and slice failure handling."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from server import Handler, ThreadingHTTPServer


def make_jd(path, height):
    image = Image.new('RGB', (432, height), 'white')
    draw = ImageDraw.Draw(image)
    try: font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 21)
    except OSError: font = ImageFont.load_default(size=21)
    count = 5 if height < 800 else 18
    lines = ['职位名称：高级产品经理', '公司名称：示例科技有限公司', '岗位职责：']
    lines += [f'{i}. 负责产品路线图第{i}项规划与交付。' for i in range(1, count + 1)]
    lines += ['任职要求：']
    lines += [f'{i}. 要求编号{100+i}，具备数据分析和用户研究能力。' for i in range(1, count + 1)]
    step = max(38, (height - 50) // len(lines))
    for index, line in enumerate(lines):
        draw.text((12, 16 + index * step), line, fill='black', font=font)
    image.save(path, optimize=True)


def add_image(page, path):
    page.locator('#add').click(); page.locator('[data-mode="image"]').click()
    page.locator('#jd-image').set_input_files(str(path))
    page.get_by_text('1 张已就绪', exact=True).wait_for()
    page.locator('#save-jd').click()
    page.locator('.overlay').wait_for(state='detached', timeout=360000)
    return page.evaluate('state.jds[state.jds.length-1]')


def main():
    os.makedirs('work', exist_ok=True)
    with tempfile.TemporaryDirectory(dir='work') as folder:
        normal = Path(folder) / 'normal.png'; make_jd(normal, 700)
        long = Path(folder) / 'long-432x2048.png'; make_jd(long, 2048)
        longer = Path(folder) / 'longer-432x4096.png'; make_jd(longer, 4096)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        records = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    for label, viewport, path in (
                        ('mobile-2048', {'width': 390, 'height': 844}, long),
                        ('desktop-4096', {'width': 1440, 'height': 900}, longer),
                        ('desktop-normal', {'width': 1440, 'height': 900}, normal)):
                        context = browser.new_context(viewport=viewport, is_mobile=label.startswith('mobile'))
                        page = context.new_page(); slices = []
                        page.on('requestfinished', lambda request: slices.append(request) if request.url.endswith('/api/ocr-slice') else None)
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        print(f'RUN {label}', flush=True)
                        started = time.perf_counter(); jd = add_image(page, path); elapsed = time.perf_counter() - started
                        raw = jd['rawJD']
                        assert jd['jobTitle'] == '高级产品经理', (jd['jobTitle'], raw)
                        assert '岗位职责' in raw and '任职要求' in raw
                        end = 5 if label == 'desktop-normal' else 18
                        assert raw.index('路线图第1项') < raw.index(f'路线图第{end}项') < raw.index('要求编号101') < raw.index(f'要求编号{100+end}')
                        if label == 'desktop-normal':
                            add_image(page, normal)
                            assert page.evaluate('state.jds.length') == 2
                        records.append((label, len(slices), elapsed, len(raw)))
                        context.close()

                    # Bounded failures of one slice must retry only that slice and never save a partial JD.
                    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
                    page = context.new_page(); calls = {'count': 0}
                    def fail_slice(route):
                        calls['count'] += 1
                        route.fulfill(status=500, content_type='application/json', body='{"error":"injected slice failure"}')
                    page.route('**/api/ocr-slice', fail_slice)
                    page.goto(f'http://127.0.0.1:{server.server_port}')
                    page.locator('#add').click(); page.locator('[data-mode="image"]').click()
                    page.locator('#jd-image').set_input_files(str(long)); page.get_by_text('1 张已就绪', exact=True).wait_for()
                    page.locator('#save-jd').click(); page.locator('.alert').first.wait_for()
                    assert 'JD 内容可能不完整' in page.locator('.alert').first.inner_text()
                    assert calls['count'] == 3 and page.evaluate('state.jds.length') == 0
                    records.append(('injected-failure', calls['count'], 0, 0)); context.close()

                    # A per-slice timeout is retried a bounded number of times and cannot create a partial JD.
                    context = browser.new_context(viewport={'width': 1440, 'height': 900})
                    page = context.new_page(); calls = {'count': 0}
                    def slow_slice(route):
                        calls['count'] += 1; time.sleep(.25)
                        route.fulfill(status=200, content_type='application/json', body='{"text":"late"}')
                    page.route('**/api/ocr-slice', slow_slice)
                    page.goto(f'http://127.0.0.1:{server.server_port}')
                    page.evaluate('JD_IMAGE.sliceTimeoutMs=100')
                    page.locator('#add').click(); page.locator('[data-mode="image"]').click()
                    page.locator('#jd-image').set_input_files(str(normal)); page.get_by_text('1 张已就绪', exact=True).wait_for()
                    page.locator('#save-jd').click(); page.locator('.alert').first.wait_for()
                    assert calls['count'] == 3 and page.evaluate('state.jds.length') == 0
                    records.append(('injected-timeout', calls['count'], 0, 0)); context.close()
                finally: browser.close()
        finally: server.shutdown(); server.server_close()
        for label, slices, elapsed, chars in records:
            print(f'PASS {label}: slices={slices} elapsed={elapsed:.2f}s raw_chars={chars}', flush=True)


if __name__ == '__main__': main()
