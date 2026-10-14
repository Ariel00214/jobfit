import os,sys,unittest,io,base64
from unittest.mock import patch
sys.path.insert(0,os.path.dirname(__file__))
from intelligence import parse_resume,parse_jd,analyze,action_plan
from server import full_analysis,image_mime,optimize_ocr_image,ocr_tiles,vision,recognize_slice,combine_ocr_parts,merge_adjacent_ocr,ocr_text_status,image_is_visually_blank,ocr_capacity
from ocr_worker import lines as ocr_lines
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
 def test_ocr_identity(self):
  text='''【截图 1】\n星河科技有限公司\nAI产品经理\n负责用户研究、需求分析与产品上线\n任职要求：三年以上产品经验'''
  current=parse_jd(text,'image');legacy=parse_legacy_jd(text,'image');self.assertEqual(current['jobTitle'],'AI产品经理');self.assertEqual(current['company'],'星河科技有限公司');self.assertEqual(legacy['jobTitle'],'AI产品经理');self.assertEqual(legacy['company'],'星河科技有限公司')
 def test_screenshot_company_and_unlabelled_role(self):
  text='''【截图 1】\n01Oct.2026\n浙江连信科技有限公司正在招聘\n内容增长（AI内容方向)\n杭州/12-20K/3-5年/本科\n职位详情\n负责内容策略与社媒运营。\n任职要求：熟悉小红书及抖音。'''
  parsed=parse_legacy_jd(text,'image')
  self.assertEqual(parsed['jobTitle'],'内容增长（AI内容方向)')
  self.assertEqual(parsed['company'],'浙江连信科技有限公司')
 def test_ambiguous_identity_keeps_fallback(self):
  text='''招聘信息\n负责产品需求分析和运营工作\n待遇从优\n期待你的加入''';current=parse_jd(text,'image');legacy=parse_legacy_jd(text,'image');self.assertEqual(current['jobTitle'],'未命名岗位');self.assertEqual(current['company'],'');self.assertEqual(legacy['jobTitle'],'未命名岗位');self.assertEqual(legacy['company'],'')
 def test_mobile_image_mime_fallback(self):
  self.assertEqual(image_mime({'name':'岗位截图.JPG','mime':''}),'image/jpeg')
  self.assertEqual(image_mime({'name':'岗位截图.jpg','mime':'image/jpg'}),'image/jpeg')
  self.assertEqual(image_mime({'name':'岗位截图.PNG'}),'image/png')
  self.assertEqual(image_mime({'name':'岗位截图.HEIC'}),'')
 def test_ocr_image_preserves_text_resolution(self):
  from PIL import Image
  source=io.BytesIO();Image.new('RGB',(2000,3000),'white').save(source,'PNG')
  optimized=optimize_ocr_image(source.getvalue())
  self.assertEqual(optimized.shape[:2],(3000,2000))
  wide=io.BytesIO();Image.new('RGB',(3000,4500),'white').save(wide,'JPEG')
  bounded=optimize_ocr_image(wide.getvalue())
  self.assertEqual(bounded.shape[:2],(3000,2000))
 def test_long_screenshot_ocr_uses_bounded_tiles(self):
  from PIL import Image
  source=io.BytesIO();Image.new('RGB',(1134,5367),'white').save(source,'JPEG')
  shapes=[tile.shape[:2] for tile in ocr_tiles(source.getvalue())]
  self.assertGreaterEqual(len(shapes),6)
  self.assertTrue(all(height<=900 and width<=1200 for height,width in shapes))
  def fake_ocr(image):
   self_shapes.append(image.shape[:2])
   return '招聘岗位：内容增长，负责制定内容策略、运营渠道、分析用户增长数据并持续优化转化。'
  self_shapes=[]
  with patch('server.isolated_ocr_tile',side_effect=fake_ocr):
   content=vision([{'name':'long.jpg','mime':'image/jpeg','data':base64.b64encode(source.getvalue()).decode()}])
  self.assertIn('内容增长',content)
  self.assertEqual(self_shapes,shapes)
 def test_sequential_slice_ocr_combines_into_one_job(self):
  from PIL import Image
  source=io.BytesIO();Image.new('RGB',(1000,800),'white').save(source,'JPEG')
  with patch('server.isolated_ocr_tile',return_value='浙江连信科技有限公司正在招聘\n内容增长（AI内容方向)\n负责内容策略与用户增长。'):
   first=recognize_slice({'name':'part1.jpg','mime':'image/jpeg','data':base64.b64encode(source.getvalue()).decode()})['text']
  combined=combine_ocr_parts([{'imageIndex':0,'partIndex':0,'totalParts':2,'text':first},{'imageIndex':0,'partIndex':1,'totalParts':2,'text':'任职要求：熟悉内容运营和数据分析。'}])
  parsed=parse_legacy_jd(combined,'image')
  self.assertEqual(parsed['jobTitle'],'内容增长（AI内容方向)')
  self.assertEqual(parsed['company'],'浙江连信科技有限公司')
  self.assertIn('任职要求',combined)
 def test_slice_overlap_dedup_is_boundary_only(self):
  previous='负责 AI 产品设计\n参与需求分析\n完成产品上线'
  current='参与需求分析\n完成产品上线\n负责数据复盘'
  merged=merge_adjacent_ocr(previous,current)
  self.assertEqual(merged.count('参与需求分析'),1)
  self.assertEqual(merged.count('完成产品上线'),1)
  self.assertTrue(merged.endswith('负责数据复盘'))
  self.assertEqual(merge_adjacent_ocr('沟通能力\n其他内容','沟通能力\n团队合作').count('沟通能力'),2)
 def test_incomplete_slice_set_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'内容不完整'):
   combine_ocr_parts([{'imageIndex':0,'partIndex':0,'totalParts':2,'text':'岗位名称：产品经理\n岗位职责：负责产品规划与交付。'}])
  with self.assertRaisesRegex(ValueError,'内容不完整'):
   combine_ocr_parts([{'imageIndex':0,'partIndex':0,'totalParts':1,'text':''}])
 def test_duplicate_and_non_contiguous_slice_indexes_are_rejected(self):
  duplicate=[{'imageIndex':0,'partIndex':0,'totalParts':1,'text':'岗位名称：产品经理\n岗位职责：负责产品规划与交付。'}]*2
  with self.assertRaisesRegex(ValueError,'索引重复'):combine_ocr_parts(duplicate)
  with self.assertRaisesRegex(ValueError,'索引不连续'):
   combine_ocr_parts([{'imageIndex':1,'partIndex':0,'totalParts':1,'text':'岗位名称：产品经理\n岗位职责：负责产品规划与交付。'}])
 def test_slice_identity_and_coverage_are_verified(self):
  base={'imageIndex':0,'totalParts':2,'taskId':'task-a','fingerprint':'sha-a','scaledHeight':2200}
  valid=[{**base,'partIndex':0,'coverageTop':0,'coverageBottom':1200,'text':'岗位名称：产品经理\n岗位职责：负责产品规划与交付。'},
         {**base,'partIndex':1,'coverageTop':1104,'coverageBottom':2200,'text':'任职要求：具备数据分析能力。'}]
  self.assertIn('任职要求',combine_ocr_parts(valid))
  with self.assertRaisesRegex(ValueError,'身份不一致'):
   combine_ocr_parts([valid[0],{**valid[1],'fingerprint':'sha-other'}])
  with self.assertRaisesRegex(ValueError,'未覆盖'):
   combine_ocr_parts([valid[0],{**valid[1],'coverageTop':1300}])
 def test_ocr_status_distinguishes_failure_review_and_complete(self):
  self.assertEqual(ocr_text_status('')[0],'failed')
  self.assertEqual(ocr_text_status('薪资 20K')[0],'needs_review')
  self.assertEqual(ocr_text_status('岗位职责：负责产品规划。任职要求：具备数据分析能力。')[0],'complete')
 def test_enhancement_is_opt_in(self):
  from PIL import Image
  source=io.BytesIO();Image.new('RGB',(400,300),(210,210,210)).save(source,'PNG')
  normal=optimize_ocr_image(source.getvalue());enhanced=optimize_ocr_image(source.getvalue(),True)
  self.assertEqual(normal.shape,(300,400,3));self.assertGreater(enhanced.shape[1],normal.shape[1])
 def test_blank_slice_is_distinguished_from_missed_text(self):
  from PIL import Image
  blank=io.BytesIO();Image.new('RGB',(400,300),'white').save(blank,'PNG')
  prepared=optimize_ocr_image(blank.getvalue());self.assertTrue(image_is_visually_blank(prepared))
  parts=[{'imageIndex':0,'partIndex':0,'totalParts':2,'status':'complete','text':'岗位名称：产品经理\n岗位职责：负责产品规划、用户研究与项目交付。\n任职要求：具备数据分析和沟通能力。'},
         {'imageIndex':0,'partIndex':1,'totalParts':2,'status':'blank','text':''}]
  self.assertIn('岗位职责',combine_ocr_parts(parts))
  self.assertEqual(ocr_lines(type('EmptyResult',(),{'txts':None})()),[])
 def test_runtime_ocr_capacity_preserves_headroom(self):
  with patch('server.memory_stats',return_value={'currentMb':280,'limitMb':512,'peakMb':300,'oomKills':0}):
   capacity=ocr_capacity();self.assertEqual(capacity['safePixels'],900000);self.assertEqual(capacity['reserveMb'],96)
  with patch('server.memory_stats',return_value={'currentMb':410,'limitMb':512,'peakMb':420,'oomKills':0}):
   capacity=ocr_capacity();self.assertEqual(capacity['safePixels'],524288);self.assertLess(capacity['safePixels'],capacity['validatedPixels'])

if __name__=='__main__':unittest.main()
