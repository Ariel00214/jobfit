import re
from collections import Counter
from datetime import datetime, timezone

FAMILIES = {
 'AI_PRODUCT': ('AI 产品', ['ai产品','aigc产品','大模型产品','智能体产品','agent产品','llm产品','ai应用','人工智能产品']),
 'DATA_PRODUCT': ('数据产品', ['数据产品','指标体系','数据平台','数据中台','数据治理']),
 'DATA_ANALYSIS': ('数据分析', ['数据分析师','数据分析','商业分析','sql','python','报表','可视化']),
 'PRODUCT_OPERATION': ('产品运营', ['产品运营','用户运营','增长运营','活动运营','用户增长','用户留存','转化率']),
 'CONTENT_OPERATION': ('内容运营', ['内容运营','新媒体','短视频','内容策划','账号运营','直播运营']),
 'AI_SOLUTION': ('AI 解决方案', ['解决方案','售前','客户需求','方案设计','技术方案','ai落地']),
 'PROJECT_MANAGEMENT': ('项目管理', ['项目经理','项目管理','项目交付','进度管理','项目协调']),
 'PRODUCT_MANAGER': ('产品经理', ['产品经理','需求分析','需求文档','产品设计','原型','迭代','用户研究']),
 'MARKETING': ('市场营销', ['市场营销','品牌营销','市场推广','投放','品牌策划']),
 'SALES': ('销售/商务', ['销售','商务拓展','客户开发','销售业绩','签约']),
 'DESIGN': ('设计', ['ui设计','ux设计','交互设计','视觉设计','设计师']),
 'DEVELOPMENT': ('开发', ['开发工程师','前端开发','后端开发','软件开发','编程','java','javascript']),
}

CAPABILITIES = {
 'AI 应用理解':['ai','人工智能','aigc','大模型','llm','智能体','agent','prompt','提示词','rag'],
 '产品需求分析':['需求分析','需求文档','prd','用户需求','产品方案','产品设计','原型','axure','figma'],
 '用户研究':['用户研究','用户访谈','问卷','可用性测试','用户反馈'],
 '数据驱动决策':['数据分析','数据复盘','后台数据','指标体系','转化率','留存','增长','报表','sql','python','excel','可视化'],
 '内容策略':['内容运营','内容策划','新媒体','短视频','直播','账号运营','选题','文案'],
 '用户与增长运营':['用户运营','产品运营','增长运营','活动运营','拉新','留存','转化'],
 '项目推进':['项目管理','项目推进','排期','里程碑','进度','上线','落地','交付'],
 '跨团队协作':['跨团队','跨部门','协调','协同','对接','stakeholder'],
 '客户与方案':['客户需求','解决方案','方案设计','售前','客户沟通','交付方案'],
 '市场与品牌':['市场营销','品牌营销','推广','投放','品牌策划'],
 '销售与商务':['销售','商务拓展','客户开发','签约','成交'],
 '软件实现':['前端','后端','开发','编程','javascript','java','api','接口','测试'],
 '设计表达':['ui','ux','交互设计','视觉设计','设计师'],
}

TRANSFER = {
 '数据驱动决策':['产品需求分析','用户与增长运营'],
 '内容策略':['用户与增长运营','市场与品牌'],
 '跨团队协作':['项目推进','客户与方案'],
 '项目推进':['产品需求分析','客户与方案'],
 '客户与方案':['产品需求分析','销售与商务'],
 'AI 应用理解':['产品需求分析','客户与方案'],
}

OWNERSHIP = [('主导','lead'),('牵头','lead'),('负责人','own'),('全权负责','own'),('独立负责','own'),('负责','own'),('推动','execute'),('推进','execute'),('执行','execute'),('完成','execute'),('协调','collaborate'),('协同','collaborate'),('配合','collaborate'),('协助','assist'),('参与','assist')]
RESULT_RE = re.compile(r'\d+(?:\.\d+)?\s*(?:%|％|万|千|人|次|元|倍|小时|天)|提升|降低|增长|节省|上线|落地|交付|完成')
DATE_RE = re.compile(r'(20\d{2})[./年-](0?[1-9]|1[0-2])')
YEAR_REQ = re.compile(r'(\d{1,2})\s*年(?:以上|及以上|工作|相关|经验)')
EDU_RE = re.compile(r'博士|硕士|研究生|本科|大专|专科')
GENERIC = ['责任心','学习能力','抗压','团队意识','积极主动','工作态度','沟通能力强']

