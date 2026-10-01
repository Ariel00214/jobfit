import re
from datetime import date

FAMILIES={
 'AI_PRODUCT':('AI 产品方向',['ai产品','aigc产品','大模型产品','智能体产品','agent产品','llm产品','模型应用','大模型','智能体','ai应用']),
 'DATA_PRODUCT':('数据产品方向',['数据产品','指标体系','数据平台','数据中台','数据治理']),
 'DATA_ANALYSIS':('数据分析方向',['数据分析师','数据分析','商业分析','sql','python','报表','可视化']),
 'PRODUCT_OPERATION':('产品运营方向',['产品运营','用户运营','增长运营','活动运营','用户增长','用户留存','转化率']),
 'CONTENT_OPERATION':('内容运营方向',['内容运营','新媒体','短视频','内容策划','账号运营','直播运营']),
 'AI_SOLUTION':('AI 解决方案方向',['解决方案','售前','客户需求','方案设计','技术方案','ai落地']),
 'PROJECT_MANAGEMENT':('项目管理方向',['项目经理','项目管理','项目交付','进度管理','项目协调']),
 'PRODUCT_MANAGER':('产品经理方向',['产品经理','需求分析','需求文档','产品设计','原型','迭代','用户研究']),
 'MARKETING':('市场营销方向',['市场营销','品牌营销','市场推广','投放','品牌策划']),
 'SALES':('销售方向',['销售','商务拓展','客户开发','销售业绩','签约']),
 'DESIGN':('设计方向',['ui设计','ux设计','交互设计','视觉设计','设计师']),
 'DEVELOPMENT':('开发方向',['开发工程师','前端开发','后端开发','软件开发','编程','java','javascript'])}
SKILLS=['ai','aigc','llm','agent','prompt','rag','产品设计','需求分析','用户研究','原型','axure','figma','sql','python','excel','数据分析','指标体系','数据治理','数据可视化','用户增长','转化率','内容运营','短视频','直播','项目管理','跨部门','沟通协调','市场营销','客户需求','方案设计','前端开发','后端开发','api','测试','文案策划','活动策划','用户运营','产品运营','产品经理','商业分析','竞品分析','需求文档']
ALIASES={'ai':['人工智能','大模型','aigc'],'llm':['大模型','语言模型'],'agent':['智能体'],'prompt':['提示词'],'rag':['检索增强'],'api':['接口'],'跨部门':['跨团队'],'产品设计':['产品方案'],'数据分析':['数据复盘'],'用户研究':['用户访谈'],'产品经理':['产品管理']}
OWNERSHIP=[('对结果负责',4),('主导',3),('牵头',3),('从0到1',3),('0-1',3),('负责',2),('独立',2),('协助',1),('参与',1)]
YEAR=re.compile(r'(\d{1,2})\s*年(?:以上|及以上|工作|相关|经验)');EDU=re.compile(r'博士|硕士|研究生|本科|大专|专科')
STATUS={'direct_match':'匹配','equivalent_match':'匹配','compensated_match':'部分匹配','partial_match':'部分匹配','needs_confirmation':'暂未体现','not_evidenced':'暂未体现','clear_gap':'暂未体现','hard_gate_conflict':'暂未体现'}
IW={'high':3.0,'medium':1.8,'low':.8};JV={'direct_match':1,'equivalent_match':.9,'compensated_match':.78,'partial_match':.52,'needs_confirmation':.5,'not_evidenced':.2,'clear_gap':0,'hard_gate_conflict':0}

def lines(text):return [x.strip(' •-—\t') for x in re.split(r'[\n。；;]+',text or '') if x.strip(' •-—\t')]
def has(text,skill):return any(w.lower() in (text or '').lower() for w in [skill]+ALIASES.get(skill,[]))
def related(text):return [s for s in SKILLS if has(text,s)]
def evidence(text,skill):
 found=[x for x in lines(text) if has(x,skill)]
 if not found:return {'level':'None','quote':''}
 def rank(x):
  outcome=bool(re.search(r'\d+\s*(?:%|％|万|人|次|元|倍)|提升|降低|增长|节省|上线|落地|交付',x));owner=max([n for w,n in OWNERSHIP if w in x] or [0]);return (2 if outcome and owner>=2 else 1 if outcome or owner>=2 else 0,len(x))
 quote=max(found,key=rank)[:180];return {'level':['Low','Medium','High'][rank(quote)[0]],'quote':quote}
def best_evidence(resume,requirement):
 found=[evidence(resume,s) for s in related(requirement)];found=[x for x in found if x['quote']]
 return max(found,key=lambda x:({'Low':1,'Medium':2,'High':3}[x['level']],len(x['quote']))) if found else {'level':'None','quote':''}
def years(text):
 m=re.search(r'(?:工作|从业|相关经验)\s*(\d{1,2})\s*年',text)
 if m:return int(m.group(1))
 work_text=re.split(r'工作及实习经历|工作经历|实习经历',text,maxsplit=1)[-1]
 dates=sorted((int(y),int(m)) for y,m in re.findall(r'(20\d{2})\s*[.年/\-]\s*(0?[1-9]|1[0-2])',work_text))
 if dates and re.search(r'至今|现在|present',work_text,re.I):dates.append((date.today().year,date.today().month))
 return min(40,round(((dates[-1][0]*12+dates[-1][1])-(dates[0][0]*12+dates[0][1]))/12,1)) if len(dates)>1 else None

