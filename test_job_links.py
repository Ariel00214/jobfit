import json
import socket
import subprocess
import unittest
from unittest.mock import patch, Mock

import job_links as links

DESCRIPTION = ('岗位职责：负责用户需求分析、产品原型设计，协调开发测试并推动产品上线。\n'
               '跟踪产品使用数据，结合用户反馈制定迭代方案，对产品使用效果负责。\n'
               '任职要求：具备产品设计经验，熟悉需求文档与跨团队协作，有数据分析经验。')


class LinkTests(unittest.TestCase):
    def test_listing_rejected_before_starting_worker(self):
        with patch('job_links.subprocess.Popen') as process:
            result = links.read_job('https://www.zhaopin.com/sou/jl653/kwtest')
        process.assert_not_called()
        self.assertTrue(result['needsSupplement'])
        self.assertIn('/sou/', result['sourceUrl'])

    def test_browser_skips_render_when_memory_is_low(self):
        from unittest.mock import mock_open
        with patch('builtins.open', mock_open()) as opened:
            opened.side_effect = [mock_open(read_data=str(512*1024*1024))(),
                                  mock_open(read_data=str(375*1024*1024))()]
            self.assertFalse(links.browser_memory_available())
        with patch('job_links.browser_memory_available', return_value=False):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                links.browser_html('https://m.liepin.com/job/123.shtml', 0)

    def test_mobile_share_and_markdown_preserve_query(self):
        url = 'https://m.zhipin.com/mpa/html/weijd/weijd-job/abc?sid=1&openWeapp=1'
        self.assertEqual(links.normalize_url('看看这个岗位：' + url + '。'), url)
        self.assertEqual(links.normalize_url('[岗位](' + url.replace('&', '\\&') + ')'), url)
        self.assertEqual(links.platform_for(url), 'BOSS直聘')
        self.assertEqual(links.platform_for('https://m.zhaopin.com/jobs/abc'), '智联招聘')
        self.assertEqual(links.platform_for('https://m.liepin.com/job/123.shtml'), '猎聘')
        self.assertEqual(links.platform_for('https://zhipin.com.attacker.example/a'), '招聘平台')

    def test_canonical_url_job_id_and_tracking_cleanup(self):
        raw = '岗位：https%3A%2F%2Fwww.zhipin.com%2Fjob_detail%2Fabc123.html%3Futm_source%3Dshare%26sid%3Dkeep。'
        url = links.normalize_url(raw)
        self.assertEqual(url, 'https://www.zhipin.com/job_detail/abc123.html?sid=keep')
        self.assertEqual(links.platform_code(url), 'boss')
        self.assertEqual(links.job_id_for(url), 'abc123')

    def test_normalized_result_preserves_raw_jd_and_provenance(self):
        content = '职位名称：AI产品经理\n公司名称：测试公司\n来源平台：BOSS直聘\n' + DESCRIPTION
        result = links.normalized_result('https://www.zhipin.com/job_detail/abc.html',
                                         'https://www.zhipin.com/job_detail/abc.html', content, 'http')
        self.assertEqual(result['platform'], 'boss')
        self.assertEqual(result['jobId'], 'abc')
        self.assertTrue(result['extraction']['identityVerified'])
        self.assertIn('任职要求', result['rawJD'])
        self.assertNotIn('来源平台：', result['rawJD'])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            links.normalized_result('https://www.zhipin.com/job_detail/abc.html',
                                    'https://www.zhipin.com/job_detail/other.html', content, 'http')

    def test_search_rejects_conflicting_job_id(self):
        response = Mock(status_code=200)
        response.json.return_value = {'web': {'results': [
            {'url': 'https://www.zhipin.com/job_detail/wrong.html'},
            {'url': 'https://www.zhipin.com/job_detail/abc.html'},
        ]}}
        with patch.dict(links.os.environ, {'BRAVE_SEARCH_API_KEY': 'secret'}), \
             patch.object(links, 'safe_url', side_effect=lambda value: value), \
             patch('requests.get', return_value=response):
            found = links.search_candidates('https://www.zhipin.com/job_detail/abc.html', links.time.monotonic()+5)
        self.assertEqual(found, ['https://www.zhipin.com/job_detail/abc.html'])

    def test_unsupported_platform_degrades_without_worker(self):
        with patch('job_links.subprocess.Popen') as process:
            result = links.read_job('https://jobs.example.com/job/123')
        process.assert_not_called()
        self.assertEqual(result['readStatus'], 'unsupported_platform')
        self.assertTrue(result['needsSupplement'])

    def test_invalid_or_multiple_urls(self):
        for value in ('没有链接', 'javascript:alert(1)', 'https://u:p@example.com/a'):
            self.assertEqual(links.read_job(value)['readStatus'], 'invalid_url')
        self.assertEqual(links.read_job('https://a.com/a https://b.com/b')['readStatus'], 'multiple_urls')

    def test_platform_ssr_fields_and_escaped_text(self):
        for host, data in (
            ('m.zhipin.com', {'jobName': 'AI产品经理', 'brandName': '测试公司', 'jobSecText': DESCRIPTION, 'encryptJobId': 'abc'}),
            ('m.zhaopin.com', {'jobTitle': 'AI产品经理', 'companyName': '测试公司', 'jobDescription': DESCRIPTION, 'positionId': 'abc'}),
            ('m.liepin.com', {'jobName': 'AI产品经理', 'companyName': '测试公司', 'jobDesc': DESCRIPTION, 'jobId': 'abc'}),
        ):
            source = '<script>window.__INITIAL_STATE__ = ' + json.dumps({'job': data}) + ';</script>'
            parsed = links.extract(source, 'https://' + host + '/job/abc')
            self.assertIn('职位名称：AI产品经理', parsed)
            self.assertIn('公司名称：测试公司', parsed)
            self.assertIn('任职要求', parsed)

    def test_schema_graph_and_focused_dom(self):
        schema = {'@graph': [{'@type': 'JobPosting', 'title': '产品经理',
                            'hiringOrganization': {'name': '测试公司'}, 'description': DESCRIPTION}]}
        self.assertIn('测试公司', links.extract('<script type="application/ld+json">' + json.dumps(schema) + '</script>', 'https://example.com/job/abc'))
        source = '<h1>产品经理</h1><a class="company-name">测试公司</a><div class="job-sec-text">' + DESCRIPTION.replace('\n', '<br>') + '</div><aside>推荐岗位：后端工程师</aside>'
        result = links.extract(source, 'https://www.zhipin.com/job_detail/abc.html')
        self.assertIn('测试公司', result)
        self.assertNotIn('后端工程师', result)

    def test_recommended_job_mismatch_and_ambiguity_rejected(self):
        records = [{'jobName': '后端工程师', 'jobDescription': DESCRIPTION, 'jobId': 'wrong'}]
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            links.extract('<script>' + json.dumps(records) + '</script>', 'https://www.zhipin.com/job_detail/abc.html')
        records.append({'jobName': '运营专员', 'jobDescription': DESCRIPTION})
        records[0].pop('jobId')
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            links.extract('<script>' + json.dumps(records) + '</script>', 'https://example.com/job/abc')

    def test_verification_expired_and_listing_not_scored(self):
        for page, reason in (('<h1>安全验证</h1>', 'blocked'), ('职位已下架', 'expired'),
                             ('<h1>产品经理招聘列表</h1>' + DESCRIPTION, 'unavailable')):
            with self.assertRaisesRegex(ValueError, reason):
                links.extract(page, 'https://example.com/jobs')
        data = {'jobName': '产品经理', 'jobDescription': DESCRIPTION}
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            links.extract('<script>'+json.dumps(data)+'</script>', 'https://www.zhaopin.com/sou/jl653/kw123')

    def test_private_addresses_and_redirect_checked(self):
        with patch.object(socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaisesRegex(ValueError, 'invalid_url'): links.safe_url('https://example.com/a')
        response = Mock(); response.is_redirect = True; response.headers = {'Location': 'http://127.0.0.1/private'}
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        with patch.object(links, 'safe_url', side_effect=lambda u: u if 'example.com' in u else (_ for _ in ()).throw(ValueError('invalid_url'))), patch('requests.get', return_value=response):
            with self.assertRaisesRegex(ValueError, 'invalid_url'): links.fetch_html('https://example.com/a', links.time.monotonic()+10)

    def test_busy_and_timeout_retain_source(self):
        url = 'https://m.zhipin.com/job/abc'
        links._SLOT.acquire()
        try: self.assertEqual(links.read_job(url)['readStatus'], 'busy')
        finally: links._SLOT.release()
        proc = Mock(); proc.pid = 999999; proc.communicate.side_effect = [subprocess.TimeoutExpired('test', 24), ('', '')]
        with patch.object(links.subprocess, 'Popen', return_value=proc), patch('os.killpg', create=True):
            result = links.read_job(url)
        self.assertEqual(result['readStatus'], 'timeout')
        self.assertEqual(result['sourceUrl'], url)
        self.assertEqual(result['sourcePlatform'], 'BOSS直聘')
        self.assertTrue(result['needsSupplement'])

    def test_worker_failure_retains_platform_and_job_identity(self):
        url = 'https://www.zhaopin.com/jobdetail/CCL1501502560J40886420814.htm'
        proc = Mock(); proc.pid = 999999
        proc.communicate.return_value = (json.dumps(links.failure('unavailable')), '')
        with patch.object(links.subprocess, 'Popen', return_value=proc), patch('os.killpg', create=True):
            result = links.read_job(url)
        self.assertEqual(result['sourceUrl'], url)
        self.assertEqual(result['platform'], 'zhaopin')
        self.assertEqual(result['jobId'], 'CCL1501502560J40886420814')
        self.assertEqual(result['extraction']['sourceUrls'], [url])


if __name__ == '__main__': unittest.main()