def lines(text):
 return [x.strip(' •-—\t0123456789.、)）') for x in re.split(r'[\n。；;，]+', text or '') if x.strip(' •-—\t0123456789.、)）')]

def contains(text, terms):
 t=(text or '').lower()
 return any(w.lower() in t for w in terms)

def ownership_of(text):
 for word, level in OWNERSHIP:
  if word in text:return level
 return 'unknown'

def ownership_weight(level):
 return {'lead':1,'own':.9,'execute':.72,'collaborate':.58,'assist':.35,'unknown':.42}.get(level,.42)

def capability_hits(text):
 return [name for name,terms in CAPABILITIES.items() if contains(text,terms)]

def extract_blocks(text):
 result=[]
 for i,s in enumerate(lines(text)):
  caps=capability_hits(s)
  if not caps and not re.search(r'公司|任职|岗位|项目|职责|教育|学历',s):continue
  own=ownership_of(s)
  result.append({'id':f'e{i+1}','rawText':s[:260],'type':'project' if '项目' in s else 'experience','capabilities':caps,
   'ownership':own,'hasOutcome':bool(RESULT_RE.search(s)),'metrics':re.findall(r'\d+(?:\.\d+)?\s*(?:%|％|万|千|人|次|元|倍)',s),
   'projectComplexity':'high' if len(caps)>=3 or contains(s,['跨团队','多个','全流程','从0到1']) else 'medium' if len(caps)>=2 else 'low','source':'resume'})
 return result

def evidence_level(block, capability, direct=True):
 if not block:return 'none'
 base=ownership_weight(block['ownership'])
 base+=.18 if block['hasOutcome'] else 0
 base+=.1 if block['projectComplexity']=='high' else .04 if block['projectComplexity']=='medium' else 0
 if not direct: return 'transferable' if base>=.45 else 'weak'
 if base>=.92:return 'strong'
 if base>=.65:return 'medium'
 return 'weak'

def annotate_strength(block):
 """Attach an intrinsic evidence grade without turning inferred capability into fact."""
 levels=[evidence_level(block,c,True) for c in block.get('capabilities',[])]
 rank={'strong':4,'medium':3,'transferable':2,'weak':1,'none':0}
 block['evidenceStrength']=max(levels,key=lambda x:rank[x]) if levels else 'weak'
 return block

def work_years(text):
 explicit=re.search(r'(?:工作|从业)\s*(\d{1,2})\s*年',text)
 if explicit:return int(explicit.group(1))
 months=[]
 for s in lines(text):
  if re.search(r'教育|大学|学院|硕士|本科|大专|项目时间',s):continue
  dates=DATE_RE.findall(s)
  if len(dates)>=2 and re.search(r'公司|任职|工作|岗位',s):
   a=int(dates[0][0])*12+int(dates[0][1]);b=int(dates[-1][0])*12+int(dates[-1][1]);months.append(max(0,b-a))
 return round(sum(months)/12,1) if months else None

