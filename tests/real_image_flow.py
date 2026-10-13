"""Run the real two-screenshot JD flow against local RapidOCR.

Usage: python tests/real_image_flow.py first.png second.png
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from server import Handler, ThreadingHTTPServer


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: real_image_flow.py first.png second.png')
    paths = [str(Path(value).resolve()) for value in sys.argv[1:]]
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
                requests = []
                page.on('requestfinished', lambda request: requests.append(request) if request.url.endswith('/api/ocr-slice') else None)
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#add').click(); page.locator('[data-mode="image"]').click()
                started = time.perf_counter(); page.locator('#jd-image').set_input_files(paths)
                page.get_by_text('2 张已就绪', exact=True).wait_for()
                layout = page.evaluate('state.jdImages.map(x=>({imageIndex:x.imageIndex,totalParts:x.totalParts,width:x.width,height:x.height,isLong:x.isLong}))')
                page.locator('#save-jd').click(); page.locator('.overlay').wait_for(state='detached', timeout=240000)
                jd = page.evaluate('state.jds[0]'); raw = jd['rawJD']
                required = ['AI品牌及产品运营', '15-25K', '岗位职责', '任职要求', '2-3年', '团队协作', '新技术']
                missing = [value for value in required if value not in raw]
                assert len(layout) == 2 and all(item['totalParts'] == 1 for item in layout), layout
                assert not missing, {'missing': missing, 'raw': raw}
                assert page.evaluate('state.jds.length') == 1
                print({'layout': layout, 'requests': len(requests), 'seconds': round(time.perf_counter()-started, 2),
                       'title': jd['jobTitle'], 'company': jd['company'], 'salary': jd['salary'],
                       'rawChars': len(raw), 'missing': missing})
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