def parse_resume(text):
 ls=lines(text);skills=[s for s in SKILLS if has(text,s)];ev={s:evidence(text,s) for s in skills}
 return {'basicInfo':ls[:2],'relevantExperienceYears':years(text),'skills':skills,'skillLevel':{s:ev[s]['level'] for s in skills},
 'projects':[x[:180] for x in ls if re.search(r'项目|上线|落地|产品|活动|体系',x)][:10],
 'responsibilities':[x[:180] for x in ls if re.search(r'负责|主导|参与|协助|独立|牵头',x)][:12],
 'ownership':max([n for w,n in OWNERSHIP if w in text] or [0]),'outcomes':[x[:180] for x in ls if re.search(r'\d+\s*(?:%|％|万|人|次|元|倍)|提升|降低|增长|上线|落地|交付',x)][:10],
 'industries':[x for x in ['电商','教育','金融','文旅','游戏','娱乐','企业服务','互联网','医疗','零售','制造'] if x in text],
 'education':next((x for x in ['博士','硕士','研究生','本科','大专','专科'] if x in text),None),'evidence':ev,'rawResume':text}

def classify(title,responsibilities,skills):
 body=' '.join(responsibilities)+' '.join(skills);scores={k:sum((2 if w.lower() in title.lower() else 0)+(1 if w.lower() in body.lower() else 0) for w in terms) for k,(_,terms) in FAMILIES.items()}
 if re.search('开发工程师|算法工程师|软件工程师|程序员',title):return 'DEVELOPMENT'
 if re.search('产品',title) and re.search('ai|aigc|大模型|智能体|llm',title,re.I):return 'AI_PRODUCT'
 if re.search('产品|需求|原型',title+body) and re.search('ai|aigc|大模型|智能体|llm',title+body,re.I):scores['AI_PRODUCT']+=3
 if '数据产品' in title:scores['DATA_PRODUCT']+=5
 if '产品运营' in title:scores['PRODUCT_OPERATION']+=5
 return max(scores,key=scores.get) if max(scores.values(),default=0)>0 else 'OTHER'

def infer_job_identity(text,ls):
 """Infer OCR/web title and company conservatively from visible lines."""
 cleaned=[re.sub(r'^(?:【截图\s*\d+】|页面标题\s*[:：])\s*','',x).strip() for x in ls[:60]]
 cleaned=[x for x in cleaned if x and not re.search(r'岗位职责|工作职责|任职要求|职位描述|岗位要求|薪资|福利|收藏|投递|沟通',x)]
 title='';company=''
 labelled=re.search(r'(?:职位名称|岗位名称|招聘职位|职位|岗位)\s*[:：]\s*([^\n；;]{2,50})',text)
 if labelled:title=labelled.group(1).strip()
 if not title:
  page=re.search(r'页面标题\s*[:：]\s*([^\n]{2,120})',text)
  if page:
   value=page.group(1);m=re.search(r'([^|_\-—]{2,40}?)(?:招聘|职位|薪资)',value)
   if m:title=m.group(1).strip('【】[] ')
 role_pattern=r'(?:产品经理|项目经理|数据分析师|商业分析师|设计师|[前后]端开发工程师|算法工程师|测试工程师|销售经理|运营(?:经理|主管|专员)?|顾问|专员|主管|总监|负责人|研究员|策划|编辑|商务|市场|客服|教师|会计|招聘|人力资源)'
 if not title:
  candidates=[x for x in cleaned if 2<=len(x)<=28 and re.fullmatch(r'(?:招聘[：:]?)?[A-Za-z0-9＋+#· /\-\u4e00-\u9fff]{0,18}'+role_pattern+r'(?:[（(][^）)]{1,8}[）)])?',x,re.I) and not re.search(r'负责|要求|经验|能力|熟悉|具备|我们|加入',x)]
  if candidates:title=min(candidates,key=lambda x:(len(x)>20,len(x)))
 cm=re.search(r'(?:公司名称|企业名称|公司)\s*[:：]\s*([^\n；;]{2,60})',text)
 if cm:company=cm.group(1).strip()
 if not company:
  company_candidates=[x for x in cleaned if 4<=len(x)<=60 and re.search(r'(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|集团)$',x) and x!=title and not re.search(r'负责|要求|经验|能力|岗位',x)]
  if company_candidates:company=min(company_candidates,key=len)
 return title[:60],company[:60]