def parse_resume(text, supplements=None):
 supplements=supplements or []
 base=extract_blocks(text)
 extra=[]
 for i,x in enumerate(supplements):
  cap=x.get('relatedCapability','').strip()
  inferred=capability_hits(x.get('rawText',''));caps=list(dict.fromkeys(([cap] if cap else [])+inferred))
  extra.append({'id':f's{i+1}','rawText':x.get('rawText','')[:260],'type':'supplement','capabilities':caps,
   'ownership':x.get('ownership') or ownership_of(x.get('rawText','')),'hasOutcome':bool(RESULT_RE.search(x.get('rawText',''))),'metrics':re.findall(r'\d+(?:\.\d+)?\s*(?:%|％|万|千|人|次|元|倍)',x.get('rawText','')),
   'projectComplexity':'medium','source':'userSupplement','reusable':bool(x.get('reusable',True))})
 base=[annotate_strength(x) for x in base];extra=[annotate_strength(x) for x in extra]
 all_ev=base+extra
 explicit=[];hidden=[]
 for cap in CAPABILITIES:
  direct=[e for e in all_ev if cap in e['capabilities']]
  if direct:explicit.append(cap)
 # Hidden capabilities require behavioral evidence, never invented facts.
 patterns={'项目推进':['排期','推进','上线','里程碑','交付'],'跨团队协作':['协调','跨团队','跨部门','对接'],'数据驱动决策':['根据数据','后台数据','数据复盘','指标'],'用户研究':['访谈','问卷','用户反馈']}
 for cap,terms in patterns.items():
  if cap not in explicit and contains(text,terms):hidden.append(cap)
 transfer=[]
 for cap in explicit+hidden:
  transfer.extend(TRANSFER.get(cap,[]))
 transfer=[x for x in dict.fromkeys(transfer) if x not in explicit and x not in hidden]
 facts={'companies':[s for s in lines(text) if re.search(r'公司|集团|科技|有限',s)][:10],
  'roles':[s for s in lines(text) if re.search(r'岗位|职位|任职|经理|运营|分析师|设计师|工程师',s)][:12],
  'dates':['-'.join(x) for x in DATE_RE.findall(text)],'responsibilities':[e['rawText'] for e in base if e['ownership']!='unknown'][:20],
  'projects':[e['rawText'] for e in base if e['type']=='project'][:12],
  'skills':list(dict.fromkeys(c for e in base for c in e['capabilities'])),'tools':[w for w in ['Excel','SQL','Python','Axure','Figma','JavaScript','Java','API'] if w.lower() in text.lower()],
  'metrics':[m for e in base for m in e['metrics']][:20],'achievements':[e['rawText'] for e in base if e['hasOutcome']][:12],
  'education':[s for s in lines(text) if EDU_RE.search(s)][:6],'ownership':[{'text':e['rawText'],'ownership':e['ownership']} for e in base]}
 return {'factLayer':facts,'resumeFactRegistry':facts,'evidence':all_ev,'explicitSkills':explicit,'hiddenCapabilities':hidden,
  'transferableSkills':transfer,'totalWorkYears':work_years(text),'industries':[x for x in ['电商','教育','金融','文旅','游戏','娱乐','企业服务','互联网','医疗','零售','制造'] if x in text],
  'achievements':facts['achievements'],'responsibilityPatterns':Counter(e['ownership'] for e in base),'projectComplexity':Counter(e['projectComplexity'] for e in base),
  'evidenceStrength':Counter(e['evidenceStrength'] for e in all_ev),'supplements':supplements,
  'reusableSupplements':[x for x in supplements if x.get('reusable',True)]}

def classify(title,body):
 scores={k:sum((3 if w.lower() in title.lower() else 0)+(1 if w.lower() in body.lower() else 0) for w in terms) for k,(_,terms) in FAMILIES.items()}
 if contains(title+body,['ai','aigc','大模型','智能体']) and contains(title+body,['产品','需求','原型']):scores['AI_PRODUCT']+=4
 return max(scores,key=scores.get) if max(scores.values()) else 'OTHER'

def infer_requirements(text):
 candidates=[]
 for s in lines(text):
  if any(g in s for g in GENERIC):continue
  caps=capability_hits(s)
  if not caps:continue
  signal=0
  if re.search(r'核心|必须|负责|主导|独立|能够|要求|职责',s):signal+=2
  if re.search(r'优先|加分|更佳',s):signal-=3
  if re.search(r'熟悉|了解',s):signal-=1
  candidates.append({'text':s[:180],'capabilities':caps,'signal':signal})
 merged={}
 for item in candidates:
  key=item['capabilities'][0]
  if key not in merged or item['signal']>merged[key]['signal']:merged[key]=item
 vals=list(merged.values())
 core=[x for x in vals if x['signal']>=2][:5]
 important=[x for x in vals if x not in core and x['signal']>=0][:5]
 bonus=[x for x in vals if x not in core and x not in important][:4]
 if not core and vals:core=vals[:min(3,len(vals))];important=[x for x in vals if x not in core][:4]
 return core,important,bonus

