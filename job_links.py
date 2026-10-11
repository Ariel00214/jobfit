"""Bounded public-job reading. Never logs in or treats a listing as a JD."""
import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

PLATFORMS = {'zhipin.com': 'BOSS直聘', 'zhaopin.com': '智联招聘',
             'liepin.com': '猎聘', '51job.com': '前程无忧',
             'lagou.com': '拉勾', 'kanzhun.com': '看准'}
LIMIT = 24
_SLOT = threading.BoundedSemaphore(1)
BLOCKED = re.compile(r'安全验证|访问验证|滑动验证|验证码|请登录后|security verification|captcha', re.I)
EXPIRED = re.compile(r'职位已(?:关闭|下架|失效)|岗位已(?:关闭|下架|失效)|该职位不存在|职位不存在|job expired', re.I)
TERMS = re.compile(r'职位(?:描述|介绍|要求)|岗位(?:职责|要求)|任职要求|工作职责|responsibilit|requirement', re.I)
MESSAGES = {
    'blocked': '平台需要登录或验证，请上传岗位截图或粘贴正文。',
    'expired': '岗位可能已下架，请上传保存的截图或粘贴正文。',
    'timeout': '链接读取超时，请上传岗位截图或粘贴正文。',
    'busy': '当前链接读取较忙，请稍后重试或上传截图。',
    'unavailable': '暂未读取到完整岗位，请上传截图或粘贴正文。',
    'invalid_url': '请粘贴一个有效的 http/https 岗位链接。',
    'multiple_urls': '检测到多个链接，请每次添加一个岗位。',
}


def platform_for(url):
    host = (urlparse(url).hostname or '').lower()
    return next((name for d, name in PLATFORMS.items()
                 if host == d or host.endswith('.' + d)), '招聘平台' if url else '')


def normalize_url(value):
    value = html.unescape(str(value or '').replace('\\&', '&')).strip()
    urls = list(dict.fromkeys(re.findall(r'https?://[^\s<>"\u3000]+', value, re.I)))
    urls = [u.rstrip('。，；、！？）】」』)>]') for u in urls]
    if len(urls) > 1:
        raise ValueError('multiple_urls')
    if not urls:
        raise ValueError('invalid_url')
    url = urls[0]
    p = urlparse(url)
    if p.scheme.lower() not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('invalid_url')
    if len(url) > 4096:
        raise ValueError('invalid_url')
    return url


def safe_url(url):
    p = urlparse(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('invalid_url')
    if any(not ipaddress.ip_address(a[4][0]).is_global
           for a in socket.getaddrinfo(p.hostname, None, type=socket.SOCK_STREAM)):
        raise ValueError('invalid_url')
    return url


def clean(value):
    value = html.unescape(re.sub(r'<[^>]+>', '\n', str(value or '')))
    return re.sub(r'\n\s*\n+', '\n', value).strip()


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []; self.h1 = []; self.visible = []; self.descriptions = []
        self.companies = []
        self.stack = []; self.scripts = []; self.script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '') + ' ' + attrs.get('id', '')
        focused = bool(re.search(r'(?:job-sec-text|job-detail|job-description|job-desc|job-intro|job_duty|describ|job-responsibilit)', classes, re.I))
        if focused: self.descriptions.append([])
        if tag not in ('br', 'img', 'meta', 'link', 'hr', 'input', 'source', 'wbr'):
            company = bool(re.search(r'(?:company-name|companyName|company-title|company-title-info)', classes))
            self.stack.append((tag, len(self.descriptions) - 1 if focused else None, company))
        if tag == 'script': self.script = []

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script)); self.script = None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack = self.stack[:i]; break

    def handle_data(self, data):
        tags = [t for t, _, _ in self.stack]
        if self.script is not None: self.script.append(data); return
        if 'style' in tags: return
        if 'title' in tags: self.title.append(data); return
        if 'h1' in tags: self.h1.append(data)
        self.visible.append(data)
        if any(c for _, _, c in self.stack): self.companies.append(data)
        for _, index, _ in self.stack:
            if index is not None: self.descriptions[index].append(data)


def objects(value, depth=0):
    if depth > 18: return
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from objects(child, depth+1)
    elif isinstance(value, list):
        for child in value[:200]: yield from objects(child, depth+1)