def parse_jd(text,source='text',url='',metadata=None):
 metadata=metadata or {};ls=lines(text);first=ls[0][:50] if ls else '未命名岗位'
 inferred_title,inferred_company=infer_job_identity(text,ls);title=inferred_title or first
 if not inferred_title and (len(title)>32 or re.search('职责|要求|工作内容|截图|招聘信息|职位信息',title) or not re.search(r'经理|运营|分析师|设计师|工程师|开发|销售|顾问|专员|主管|总监|负责人|研究员|策划|编辑|商务|市场|客服|教师|会计|招聘|人力资源$',title)):title='未命名岗位'
 def field(label):
  m=re.search(r'(?:'+label+r')\s*[:：]\s*([^\n；;]{1,55})',text);return m.group(1).strip() if m else ''
 company=field('公司(?:名称)?|企业(?:名称)?') or inferred_company;location=field('工作地点|地点|城市');salary=field('薪资|薪酬')
 if not location:
  m=re.search(r'(北京|上海|广州|深圳|杭州|成都|南京|苏州|武汉|西安|重庆|天津|长沙|厦门|郑州|合肥|青岛|宁波|佛山)(?:[-·\s]|市)',text[:1500]);location=m.group(1) if m else ''
 relevant=[x for x in ls if not re.search('有责任心|学习能力强|抗压能力强|团队意识强|积极主动',x) and not re.search(r'^(?:职位名称|岗位名称|招聘职位|职位|岗位|公司名称|企业名称|工作地点|地点|城市|薪资|薪酬|来源平台)\s*[:：]',x)]
 requirements=[x[:180] for x in relevant if re.search(r'要求|熟悉|掌握|具备|经验|学历|本科|技能|优先|必须',x)][:14]
 responsibilities=[x[:180] for x in relevant if re.search(r'负责|推动|设计|分析|制定|协作|开发|运营|职责|搭建|管理',x)][:14]
 skills=related(' '.join(relevant));ym=YEAR.search(text);edu=EDU.search(text);completeness=min(1,(len(text)/500)*.35+min(len(responsibilities),4)/4*.35+min(len(requirements),4)/4*.3);source_quality=.8 if source=='text' else .72 if source=='image' else .9
 return {'jdId':metadata.get('jdId',''),'inputType':source,'sourceType':source,'sourcePlatform':metadata.get('sourcePlatform') or field('来源平台') or ('手动 JD' if source=='text' else '岗位截图' if source=='image' else '招聘平台'),'sourceUrl':url or metadata.get('sourceUrl',''),'sourceImage':metadata.get('sourceImage',[]),'rawJD':text,'jobDescription':text,
 'jobTitle':title,'company':company,'location':location,'salary':salary,'responsibilities':responsibilities,'requirements':requirements,'jobFamily':classify(title,responsibilities,skills),'seniority':'高级' if re.search('高级|资深|专家|总监',title) else '初级' if re.search('初级|助理|实习|junior',title,re.I) else '未注明','industry':next((x for x in ['电商','教育','金融','文旅','游戏','娱乐','企业服务','互联网','医疗','零售','制造'] if x in text),''),'coreResponsibilities':responsibilities[:6],'coreSkills':skills[:12],'skillRequirements':skills,'experienceRequirement':int(ym.group(1)) if ym else None,'educationRequirement':edu.group(0) if edu else None,'importantRequirements':requirements[:6],'preferredRequirements':[x for x in relevant if re.search('加分|优先',x)][:5],
 'dataReliability':{'score':round(completeness*source_quality,2),'jdCompleteness':round(completeness,2),'sourceQuality':source_quality,'missing':(['完整岗位职责'] if len(responsibilities)<2 else [])+(['任职要求'] if len(requirements)<2 else [])}}

def clean_requirement(text):
 text=re.sub(r'^\s*[（(]?\d+[）).、．:]\s*','',text or '')
 return re.sub(r'^(?:岗位职责|工作职责|任职要求|岗位要求|要求)\s*[:：]?\s*','',text).strip(' ，。；;')

def dimension_key(text):
 groups=[('ai_product',r'ai|aigc|大模型|智能体|agent|prompt|rag'),('content_growth',r'内容|新媒体|短视频|直播|传播|增长|营销'),('data_decision',r'数据|指标|sql|分析|复盘|转化|留存'),('product_delivery',r'产品|需求|原型|迭代|上线|用户研究'),('customer_solution',r'客户|企业服务|售前|解决方案|交付|商务'),('collaboration',r'协作|跨部门|沟通|项目管理|推动|协调')]
 return next((k for k,p in groups if re.search(p,text,re.I)),re.sub(r'\W','',text)[:16] or 'other')

def requirement_meaning(requirement,jd=None):
 text=clean_requirement(requirement);jd=jd or {};family=jd.get('jobFamily','');industry=jd.get('industry','');title=jd.get('jobTitle','该岗位')
 if re.search(r'ai|aigc|大模型|智能体|agent|prompt|rag',text,re.I):
  scene='真实业务场景' if not industry else f'{industry}业务场景'
  action='形成可落地的产品方案' if family in ('AI_PRODUCT','PRODUCT_MANAGER') else '支持实际运营与业务结果'
  return f'是否能够把 AI 能力用于{scene}并{action}'
 if re.search(r'内容|新媒体|短视频|直播|传播',text):
  return '是否能够围绕目标用户完成内容策划、传播并根据反馈持续优化'
 if re.search(r'数据|指标|sql|分析|复盘|转化|留存',text,re.I):
  target='内容表现' if family=='CONTENT_OPERATION' else '产品与业务效果' if family in ('PRODUCT_MANAGER','AI_PRODUCT','DATA_PRODUCT') else '关键业务表现'
  return f'是否能够用数据判断{target}并推动后续改进'
 if re.search(r'客户|企业服务|售前|解决方案|交付',text):
  return '是否能够理解客户的真实需求并推动方案落地与持续交付'
 if re.search(r'协作|跨部门|沟通|项目管理|推动|协调',text):
  scene='产品落地' if '产品' in title or family in ('AI_PRODUCT','PRODUCT_MANAGER') else '关键项目完成'
  return f'是否能够明确承担个人责任并协调不同角色推动{scene}'
 if re.search(r'需求|原型|产品|迭代|上线|用户研究',text):
  return '是否能够从真实用户需求出发完成方案设计并推动产品迭代落地'
 terms=[x for x in re.split(r'[、，,及和或/；;]',text) if 2<=len(x)<=18]
 subject='、'.join(terms[:2]) or text
 return f'是否具备在当前岗位中运用{subject}解决实际问题的经验'

