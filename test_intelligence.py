import os,sys,unittest
sys.path.insert(0,os.path.dirname(__file__))
from intelligence import parse_resume,parse_jd,analyze,action_plan
from server import extract_job_payload,full_analysis
from engine import parse_jd as parse_legacy_jd

RESUME='''张三 产品运营 2021.01-2024.01 某科技公司
负责内容策略，根据后台数据调整内容方向，转化率提升20%。
协调主播、剪辑和运营跨团队排期推进，协助项目按期上线。
参与用户访谈并整理反馈，使用 Excel 完成数据复盘。 本科学历。'''
JDS=[
'''职位名称：AI 产品运营\n核心职责：负责 AI 功能运营和用户增长，根据数据持续优化。要求跨团队推进产品上线。加分：熟悉 SQL。''',
'''职位名称：内容运营\n负责内容策略、账号运营和数据复盘。要求有短视频内容经验，能够提升转化率。''',
'''职位名称：AI 产品经理\n主导用户研究、需求分析、PRD 和 AI 产品从0到1上线。要求独立负责产品迭代。加分：内容经验。''',
'''职位名称：后端开发工程师\n核心职责：负责 Java 后端、数据库与 API 开发。要求独立完成系统设计和测试。加分：沟通能力。''',
'''职位名称：项目经理\n负责跨团队排期、项目推进和交付，管理里程碑。要求独立负责复杂项目。''']

class JobFitTests(unittest.TestCase):
 def setUp(self):self.jds=[parse_jd(x) for x in JDS]
 def test_m1_hidden_and_ownership(self):
  p=parse_resume(RESUME);self.assertIn('项目推进',p['hiddenCapabilities']+p['explicitSkills']);self.assertTrue(any(x['ownership']=='assist' for x in p['evidence']));self.assertEqual(p['totalWorkYears'],3)
 def test_m2_without_jds(self):
  r=analyze(RESUME,[self.jds[1]]);self.assertGreaterEqual(len(r['careerDirections']['close']),2);self.assertIn('comparison',r['careerDirections'])
 def test_m3_scores_spread_and_core_cap(self):
  r=analyze(RESUME,self.jds);scores=[j['matchScore'] for g in r['families'] for j in g['jobs']];self.assertGreater(max(scores)-min(scores),20)
  dev=next(j for g in r['families'] for j in g['jobs'] if '后端' in j['jobTitle']);self.assertLessEqual(dev['matchScore'],39)
 def test_synonym_evidence(self):
  jd=parse_jd('职位名称：产品运营\n负责用业务数据驱动策略决策，要求分析指标并优化转化。');r=analyze(RESUME,[jd]);items=r['families'][0]['jobs'][0]['requirementAlignment']['core'];self.assertTrue(any(x['status']!='none' for x in items))
 def test_comparison_and_gaps(self):
  r=analyze(RESUME,self.jds);self.assertTrue(r['comparison']);self.assertLessEqual(len(r['gaps']['key']),3);self.assertLessEqual(len(r['gaps']['ignore']),2)
 def test_plans_are_depth_based(self):
  gaps={'key':[{'capability':'产品落地'}]};p3=action_plan(gaps,3);p7=action_plan(gaps,7);p30=action_plan(gaps,30);self.assertNotEqual(p3['depth'],p7['depth']);self.assertNotEqual(p7['depth'],p30['depth']);self.assertIn('真实试用',p30['depth'])
 def test_supplement_recomputes_without_master_change(self):
  before=analyze(RESUME,[self.jds[2]]);supp=[{'rawText':'独立负责一个 AI 助手需求分析和原型，组织测试并完成上线。','relatedCapability':'产品需求分析','ownership':'own','reusable':True}];after=analyze(RESUME,[self.jds[2]],supp)
  self.assertGreater(after['families'][0]['jobs'][0]['matchScore'],before['families'][0]['jobs'][0]['matchScore']);self.assertEqual(after['profile']['resumeFactRegistry'],parse_resume(RESUME)['resumeFactRegistry'])
  visible=full_analysis(RESUME,[parse_legacy_jd(JDS[2])],supp);visible_job=visible['families'][0]['jobs'][0];self.assertEqual(visible_job['matchScore'],visible_job['evidenceMatch']['matchScore'])
 def test_link_payload_and_ocr_identity(self):
  html='''<title>AI产品经理招聘_星河科技</title><script>{"jobName":"AI产品经理","companyName":"星河科技有限公司","jobDescription":"负责用户研究、需求分析与产品上线，要求三年以上产品经验"}</script>'''
  payload=extract_job_payload(html);self.assertIn('AI产品经理',payload);self.assertIn('星河科技有限公司',payload)
  text='''【截图 1】\n星河科技有限公司\nAI产品经理\n负责用户研究、需求分析与产品上线\n任职要求：三年以上产品经验'''
  current=parse_jd(text,'image');legacy=parse_legacy_jd(text,'image');self.assertEqual(current['jobTitle'],'AI产品经理');self.assertEqual(current['company'],'星河科技有限公司');self.assertEqual(legacy['jobTitle'],'AI产品经理');self.assertEqual(legacy['company'],'星河科技有限公司')
 def test_ambiguous_identity_keeps_fallback(self):
  text='''招聘信息\n负责产品需求分析和运营工作\n待遇从优\n期待你的加入''';current=parse_jd(text,'image');legacy=parse_legacy_jd(text,'image');self.assertEqual(current['jobTitle'],'未命名岗位');self.assertEqual(current['company'],'');self.assertEqual(legacy['jobTitle'],'未命名岗位');self.assertEqual(legacy['company'],'')

if __name__=='__main__':unittest.main()
