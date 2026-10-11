"""Mobile browser regression using explicit synthetic platform pages + real OCR.

No fixture is presented as a real recruitment-platform success.
Run: python tests/mobile_flow.py (Chromium must be installed).
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from server import Handler, ThreadingHTTPServer
from job_links import extract, failure, normalize_url, platform_for
from test_job_links import DESCRIPTION

RESUME = ('张三 产品运营 本科 2021.01-2024.01 某科技公司\n'
          '负责内容策略和产品需求分析，根据后台数据调整内容方向，转化率提升20%。\n'
          '协调开发、测试和运营跨团队排期推进，负责项目按期上线。\n'
          '参与用户访谈并整理反馈，使用 Excel 完成数据复盘。')


def fixture_reader(value):
    try: url = normalize_url(value)
    except ValueError as exc: return failure(str(exc))
    if '/blocked' in url: return failure('blocked', url)
    if '/slow' in url:
        import time
        time.sleep(.5)
    data = {'jobName': 'AI产品经理', 'companyName': '测试公司', 'jobDescription': DESCRIPTION}
    source = '<script>' + json.dumps(data, ensure_ascii=False) + '</script>'
    return {'content': extract(source, url), 'readStatus': 'success', 'method': 'fixture',
            'sourceUrl': url, 'sourcePlatform': platform_for(url)}


def main():
    os.makedirs('work', exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        resume = Path(folder)/'resume.txt'; resume.write_text(RESUME)
        image = Image.new('RGB', (1000, 600), 'white'); draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('DejaVuSans.ttf', 30)
        for i, line in enumerate(['AI Product Manager', 'Company: Example Technology',
                                  'Responsibilities: product design and user research.',
                                  'Manage requirements and coordinate development.',
                                  'Requirements: product experience and data analysis.',
                                  'Work with engineering teams and test new features.']):
            draw.text((30, 30+i*70), line, fill='black', font=font)
        screenshot = Path(folder)/'job.png'; image.save(screenshot)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch('server.read_job', side_effect=fixture_reader), sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    for width in (375, 390, 430):
                        context = browser.new_context(viewport={'width': width, 'height': 844}, is_mobile=True, has_touch=True)
                        page = context.new_page(); errors = []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('#resume').set_input_files(str(resume))
                        page.get_by_text('当前使用中', exact=False).wait_for()
                        for host in ('m.zhipin.com', 'm.zhaopin.com', 'm.liepin.com'):
                            page.locator('#add').click(); page.locator('[data-mode="url"]').click()
                            page.locator('#jd-url').fill('推荐岗位：https://'+host+'/job/fixture?share=1')
                            page.locator('#save-jd').click()
                            page.locator('.overlay').wait_for(state='detached')
                        assert page.locator('.compact-job').count() == 3
                        # The failed URL survives text fallback and later source display.
                        page.locator('#add').click(); page.locator('[data-mode="url"]').click()
                        page.locator('#jd-url').fill('https://m.zhipin.com/job/blocked?sid=text')
                        page.locator('#save-jd').click()
                        page.get_by_text('已保留原岗位链接', exact=False).wait_for()
                        assert page.locator('#jd-image').count() == 1
                        page.locator('[data-mode="text"]').click()
                        page.locator('#jd-text').fill('职位名称：产品运营\n'+DESCRIPTION)
                        page.locator('[data-mode="url"]').click()
                        assert 'sid=text' in page.locator('#jd-url').input_value()
                        page.locator('[data-mode="text"]').click()
                        assert '产品运营' in page.locator('#jd-text').input_value()
                        page.locator('#save-jd').click(); page.locator('.overlay').wait_for(state='detached')
                        # Exercise the existing browser compression + actual server OCR.
                        page.locator('#add').click(); page.locator('[data-mode="url"]').click()
                        page.locator('#jd-url').fill('https://m.liepin.com/job/blocked?sid=image')
                        page.locator('#save-jd').click()
                        page.get_by_text('已保留原岗位链接', exact=False).wait_for()
                        page.locator('#jd-image').set_input_files(str(screenshot))
                        page.get_by_text('1 张已就绪', exact=True).wait_for()
                        page.locator('#save-jd').click(); page.locator('.overlay').wait_for(state='detached', timeout=120000)
                        assert page.locator('.compact-job').count() == 5
                        # Cancel must preserve draft and reject the late response.
                        page.locator('#add').click(); page.locator('[data-mode="url"]').click()
                        page.locator('#jd-url').fill('https://m.zhipin.com/job/slow')
                        page.locator('#save-jd').click(); page.locator('#cancel-jd').click()
                        page.wait_for_timeout(800)
                        assert page.locator('.compact-job').count() == 5
                        assert 'slow' in page.locator('#jd-url').input_value()
                        page.locator('#close').click()
                        page.locator('#analyze').click(); page.locator('.job-row').first.wait_for(timeout=30000)
                        assert page.locator('.job-row').count() == 5
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        # Inspect every source; screenshot fallback exposes both link and image.
                        found_image = found_text = False
                        for i in range(5):
                            page.locator('.job-row').nth(i).click()
                            anchor = page.locator('a.source-action')
                            if 'sid=image' in anchor.get_attribute('href'):
                                found_image = True
                                page.locator('#view-source').click()
                                assert page.locator('.source-img').count() == 1
                                page.locator('#close').click()
                            if 'sid=text' in anchor.get_attribute('href'):
                                found_text = True
                                page.locator('#view-source').click()
                                assert '岗位职责' in page.locator('.raw').inner_text()
                                page.locator('#close').click()
                            page.locator('[data-page="results"]').click()
                        assert found_image and found_text
                        assert not errors, errors
                        page.screenshot(path=f'work/mobile-{width}.png', full_page=True)
                        context.close()
                        print(f'PASS {width}px: resume, 3 platform fixtures, text/image fallback, real OCR, cancel, match, sources')
                finally: browser.close()
        finally: server.shutdown(); server.server_close()


if __name__ == '__main__': main()