def combined_evidence(resume,requirement):
 candidates=[]
 key=dimension_key(requirement);patterns={'ai_product':r'ai|aigc|大模型|智能体|agent|prompt|rag','content_growth':r'内容|新媒体|短视频|直播|传播|增长|营销','data_decision':r'数据|指标|sql|分析|复盘|转化|留存','product_delivery':r'产品|需求|原型|迭代|上线|用户研究','customer_solution':r'客户|企业服务|售前|解决方案|交付|商务','collaboration':r'协作|跨部门|联合|沟通|项目|推动|协调'}
 pattern=patterns.get(key)
 for line in lines(resume):
  if ((pattern and re.search(pattern,line,re.I)) or any(has(line,s) for s in related(requirement))) and line not in [x[1] for x in candidates]:
   outcome=bool(re.search(r'\d+\s*(?:%|％|万|人|次|元|倍)|提升|降低|增长|节省|上线|落地|交付',line));owner=max([n for w,n in OWNERSHIP if w in line] or [0]);rank=3 if outcome and owner>=2 else 2 if outcome or owner>=2 else 1
   candidates.append((rank,line[:180]))
 candidates.sort(key=lambda x:(x[0],len(x[1])),reverse=True);chosen=candidates[:3]
 if not chosen:return {'level':'None','quotes':[]}
 score=sum(x[0] for x in chosen);level='High' if chosen[0][0]==3 or score>=5 else 'Medium' if chosen[0][0]>=2 or len(chosen)>=2 else 'Low'
 return {'level':level,'quotes':[x[1] for x in chosen]}

def item(requirements,category,importance,resume,jd):
 requirements=requirements if isinstance(requirements,list) else [requirements];joined='；'.join(requirements)
 ev=combined_evidence(resume,joined);judgment={'High':'direct_match','Medium':'equivalent_match','Low':'partial_match','None':'not_evidenced'}[ev['level']]
 if re.search(r'(?:必须|须持有|持证).{0,12}(?:律师执业|医师资格|教师资格|注册会计师|CPA|工作许可|签证|驾驶证)',joined,re.I) and ev['level']=='None':judgment='needs_confirmation';category='hard_gate'
 meaning=requirement_meaning(joined,jd);quotes=ev['quotes']
 if quotes:
  evidence_text='；'.join(quotes)
  bridge=('这些经历直接覆盖了岗位的核心工作场景。' if ev['level']=='High' else '这些相邻经历共同证明了能力具备合理的迁移基础。' if ev['level']=='Medium' else '目前只有技能或局部实践线索，尚不足以证明完整胜任。')
 else:evidence_text='当前简历中没有找到足以支持这一判断的真实经历。';bridge='没有证据时不根据关键词推断能力。'
 return {'requirementRaw':requirements[0],'jdSources':requirements,'requirementMeaning':meaning,'requirement':meaning,'category':category,'importance':importance,'evidence':evidence_text,'evidenceItems':quotes,'evidenceStrength':ev['level'],'judgment':judgment,'judgmentLabel':STATUS[judgment],'reason':bridge,'compensationReason':''}