def json_blobs(script):
    # Decode whole JSON scripts and assigned SSR objects with the JSON decoder.
    decoder = json.JSONDecoder()
    script = script.strip()
    try:
        yield json.loads(script); return
    except (ValueError, TypeError): pass
    for match in list(re.finditer(r'(?:window\.[\w.$]+|(?:var|let|const)\s+\w+)\s*=\s*', script))[:20]:
        try: yield decoder.raw_decode(script[match.end():].lstrip())[0]
        except ValueError: pass


def first(obj, keys):
    return next((obj[k] for k in keys if isinstance(obj.get(k), (str, int)) and obj[k]), '')


def extract(source, url):
    page = Page(); page.feed(source)
    visible = '\n'.join(page.visible)
    if EXPIRED.search(visible): raise ValueError('expired')
    candidates = []
    for script in page.scripts:
        for blob in json_blobs(script):
            for obj in objects(blob):
                types = obj.get('@type', '')
                schema = 'JobPosting' in (types if isinstance(types, list) else [types])
                desc = first(obj, ('jobDescription', 'postDescription', 'positionDescription', 'jobSecText', 'jobDesc', 'jobDuty', 'description'))
                name = first(obj, ('jobName', 'jobTitle', 'positionName', 'positionTitle', 'postName')) or (obj.get('title', '') if schema else '')
                if not desc or not name: continue
                org = obj.get('hiringOrganization', {})
                company = org.get('name', '') if schema and isinstance(org, dict) else first(obj, ('companyName', 'brandName', 'companyShortName', 'corpName'))
                location = first(obj, ('cityName', 'workCity', 'jobArea', 'areaName'))
                identity = first(obj, ('encryptJobId', 'jobId', 'positionId', 'id'))
                linked = obj.get('url', '') if schema else ''
                if identity and str(identity) not in url and not schema: continue
                if linked and urlparse(str(linked)).path.rstrip('/') != urlparse(url).path.rstrip('/'): continue
                desc = clean(desc)
                if len(re.sub(r'\s', '', desc)) < 80: continue
                candidates.append((str(name), str(company), str(location), desc))
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) > 1: raise ValueError('unavailable')
    if candidates:
        name, company, location, desc = candidates[0]
    else:
        if BLOCKED.search(visible): raise ValueError('blocked')
        # Only a focused description paired with the detail-page heading is accepted.
        descriptions = list(dict.fromkeys(clean('\n'.join(d)) for d in page.descriptions
                                         if len(clean('\n'.join(d))) >= 100 and TERMS.search('\n'.join(d))))
        name = ''.join(page.h1).strip()
        if len(descriptions) != 1 or not 2 <= len(name) <= 70: raise ValueError('unavailable')
        desc = descriptions[0]; company = ''.join(page.companies).strip(); location = ''
        if len(company) > 100: raise ValueError('unavailable')
    if BLOCKED.search(desc): raise ValueError('blocked')
    return '\n'.join(x for x in [f'职位名称：{name}', f'公司名称：{company}' if company else '',
                                f'工作地点：{location}' if location else '',
                                f'来源平台：{platform_for(url)}', desc] if x)


def fetch_html(url, deadline):
    import requests
    headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36',
               'Accept-Language': 'zh-CN,zh;q=0.9', 'Accept': 'text/html,application/xhtml+xml'}
    current = safe_url(url)
    for _ in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise ValueError('timeout')
        with requests.get(current, headers=headers, timeout=(min(3, remaining), min(6, remaining)),
                          allow_redirects=False, stream=True) as response:
            if response.is_redirect or response.is_permanent_redirect:
                current = safe_url(urljoin(current, response.headers.get('Location', ''))); continue
            if response.status_code in (401, 403, 429): raise ValueError('blocked')
            if response.status_code in (404, 410): raise ValueError('expired')
            if response.status_code != 200: raise ValueError('unavailable')
            if 'html' not in response.headers.get('Content-Type', ''): raise ValueError('unavailable')
            raw = response.raw.read(2*1024*1024+1, decode_content=True)
            if len(raw) > 2*1024*1024: raise ValueError('unavailable')
            encoding = response.encoding if response.encoding and response.encoding.lower() != 'iso-8859-1' else 'utf-8'
            return raw.decode(encoding, errors='replace'), current
    raise ValueError('unavailable')