def parse_jd(text,source='text',url=''):
 ls=lines(text);first=ls[0][:50] if ls else '未命名岗位'
 role=r'(?:产品经理|项目经理|数据分析师|商业分析师|设计师|[前后]端开发工程师|算法工程师|测试工程师|销售经理|运营(?:经理|主管|专员)?|顾问|专员|主管|总监|负责人|研究员|策划|编辑|商务|市场|客服|教师|会计|招聘|人力资源)'
 labelled=next((re.sub(r'^(?:职位名称|岗位名称|招聘职位|职位|岗位)\s*[:：]\s*','',s)[:50] for s in ls[:12] if re.search(r'^(?:职位名称|岗位名称|招聘职位|职位|岗位)\s*[:：]',s)),'')
 title=labelled or first
 if len(title)>36 or re.search('职责|要求|工作内容|截图|招聘信息|职位信息',title) or (not labelled and not re.fullmatch(r'[A-Za-z0-9＋+#· /\-\u4e00-\u9fff]{0,18}'+role+r'(?:[（(][^）)]{1,8}[）)])?',title,re.I)):
  title=next((s[:50] for s in ls[:60] if 2<=len(s)<=28 and re.fullmatch(r'(?:招聘[：:]?)?[A-Za-z0-9＋+#· /\-\u4e00-\u9fff]{0,18}'+role+r'(?:[（(][^）)]{1,8}[）)])?',s,re.I) and not re.search(r'负责|要求|经验|能力|熟悉|具备',s)),'未命名岗位')
 def field(label):
  m=re.search(r'(?:'+label+r')\s*[:：]\s*([^\n；;]{1,55})',text);return m.group(1).strip() if m else ''
 core,important,bonus=infer_requirements(text)
 ym=YEAR_REQ.search(text);edu=EDU_RE.search(text)
 constraints=[]
 for s in ls:
  if re.search(r'必须.*(?:证书|资质|工作许可|签证)|持有.*(?:证书|资质)',s):constraints.append({'text':s[:180],'blocking':True})
  elif re.search(r'\d+\s*年|本科|硕士|行业经验',s):constraints.append({'text':s[:180],'blocking':False})
 mission=next((s for s in ls if re.search(r'负责|目标|使命|工作内容',s)), title)
 profile={'coreMission':mission[:180],'coreRequirements':core,'importantRequirements':important,'bonusRequirements':bonus,
  'constraints':constraints[:5],'successSignals':[s[:180] for s in ls if RESULT_RE.search(s) or re.search(r'目标|结果|提升|增长',s)][:4]}
 body=' '.join(ls)
 company=field('公司(?:名称)?|企业(?:名称)?') or next((s[:60] for s in ls[:60] if 4<=len(s)<=60 and re.search(r'(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|集团)$',s) and s!=title and not re.search(r'负责|要求|经验|能力|岗位',s)),'')
 return {'jobTitle':title,'company':company,'location':field('工作地点|地点|城市'),'salary':field('薪资|薪酬'),
  'jobDescription':text,'sourceType':source,'sourceUrl':url,'jobFamily':classify(title,body),'jdProfile':profile,
  'experienceRequirement':int(ym.group(1)) if ym else None,'educationRequirement':edu.group(0) if edu else None}

def align_requirement(profile,requirement):
 caps=requirement.get('capabilities') or capability_hits(requirement.get('text',''))
 candidates=[]
 for cap in caps:
  direct=[e for e in profile['evidence'] if cap in e['capabilities']]
  if direct:
   best=max(direct,key=lambda e:(ownership_weight(e['ownership'])+.2*e['hasOutcome']))
   candidates.append((evidence_level(best,cap,True),best,cap))
  else:
   sources=[e for e in profile['evidence'] if cap in sum((TRANSFER.get(c,[]) for c in e['capabilities']),[])]
   if sources:
    best=max(sources,key=lambda e:ownership_weight(e['ownership']));candidates.append((evidence_level(best,cap,False),best,cap))
 if not candidates:return {'requirement':requirement.get('text',''),'capability':' / '.join(caps),'status':'none','evidence':'','ownership':'unknown'}
 rank={'strong':4,'medium':3,'transferable':2,'weak':1,'none':0}
 level,best,cap=max(candidates,key=lambda x:rank[x[0]])
 return {'requirement':requirement.get('text',''),'capability':cap,'status':level,'evidence':best['rawText'],'ownership':best['ownership'],'source':best['source']}