def action_for(x,jd,profile):
 topic=re.sub(r'^是否(?:能够|具备)?','',x.get('requirementMeaning') or x['requirement']);ev=x.get('evidence','');raw='；'.join(x.get('jdSources',[]));key=dimension_key(raw);has_ev=bool(x.get('evidenceItems'))
 owner=bool(re.search(r'负责|主导|牵头|独立',ev));outcome=bool(re.search(r'\d+\s*(?:%|％|万|人|次|元|倍)|提升|降低|增长|上线|落地|交付',ev))
 low_value=x.get('importance')=='low' or bool(re.search(r'优先|加分',raw))
 if low_value:
  return {'state':'D','title':'暂时不用补','duration':'先不投入额外时间','why':'这不是当前岗位最可能决定筛选结果的条件，把时间留给核心工作证据收益更高。','steps':['先核对它是否为硬性门槛；若只是优先项，面试时如实说明即可。'],'done':'不新增课程或项目，能清楚说明现状和相邻经验就停止。','use':'把时间优先用于完善最重要的项目证据。'}
 if has_ev and (not owner or not outcome):
  missing='个人责任与协作边界' if not owner else '可核实的结果、规模或交付范围'
  return {'state':'A','title':'先别做新项目 · 30分钟补证','duration':'30分钟','why':f'现有经历已经能支持“{topic}”，当前最短路径是补清{missing}，而不是重新制造经历。','steps':['打开上面最相关的真实经历。',f'补写目标、你的关键动作，以及{missing}。','没有百分比时，使用真实的数量、频率、周期、交付物或用户反馈，不编数字。'],'done':'形成一条包含背景、个人动作和真实结果的简历描述，并能在两分钟内讲清楚。','use':'直接替换简历原描述，同时作为面试追问案例。'}
 if has_ev:
  context_step='说明 AI 在哪一步真正产生价值，以及为什么没有采用更复杂的方案。' if jd.get('jobFamily')=='AI_PRODUCT' else '带上一次内容数据变化及据此调整选题或传播策略的记录。' if jd.get('jobFamily')=='CONTENT_OPERATION' else '说明一个客户需求如何被转成优先级、产品取舍或交付决定。' if jd.get('industry')=='企业服务' or key=='customer_solution' else '准备一个遇到阻碍后如何取舍的细节。'
  return {'state':'A','title':'面试前准备 · 20分钟核验证据','duration':'20分钟','why':f'“{topic}”已有较强证据，继续做新项目的边际收益较低；招聘者更会核对真实性和个人贡献。','steps':['写下项目规模、你的决定、协作边界和结果口径。',context_step],'done':'所有说法都能回到真实材料或交付物，且不把团队成果全部算到自己名下。','use':'用于面试回答和作品集项目说明。'}
 adjacent=bool(profile.get('skills') or profile.get('projects'))
 if adjacent and key=='ai_product':
  scene='内容选题助手' if jd.get('jobFamily')=='CONTENT_OPERATION' else '客户需求整理工具' if jd.get('jobFamily')=='AI_SOLUTION' or jd.get('industry')=='企业服务' else '岗位面试问题生成器'
  return {'state':'B','title':'最短补证方案 · 3天','duration':'1～3天','why':'你已有相邻工具或产品基础，真正缺的是一段可访问、可解释的真实 AI 产品证据，不需要先学完整课程。','steps':[f'选择一个真实问题，做一个轻量“{scene}”。','用 ChatGPT、Claude Code 或 Cursor 跑通输入、模型判断、结构化输出这一条核心流程。','找 3 位真实体验者，记录反馈并据此修改一版。'],'done':'有可操作页面、完整核心流程、至少一个异常处理、3份真实反馈和一次迭代；不要求多 Agent 或复杂架构。','use':'作为作品集项目，重点说明需求来源、产品取舍、AI 价值和迭代依据。'}
 if adjacent:
  task='复盘历史内容数据并形成一次优化前后对比' if jd.get('jobFamily')=='CONTENT_OPERATION' or key=='content_growth' else '整理真实客户问题并形成需求优先级' if key=='customer_solution' else '在已有项目中补一次真实用户测试并根据反馈迭代'
  return {'state':'B','title':'最短补证方案 · 1～3天','duration':'1～3天','why':f'你有相邻能力，但缺少能直接证明“{topic}”的产物；做一次小型真实任务比泛泛学习更有效。','steps':[task+'。','保留输入材料、你的判断过程和修改前后结果。','只记录真实数据；没有百分比就记录数量、周期、范围或反馈。'],'done':'产出一份可展示的分析/原型/迭代记录，并能解释为什么这样判断。','use':'加入作品集或面试材料，完成后再决定是否改进简历。'}
 return {'state':'C','title':'先完成一个最小练习','duration':'1～3小时','why':f'当前简历没有“{topic}”的基础证据，直接做复杂项目成本过高。','steps':['先理解完成这类工作最核心的输入、判断和输出。','使用一个真实小样本完成一次输入→判断→产出的闭环。','记录哪里不会、如何验证，并保留最终产物。'],'done':'能独立完成一次最小闭环并讲清步骤；尚未真实完成前，不写入简历。','use':'先作为学习产物；获得真实使用或反馈后，再升级为作品集证据。'}