def browser_html(url, deadline):
    from playwright.sync_api import sync_playwright
    bundled = os.path.join(os.path.dirname(__file__), '.playwright')
    if os.path.isdir(bundled): os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', bundled)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, timeout=max(1, int((deadline-time.monotonic())*1000)))
        try:
            context = browser.new_context(locale='zh-CN', viewport={'width': 390, 'height': 844}, is_mobile=True,
                                          user_agent='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36')
            def route_request(route):
                try:
                    if route.request.resource_type in ('image', 'media', 'font'): return route.abort()
                    safe_url(route.request.url); route.continue_()
                except Exception: route.abort()
            context.route('**/*', route_request)
            page = context.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=max(1, min(10000, int((deadline-time.monotonic())*1000))))
            last = 'unavailable'
            while time.monotonic() < deadline:
                safe_url(page.url)
                try: return extract(page.content(), page.url), page.url
                except ValueError as exc:
                    last = str(exc)
                    if last in ('blocked', 'expired'): raise
                page.wait_for_timeout(300)
            raise ValueError(last)
        finally: browser.close()


def worker(url):
    deadline = time.monotonic() + LIMIT - 2
    reasons = []
    try:
        source, resolved = fetch_html(url, deadline)
        return {'content': extract(source, resolved), 'resolvedUrl': resolved, 'method': 'html'}
    except Exception as exc: reasons.append(str(exc))
    if 'expired' in reasons: raise ValueError('expired')
    # A public render uses no user account, cookies, or credentials.
    try:
        content, resolved = browser_html(url, deadline - 5)
        return {'content': content, 'resolvedUrl': resolved, 'method': 'browser'}
    except Exception as exc: reasons.append(str(exc))
    # Preserve the existing public URL reader, with the same strict extraction.
    # Only the public job URL goes to this service, never a resume or credentials.
    host = (urlparse(url).hostname or '').lower()
    if any(host == d or host.endswith('.'+d) for d in PLATFORMS):
        try:
            import requests
            safe_url(url)
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise ValueError('timeout')
            with requests.get('https://r.jina.ai/'+url, headers={'X-Return-Format': 'html'},
                              timeout=(min(2, remaining), min(4, remaining)), stream=True) as response:
                if response.status_code != 200: raise ValueError('unavailable')
                raw = response.raw.read(2*1024*1024+1, decode_content=True)
                if len(raw) > 2*1024*1024: raise ValueError('unavailable')
                return {'content': extract(raw.decode('utf-8', errors='replace'), url),
                        'resolvedUrl': url, 'method': 'reader'}
        except Exception as exc: reasons.append(str(exc))
    raise ValueError('blocked' if 'blocked' in reasons else 'timeout' if time.monotonic() >= deadline else 'unavailable')


def read_job(value):
    try: url = normalize_url(value)
    except ValueError as exc: return failure(str(exc))
    if not _SLOT.acquire(blocking=False): return failure('busy', url)
    try:
        # Isolate DNS, network and rendering together so a slow stage cannot exceed the total budget.
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--read'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, start_new_session=True)
        try:
            output, _ = proc.communicate(json.dumps(url), timeout=LIMIT)
            result = json.loads(output)
        except subprocess.TimeoutExpired:
            import signal
            if os.name == 'posix': os.killpg(proc.pid, signal.SIGKILL)
            else: proc.kill()
            proc.communicate()
            return failure('timeout', url)
        except Exception: return failure('unavailable', url)
        finally:
            # Also clean up any browser children on a worker error.
            if os.name == 'posix':
                import signal
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            elif proc.poll() is None: proc.kill()
            proc.wait()
        return {**result, 'sourceUrl': url, 'sourcePlatform': platform_for(url)}
    finally: _SLOT.release()


def failure(reason, url=''):
    reason = reason if reason in MESSAGES else 'unavailable'
    return {'needsSupplement': True, 'readStatus': reason, 'sourceUrl': url,
            'sourcePlatform': platform_for(url), 'message': MESSAGES[reason]}


if __name__ == '__main__':
    try: result = {**worker(json.loads(sys.stdin.read())), 'readStatus': 'success'}
    except Exception as exc: result = failure(str(exc))
    print(json.dumps(result, ensure_ascii=False))