def weighted_coverage(items):
 values={'strong':1,'medium':.72,'transferable':.5,'weak':.22,'none':0}
 return sum(values[x['status']] for x in items)/len(items) if items else 0

def match(profile,jd):
 jp=jd['jdProfile'];core=[align_requirement(profile,x) for x in jp['coreRequirements']];important=[align_requirement(profile,x) for x in jp['importantRequirements']];bonus=[align_requirement(profile,x) for x in jp['bonusRequirements']]
 cc,ic,bc=weighted_coverage(core),weighted_coverage(important),weighted_coverage(bonus)
 # A blocking constraint is a risk only when the resume does not contain its concrete
 # credential/permission. Ordinary education, tenure and industry preferences stay non-blocking.
 resume_text=' '.join(e['rawText'] for e in profile['evidence'])+' '+' '.join(profile['resumeFactRegistry']['education'])
 blocking=[]
 for x in jp['constraints']:
  if not x['blocking']:continue
  tokens=[t for t in re.findall(r'[A-Za-z][A-Za-z0-9+.#-]{1,}|[\u4e00-\u9fff]{2,8}',x['text']) if t not in ('必须','持有','具备','证书','资质','工作许可')]
  if not any(t.lower() in resume_text.lower() for t in tokens):blocking.append(x['text'])
 context=1 if not blocking else .2
 score=round(100*(.60*cc+.25*ic+.10*bc+.05*context))
 # Core absence cannot be washed out by bonus matches.
 if core:
  missing=sum(x['status'] in ('none','weak') for x in core)
  if missing>=len(core):score=min(score,39)
  elif missing>=max(1,(len(core)+1)//2):score=min(score,59)
 evidence_strength=sum(x['status'] in ('strong','medium') for x in core+important)/max(1,len(core+important))
 major=[x for x in core if x['status'] in ('none','weak')]
 if blocking:label='存在关键证据缺口'
 elif cc>=.75 and evidence_strength>=.55:label='匹配基础较强'
 elif cc>=.55:label='匹配基础中等'
 elif any(x['status']=='transferable' for x in core):label='有一定迁移空间'
 elif cc<.3:label='当前核心能力重合较少'
 else:label='存在关键证据缺口'
 related_dates=[]
 relevant_caps={x['capability'] for x in core+important if x['status'] in ('strong','medium')}
 for e in profile['evidence']:
  if relevant_caps.intersection(e['capabilities']):related_dates.extend(DATE_RE.findall(e['rawText']))
 readiness={'label':label,'coreCoverage':round(cc*100),'evidenceStrength':round(evidence_strength*100),'constraints':blocking,
  'transferability':sum(x['status']=='transferable' for x in core+important),'majorGaps':[x['capability'] for x in major][:3],'risk':'高' if blocking else '中' if major else '低'}
 strengths=[x for x in core+important if x['status'] in ('strong','medium','transferable')][:4]
 return {'matchScore':score,'applicationReadiness':readiness,'relevantWorkYears':profile['totalWorkYears'] if related_dates else None,'requirementAlignment':{'core':core,'important':important,'bonus':bonus},
  'strengths':strengths,'confidence':'High' if len(core+important)>=3 and len(profile['evidence'])>=4 else 'Medium'}

def career_directions(profile,jds=None):
 caps=set(profile['explicitSkills']+profile['hiddenCapabilities']);rows=[]
 mapping={
  'PRODUCT_OPERATION':{'need':['用户与增长运营','数据驱动决策','跨团队协作'],'gap':'产品实验或完整增长闭环证据'},
  'CONTENT_OPERATION':{'need':['内容策略','数据驱动决策','跨团队协作'],'gap':'稳定的内容结果和复盘证据'},
  'PROJECT_MANAGEMENT':{'need':['项目推进','跨团队协作'],'gap':'独立承担范围、进度和结果的证据'},
  'PRODUCT_MANAGER':{'need':['产品需求分析','数据驱动决策','项目推进','用户研究'],'gap':'从需求到上线的完整产品证据'},
  'AI_PRODUCT':{'need':['AI 应用理解','产品需求分析','项目推进','数据驱动决策'],'gap':'可演示的 AI 产品落地证据'},
  'DATA_ANALYSIS':{'need':['数据驱动决策'],'gap':'SQL/Python 与可复核分析案例'},
  'AI_SOLUTION':{'need':['AI 应用理解','客户与方案','跨团队协作'],'gap':'面向客户的方案落地或交付证据'},
 }
 for key,meta in mapping.items():
  hit=[x for x in meta['need'] if x in caps];ratio=len(hit)/len(meta['need'])
  rows.append({'key':key,'title':FAMILIES[key][0],'ratio':ratio,'evidence':hit[:3],'gap':meta['gap']})
 rows.sort(key=lambda x:x['ratio'],reverse=True)
 close=rows[:min(3,max(2,len([x for x in rows if x['ratio']>=.5])))]
 remaining=[x for x in rows if x not in close]
 adjacent=remaining[:2];bridge=[]
 if close and any(x['key']=='AI_PRODUCT' for x in adjacent+remaining):
  bridge=[{'title':'AI 产品运营','evidence':list(caps & {'内容策略','用户与增长运营','数据驱动决策','跨团队协作'}),'gap':'补一段 AI 功能或工作流落地证据','solves':'先把已有运营与协作能力迁移到 AI 场景，再积累产品闭环。'}]
 explore=remaining[len(adjacent):len(adjacent)+1]
 def present(x,kind):
  ev='、'.join(x.get('evidence') or ['现有经历'])
  return {**x,'kind':kind,'reason':f"已有的{ev}可以作为切入点；目前最大的距离是{x['gap']}。"}
 out={'close':[present(x,'更接近') for x in close[:3]],'adjacent':[present(x,'相邻') for x in adjacent[:2]],'bridge':[present(x,'桥梁岗位') for x in bridge[:2]],'explore':[present(x,'探索') for x in explore[:1]]}
 if out['close'] and out['adjacent']:
  out['comparison']=f"相比直接转向{out['adjacent'][0]['title']}，{out['close'][0]['title']}更容易复用你已有的{('、'.join(out['close'][0].get('evidence',[])[:2]) or '经历')}；前者还需要补足{out['adjacent'][0]['gap']}。"
 return out

def gap_assessment(jobs):
 bycap={}
 for job_index,j in enumerate(jobs):
  for tier in ('core','important','bonus'):
   for x in j['requirementAlignment'][tier]:
    if x['status'] not in ('none','weak'):continue
    cap=x['capability'] or '相关能力';row=bycap.setdefault(cap,{'capability':cap,'core':0,'important':0,'bonus':0,'jobIds':set()});row[tier]+=1;row['jobIds'].add(job_index)
 vals=list(bycap.values())
 for x in vals:
  x['jobs']=len(x.pop('jobIds'))
  x['roi']='值得优先补' if x['core']>=2 or (x['core'] and x['jobs']>=2) else '可以之后补' if x['core'] or x['important'] else '暂时不用花时间'
  x['reason']=f"它出现在 {x['jobs']} 个目标岗位中"+('的核心要求里，补完后更容易形成直接证据。' if x['core'] else '，但当前不是决定核心工作的要求。')
 key=sorted([x for x in vals if x['roi']!='暂时不用花时间'],key=lambda x:(x['core'],x['important'],x['jobs']),reverse=True)[:3]
 ignore=sorted([x for x in vals if x['roi']=='暂时不用花时间' or (not x['core'] and x['jobs']==1)],key=lambda x:x['bonus'],reverse=True)[:2]
 return {'key':key,'ignore':ignore}

def action_plan(gaps,days):
 days=max(3,min(60,int(days or 7)));focus=(gaps.get('key') or [{'capability':'目标岗位核心证据'}])[0]['capability']
 if days<=3:phases=[('界定一个真实问题','文档/白板','一页问题定义与成功标准'),('做出最小验证','原型或轻量代码工具','可演示 Demo'),('整理证据','录屏与 README','问题—行动—结果的项目条目')]
 elif days<=7:phases=[('收窄问题并看 3 个同类方案','文档/搜索','问题定义与竞品笔记'),('写 Mini PRD','文档/原型工具','流程、边界与验收标准'),('完成可演示版本','适合任务的轻量工具','Demo 与基础测试记录'),('包装并复盘','录屏/README','一页案例与简历 bullet 草稿')]
 elif days<=21:phases=[('需求验证','访谈/问卷/竞品','明确用户与可验证指标'),('方案与实现','PRD/原型/开发工具','可运行版本'),('小范围试用','表单/分析表','真实反馈与问题清单'),('迭代与沉淀','版本记录/案例文档','第二版 Demo 与完整案例')]
 else:phases=[('验证真实问题','访谈/竞品/数据表','用户证据与基线指标'),('完成第一版','PRD/原型/开发工具','可运行 Demo 与测试记录'),('组织真实试用','反馈表/数据分析','使用数据与典型反馈'),('完成第二版迭代','版本管理/分析工具','前后对比与改进证据'),('形成求职材料','案例文档/录屏','完整案例、演示和事实安全 bullet')]
 return {'days':days,'focus':focus,'depth':'可演示最小证据' if days<=3 else '完整小案例' if days<=7 else '含反馈的迭代案例' if days<=21 else '含真实试用与数据的完整案例','steps':[{'do':f'围绕“{focus}”{a}','tools':b,'output':c,'evidence':f'形成可在面试中展示的{c}'} for a,b,c in phases]}

def batch_comparison(jobs):
 if len(jobs)<2:return ''
 top=sorted(jobs,key=lambda x:x['matchScore'],reverse=True)
 a,b=top[0],top[1]
 ac=[x['capability'] for x in a['requirementAlignment']['core'] if x['status'] in ('strong','medium')]
 bg=b['applicationReadiness']['majorGaps']
 text=f"{a['jobTitle']}与现有经历重合更多，主要靠{('、'.join(ac[:2]) or '已有直接证据')}；{b['jobTitle']}"
 text+=f"更依赖{('、'.join(bg[:2]) or '另一组能力证据')}，迁移成本相对更高。"
 if len(top)>2:
  c=top[-1];text+=f" {c['jobTitle']}的核心证据覆盖目前最低，主要差距在{('、'.join(c['applicationReadiness']['majorGaps'][:2]) or '直接案例深度')}。"
 return text

def weekly_focus(gaps,jobs):
 out=[]
 if jobs:
  fam=Counter(FAMILIES.get(j['jobFamily'],('其他方向',))[0] for j in jobs).most_common(2)
  out.append('先集中比较'+('和'.join(x[0] for x in fam))+'，用核心工作而不是岗位名做判断。')
 for g in gaps.get('key',[])[:2]:out.append(f"给“{g['capability']}”补一个可展示的小证据，不用同时补所有短板。")
 if gaps.get('ignore'):out.append(f"{gaps['ignore'][0]['capability']}这周先不用花太多时间。")
 return out[:4]

def analyze(resume,jds,supplements=None,days=7):
 profile=parse_resume(resume,supplements);jobs=[];groups={}
 for raw in jds:
  jd_text=raw.get('jobDescription') or raw.get('rawJD','')
  jd=raw if 'coreRequirements' in raw else parse_jd(jd_text,raw.get('sourceType') or raw.get('inputType','text'),raw.get('sourceUrl',''))
  item={**jd,**match(profile,jd)};jobs.append(item);groups.setdefault(jd['jobFamily'],[]).append(item)
 families=[]
 for key,items in groups.items():
  items.sort(key=lambda x:x['matchScore'],reverse=True)
  families.append({'key':key,'name':FAMILIES.get(key,('其他方向',))[0],'familyMatchScore':round(sum(x['matchScore'] for x in items)/len(items)),'jobs':items})
 families.sort(key=lambda x:x['familyMatchScore'],reverse=True)
 gaps=gap_assessment(jobs)
 return {'profile':profile,'families':families,'careerDirections':career_directions(profile,jds),'comparison':batch_comparison(jobs),
  'gaps':gaps,'actionPlan':action_plan(gaps,days),'weeklyFocus':weekly_focus(gaps,jobs)}