def interview_prep(profile,jd,items,focus):
 family=jd.get('jobFamily','OTHER');industry=jd.get('industry') or '当前业务';questions=[]
 by_key={dimension_key('；'.join(x.get('jdSources',[]))):x for x in items if x.get('category') not in ('formal_condition','hard_gate')}
 def evidence_use(x):
  quotes=x.get('evidenceItems',[])
  if quotes:
   relation='直接证明' if x.get('evidenceStrength')=='High' else '证明其中可迁移的判断与推进能力'
   return f'优先使用“{quotes[0]}”。它可以{relation}；只讲本人真实负责的部分。'
  nearby=next((v for v in profile.get('projects',[])+profile.get('responsibilities',[]) if v),None)
  return f'没有直接经历。先明确说明这一点，再用“{nearby}”证明相邻的需求理解、判断或推进能力。' if nearby else '当前没有直接或相邻证据。面试中应诚实说明经验边界，再描述自己会如何验证判断，不能虚构案例。'
 def add(priority,label,question,intent,answer,x=None,follow=None,warning=''):
  questions.append({'priority':priority,'label':label,'question':question,'intent':intent,'answerFocus':answer,'evidenceUse':evidence_use(x or {}),'followUps':follow or [],'warning':warning})
 primary=next((x for x in items if x.get('category')!='formal_condition'),items[0] if items else {})
 ev=(primary.get('evidenceItems') or [''])[0]
 if ev:
  excerpt=ev[:62].rstrip('，。；;')
  if family=='AI_PRODUCT':
   add('高概率必问','Ownership 核对',f'你在“{excerpt}”中亲自做出的产品判断是什么，哪些环节由 AI 工具或技术同事完成？','确认你是否拥有产品决策与结果责任，而不只是会使用 AI 工具。',['先划清你、工具和协作方各自完成的部分。','挑一个由你决定的需求取舍，说明依据和验证结果。'],primary,['如果没有你的判断，这个方案最可能在哪一步不同？','你否决过哪个看似可行的方案，为什么？'],'不要把 AI 生成的实现或团队交付表述为自己独立开发。')
  elif family=='CONTENT_OPERATION':
   add('高概率必问','结果归因',f'简历中的“{excerpt}”最终效果里，选题、渠道、资源和执行分别起了什么作用，你实际改变了哪一步？','确认结果是否能合理归因到你的内容判断，而不是平台流量或团队资源。',['先拆开选题、分发、资源和时间因素。','指出你改变的变量，再说明数据如何支持判断。'],primary,['如果换一个渠道，结论还成立吗？','哪条内容没有达到预期，你后来改了什么？'],'只使用能解释统计口径的真实数据。')
  else:
   add('高概率必问','责任边界',f'在“{excerpt}”这段经历中，你推动了哪几个关键节点，哪些决定需要客户、产品或交付团队共同确认？','确认你是否真的承担了需求澄清、取舍和推进责任。',['按需求进入、关键分歧、你的判断和最终交付顺序回答。','明确哪些结果来自团队，哪些节点由你推动。'],primary,['客户最初的说法和真实诉求有什么差别？','如果资源少一半，你会保留哪一步？'])
 if family=='AI_PRODUCT':
  scene='行程建议' if industry=='文旅' else '核心回答结果'
  add('岗位业务题','AI 质量判断',f'如果{industry}用户反馈 AI 生成的{scene}信息完整，但实际不可用，你会怎样判断问题来自模型、Prompt、数据、Workflow 还是产品交互？','确认你能定位 AI 结果质量问题，而不是只会反复修改提示词。',['先定义“不可用”的具体表现与评价标准。','按模型能力、上下文数据、Prompt、流程节点和交互约束逐层排查。','选择最小改动做对照验证，再决定是否改模型或产品路径。'],by_key.get('ai_product',primary),['你会先看哪三条日志或用户样本？','什么情况下你会接受结果不完美而选择上线？'])
  add('加分题','轻量 Case',f'一个{industry} AI 功能首次使用人数不少，但一周内再次使用率很低。你会如何区分“结果质量差”和“使用场景频率低”？','确认你能把业务场景、产品路径和模型效果放在同一个分析框架里。',['先拆首用来源、任务完成率、满意度、复用场景与回访周期。','提出两到三个互斥假设，并说明各自需要什么证据。','用成本最低的实验验证最可能的假设。'],by_key.get('data_decision',primary),['如果没有埋点，你会先收集什么替代证据？'])
 elif family=='CONTENT_OPERATION':
  add('岗位业务题','数据诊断','一组内容最近曝光明显上升，但互动和转化同时下降。你会先检查哪些环节，下一轮内容怎么调整？','确认你能区分流量质量、选题吸引力、内容承接和转化路径的问题。',['按曝光→点击/停留→互动→转化定位下降发生在哪一步。','比较人群、渠道、题材和发布时间，提出可验证假设。','下一轮只改一个关键变量，避免无法归因。'],by_key.get('data_decision',primary),['如果播放量是平台推荐带来的，你还会保留这个选题吗？'],'不要只报增长百分比，要说明指标口径和对照范围。')
  add('岗位业务题','内容取舍',f'在{industry}场景里，一个热点能带来短期流量，但与账号长期定位不完全一致，你会不会跟？','确认你能在流量、用户心智和业务目标之间做内容取舍。',['先说明账号目标和目标用户。','评估热点与定位的连接点、潜在收益和稀释风险。','给出跟、改造后跟或不跟的判断及验证方式。'],by_key.get('content_growth',primary),['如果商务方坚持要跟，你怎么统一方向？'])
 else:
  add('岗位业务题','客户需求判断','客户强烈要求一个当前产品不支持的功能，并表示不做就影响续约。你会如何澄清需求并推进决策？','确认你能区分客户表面要求与真实业务问题，同时管理产品边界和客户预期。',['追问使用角色、业务目标、发生频率和不解决的损失。','判断是通用需求、配置问题还是定制诉求。','与产品和交付评估价值、成本与替代方案，再明确反馈节奏。'],by_key.get('customer_solution',primary),['如果只有这一个客户需要，你如何决定是否做？','短期无法支持时，你如何避免过度承诺？'],'不要先承诺交付日期，再回内部寻找资源。')
  add('加分题','产品数据 Case','某个客户呼声很高的功能上线后，真实使用率很低。你怎样判断是功能价值不足、入口难找，还是客户没有完成组织推广？','确认你能把使用数据、客户场景和产品设计结合起来判断功能效果。',['看目标角色覆盖、入口曝光、首次使用、任务完成和重复使用。','结合客户访谈与使用路径提出不同原因假设。','分别设计产品优化、用户教育或客户成功动作。'],by_key.get('data_decision',primary),['哪一个指标最能帮助你先排除一种原因？'])
 if focus and len(questions)<4:
  f=focus[0];x=next((i for i in items if i.get('requirementRaw')==f.get('jdBasis')),primary)
  if not x.get('evidenceItems') or x.get('evidenceStrength')=='Low':
   add('高风险追问','简历疑点',f['title'],f['why'],['先直接回答事实边界。','再用最接近的真实经历证明可迁移部分；没有直接经验时明确说明。'],x,[f"如果现在让你补齐这项证据，你会先验证什么？"])
 return questions[:4]

def match(profile,jd,resume):
 source=[]
 for raw in jd['coreResponsibilities']+jd['importantRequirements']:
  if raw not in source and not re.search(r'\d+\s*年以上|学历|本科|硕士|博士|大专|专科',raw):source.append(raw)
 clusters={}
 for raw in source:clusters.setdefault(dimension_key(raw),[]).append(raw)
 ranked=sorted(clusters.values(),key=lambda xs:(any(x in jd['coreResponsibilities'][:3] for x in xs),len(xs)),reverse=True)
 items=[item(xs,'core_responsibility','high' if i<3 else 'medium',resume,jd) for i,xs in enumerate(ranked[:5])]
 req=jd['experienceRequirement'];actual=profile['relevantExperienceYears']
 if req:
  judgment='needs_confirmation';ev=f'简历可识别相关经历约 {actual:g} 年' if actual is not None else '';comp=''
  if actual is not None and actual>=req:judgment='direct_match'
  elif actual is not None and profile['ownership']>=2 and (profile['projects'] or profile['outcomes']):judgment='compensated_match';comp='年限略低，但高度相关的职责深度、Ownership 或真实成果形成补偿。'
  elif actual is not None:judgment='partial_match'
  raw=f'{req} 年以上相关经验';items.append({'requirementRaw':raw,'jdSources':[raw],'requirementMeaning':'是否具备足以承担岗位核心职责的相关实践深度','requirement':'是否具备足以承担岗位核心职责的相关实践深度','category':'formal_condition','importance':'medium','evidence':ev or '当前简历中没有识别到可靠的经历年限。','evidenceItems':[ev] if ev else [],'evidenceStrength':'Medium' if ev else 'None','judgment':judgment,'judgmentLabel':STATUS[judgment],'reason':comp or ('经历年限与岗位要求一致。' if judgment=='direct_match' else '需要结合职责深度判断，不能只按年限关键词下结论。'),'compensationReason':comp})
 if jd['educationRequirement']:
  edu=profile['education'];rank={'专科':1,'大专':1,'本科':2,'研究生':3,'硕士':3,'博士':4};judgment='needs_confirmation' if not edu else 'direct_match' if rank.get(edu,0)>=rank.get(jd['educationRequirement'],0) else 'partial_match'
  raw=jd['educationRequirement']+'学历';items.append({'requirementRaw':raw,'jdSources':[raw],'requirementMeaning':'是否满足招聘方明确列出的学历条件','requirement':'是否满足招聘方明确列出的学历条件','category':'formal_condition','importance':'low','evidence':edu or '当前简历中没有识别到学历信息。','evidenceItems':[edu] if edu else [],'evidenceStrength':'Medium' if edu else 'None','judgment':judgment,'judgmentLabel':STATUS[judgment],'reason':'学历只作为明确条件核对，不替代对实际能力的判断。','compensationReason':'' if judgment=='direct_match' else '学历默认不是淘汰门槛，需结合实际职责与招聘方口径确认。'})
 if len(items)<3:
  items += [item(x,'supporting_skill','medium',resume,jd) for x in jd['coreSkills'][:4] if not any(x in ' '.join(y.get('jdSources',[])).lower() for y in items)]
 resume_ok=len(resume)>=180 and bool(profile['responsibilities'] or profile['projects']);eligible=jd['dataReliability']['score']>=.42 and resume_ok and len(items)>=3
 missing=list(jd['dataReliability']['missing'])+([] if resume_ok else ['可验证的简历职责或项目经历'])+([] if len(items)>=3 else ['足够的核心招聘判断项'])
 if eligible:
  total=sum(IW[x['importance']] for x in items);score=round(sum(IW[x['importance']]*JV[x['judgment']] for x in items)/total*100);cs=[round(100*IW[x['importance']]*JV[x['judgment']]/total) for x in items];cs[-1]+=score-sum(cs)
  for x,c in zip(items,cs):x['contribution']=c
 else:
  score=None
  for x in items:x['contribution']=None
 covered=sum(x['judgment'] in ('direct_match','equivalent_match','compensated_match','partial_match') for x in items);confidence='high' if eligible and jd['dataReliability']['score']>=.72 and covered>=4 else 'medium' if eligible else 'low'
 positive=[x for x in items if x['judgment'] in ('direct_match','equivalent_match','compensated_match','partial_match') and x['evidenceItems'] and x['category']!='formal_condition']
 strengths=[]
 for x in positive:
  if any(y['title']==x['requirementMeaning'] for y in strengths):continue
  strengths.append({'title':x['requirementMeaning'],'jdBasis':x['requirementRaw'],'jdSources':x['jdSources'],'evidence':x['evidence'],'analysis':x['reason'],'judgment':x['judgmentLabel'],'evidenceStrength':x['evidenceStrength']})
 focus=[]
 for x in items:
  if x['category']=='formal_condition':continue
  ev=x.get('evidence','');topic=re.sub(r'^是否(?:能够|具备)?','',x['requirementMeaning'])
  if x['judgment'] in ('direct_match','equivalent_match') and x['evidenceStrength']=='High':
   if len(focus)>=2 or x['importance']!='high':continue
   title=f'你在{topic}的实践中做出的关键判断和个人贡献如何验证'
   why='这项能力已有较强证据；招聘者下一步更可能核对项目规模、个人决策以及结果口径，而不是重复确认是否做过。'
  elif not x.get('evidenceItems'):
   title=f'能否提供真实经历证明你{topic}'
   why='该能力会影响岗位核心工作的完成，但当前简历没有给出可核实的行动或结果，招聘者需要在面试中确认实际基础。'
  elif profile['ownership']<2 or not re.search(r'负责|主导|牵头|独立',ev):
   title=f'你在{topic}的经历中具体承担了什么责任'
   why='简历已经显示相关经历，但个人决策、协作边界与团队成果之间的关系还不够清楚。'
  elif not re.search(r'\d+\s*(?:%|％|万|人|次|元|倍)|提升|降低|增长|上线|落地|交付',ev):
   title=f'这段{topic}的实践最终产生了什么可验证结果'
   why='现有证据说明做过相关事情，但成果、规模或效果尚不明确，招聘者会据此判断实践深度。'
  else:
   title=f'这段{topic}的经验能否迁移到当前岗位场景'
   why='已有经历与岗位相邻，但业务对象、场景或复杂度并不完全相同，招聘者会确认迁移边界。'
  act=action_for(x,jd,profile)
  prepare=f"{act['title']}：{act['steps'][0]} 完成标准：{act['done']}"
  focus.append({'title':title,'jdBasis':x['requirementRaw'] if x['category']!='formal_condition' else '', 'jdSources':x.get('jdSources',[]),'evidence':ev,'why':why,'confirm':title,'prepare':prepare,'action':act})
 focus=focus[:4]
 action_candidates=[]
 for x in items:
  if x['category'] in ('formal_condition','hard_gate'):continue
  act=action_for(x,jd,profile)
  priority={'A':4,'B':5,'C':3,'D':0}[act['state']]+({'high':3,'medium':2,'low':0}.get(x['importance'],1))+(2 if x['judgment'] in ('not_evidenced','partial_match') else 0)
  if not any(a[1]['title']==act['title'] and a[1]['why']==act['why'] for a in action_candidates):action_candidates.append((priority,act))
 action_candidates.sort(key=lambda a:a[0],reverse=True)
 primary_action=action_candidates[0][1] if action_candidates else {'state':'D','title':'暂时不用补','duration':'','why':'当前资料不足以生成可靠行动。','steps':['补充完整 JD 与真实简历经历后再判断。'],'done':'资料完整即可。','use':'重新分析。'}
 secondary_actions=[a for _,a in action_candidates[1:] if a['state']!='D'][:2]
 checks=[]
 for x in items:
  if x['category'] in ('formal_condition','hard_gate'):
   result='符合' if x['judgment']=='direct_match' else '存在条件差异' if x['judgment'] in ('clear_gap','hard_gate_conflict') else '需确认' if x['judgment'] in ('needs_confirmation','compensated_match','partial_match') else '暂未体现';checks.append({'condition':x['requirement'],'evidence':x['evidence'] or '简历暂未体现','result':result,'note':x['compensationReason'] or ('现有证据与 JD 条件一致。' if result=='符合' else '信息需要由候选人或招聘方进一步确认。')})
 summary=f"{sum(x['result']=='符合' for x in checks)} 项符合 · {sum(x['result']!='符合' for x in checks)} 项需确认" if checks else 'JD 未列出需单独核对的明确条件'
 return {'matchScore':score,'scoreConfidence':confidence,'confidence':confidence,'scoreUnavailableReason':'；'.join(dict.fromkeys(missing)) if not eligible else '','matchBreakdown':items,'strengths':strengths,'moreStrengths':[],'hrFocus':focus,'moreHrFocus':[],'primaryAction':primary_action,'secondaryActions':secondary_actions,'interviewPrep':interview_prep(profile,jd,items,focus),'conditionChecks':checks,'conditionSummary':summary,'dataReliability':{**jd['dataReliability'],'resumeCompleteness':'adequate' if resume_ok else 'insufficient','evidenceCoverage':round(covered/len(items),2) if items else 0},'gaps':[x['title'] for x in focus]}

def analyze(resume,jds):
 profile=parse_resume(resume);groups={}
 for jd in jds:
  result={**jd,**match(profile,jd,resume)};groups.setdefault(jd['jobFamily'],[]).append(result)
 families=[]
 for key,jobs in groups.items():
  jobs.sort(key=lambda x:(x['matchScore'] is not None,x['matchScore'] or -1),reverse=True);scores=[x['matchScore'] for x in jobs if x['matchScore'] is not None]
  families.append({'key':key,'name':FAMILIES.get(key,('其他方向',))[0],'familyMatchScore':round(sum(scores)/len(scores)) if scores else None,'scoredCount':len(scores),'totalCount':len(jobs),'jobs':jobs})
 families.sort(key=lambda x:(x['familyMatchScore'] is not None,x['familyMatchScore'] or -1),reverse=True);all_jobs=[j for g in families for j in g['jobs']]
 for job in all_jobs:
  if not job['location']:job['similarJobs']=[];job['similarJobsMessage']='需要确认岗位城市后才能进行同城推荐。';continue
  similar=[x for x in all_jobs if x['jdId']!=job['jdId'] and x['location']==job['location'] and x.get('sourceUrl') and x['jobFamily']==job['jobFamily']]
  job['similarJobs']=[{k:x[k] for k in ('jdId','jobTitle','company','location','salary','sourcePlatform','sourceUrl')} for x in similar[:5]];job['similarJobsMessage']='' if job['similarJobs'] else '暂未找到可验证的同城相似岗位。'
 return {'profile':profile,'families':families}
