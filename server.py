import os,json,re,zipfile,io,html,ipaddress,socket,urllib.request,urllib.parse,urllib.error,base64,uuid,threading
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
from xml.etree import ElementTree as ET
from engine import parse_jd,analyze
from intelligence import analyze as analyze_intelligence

ROOT=os.path.dirname(__file__)
_OCR=None
_OCR_LOCK=threading.Lock()
_OCR_RUN_LOCK=threading.Lock()
FALLBACK='该岗位链接暂时无法自动读取；如平台要求登录、验证码或已下架，请上传岗位截图或粘贴 JD 文字。'
JOB_PLATFORMS={
 'zhipin.com':'BOSS直聘','liepin.com':'猎聘','zhaopin.com':'智联招聘',
 '51job.com':'前程无忧','lagou.com':'拉勾','kanzhun.com':'看准',
}
def platform_for(url):
 host=urllib.parse.urlparse(url or '').hostname or ''
 return next((name for domain,name in JOB_PLATFORMS.items() if host==domain or host.endswith('.'+domain)),'招聘平台' if url else '')
class HTMLText(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','nav','footer','header'):self.skip+=1
  if tag in ('p','div','li','h1','h2','h3','br'):self.parts.append('\n')
 def handle_endtag(self,tag):
  if tag in ('script','style','nav','footer','header'):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.parts.append(data)
def extract_job_payload(source):
 """Recover visible job fields stored in SSR/JSON blobs used by job platforms."""
 if not source:return ''
 parts=[]
 title=re.search(r'<title[^>]*>(.*?)</title>',source,re.I|re.S)
 if title:
  value=html.unescape(re.sub('<[^>]+>',' ',title.group(1))).strip()
  if value:parts.append('页面标题：'+value[:160])
 keys={
  '职位名称':('jobName','jobTitle','positionName','positionTitle','postName'),
  '公司名称':('companyName','brandName','companyShortName','corpName'),
  '工作地点':('cityName','workCity','jobArea','areaName','businessDistrict'),
  '岗位内容':('jobDescription','description','postDescription','jobDetail','positionDescription','jobSecText'),
 }
 for label,names in keys.items():
  values=[]
  for name in names:
   pattern=r'["\']'+re.escape(name)+r'["\']\s*:\s*["\']((?:\\.|[^"\']){2,12000})["\']'
   for match in re.finditer(pattern,source,re.I):
    raw=match.group(1)
    try:value=json.loads('"'+raw.replace('"','\\"').replace('\\"','"')+'"')
    except Exception:
     try:value=bytes(raw,'utf-8').decode('unicode_escape')
     except Exception:value=raw
    value=html.unescape(re.sub(r'<[^>]+>','\n',str(value)))
    value=re.sub(r'\\[nrt]|[\r\t]+','\n',value);value=re.sub(r'\n\s*\n+','\n',value).strip()
    if value and value not in values:values.append(value)
  if values:parts.append(label+'：'+values[0][:12000])
 return '\n'.join(parts)
def read_file(name,data):
 name=name.lower()
 if len(data)>8*1024*1024:raise ValueError('文件不得超过 8 MB。')
 if name.endswith('.txt'):return data.decode('utf-8-sig',errors='replace')
 if name.endswith('.docx'):
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   root=ET.fromstring(z.read('word/document.xml'))
   return '\n'.join(''.join(n.itertext()) for n in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
 if name.endswith('.pdf'):
  return read_pdf(data)
 raise ValueError('简历仅支持 PDF、DOCX、TXT。')

def _ocr_lines(result):
 """Normalize RapidOCR 1.x/2.x/3.x results into plain text lines."""
 if result is None:return []
 if hasattr(result,'txts'):return [str(x) for x in result.txts if str(x).strip()]
 if isinstance(result,tuple):result=result[0]
 lines=[]
 for item in result or []:
  if isinstance(item,(list,tuple)) and len(item)>1:
   value=item[1]
   if isinstance(value,(list,tuple)):value=value[0] if value else ''
   if str(value).strip():lines.append(str(value))
 return lines

def read_pdf(data):
 """Extract text with PyMuPDF; OCR only pages that lack a usable text layer."""
 try:
  import pymupdf
  doc=pymupdf.open(stream=data,filetype='pdf')
 except Exception as exc:
  raise ValueError('PDF 读取失败，请确认文件未损坏或加密。') from exc
 if doc.needs_pass:
  doc.close();raise ValueError('PDF 已加密，请先移除密码后再上传。')
 pages=[];ocr=None
 try:
  for page in doc:
   text=page.get_text('text',sort=True).strip()
   # A page number or watermark alone is not a usable text layer.
   if len(re.sub(r'\s+','',text))<20:
    try:
     if ocr is None:ocr=ocr_engine()
     pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
     text='\n'.join(_ocr_lines(ocr(pix.tobytes('png')))).strip()
    except Exception as exc:
     raise ValueError('扫描版 PDF 的本地 OCR 失败，请检查 rapidocr/onnxruntime 依赖。') from exc
   if text:pages.append(text)
 finally:doc.close()
 return '\n\n'.join(pages)
def safe_url(url):
 u=urllib.parse.urlparse(url)
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError(FALLBACK)
 for a in socket.getaddrinfo(u.hostname,None,type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(a[4][0]).is_global:raise ValueError(FALLBACK)
 return url
class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):safe_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
def read_url_browser(url):
 """Render JavaScript-heavy public job pages in a local headless browser."""
 os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',os.path.join(ROOT,'.playwright'))
 from playwright.sync_api import sync_playwright
 checked={}
 def route_request(route):
  target=route.request.url
  try:
   parsed=urllib.parse.urlparse(target)
   if parsed.scheme not in ('http','https'):return route.abort()
   host=parsed.hostname or ''
   if host not in checked:checked[host]=bool(safe_url(target))
   return route.continue_()
  except Exception:return route.abort()
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  context=browser.new_context(locale='zh-CN',user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36')
  page=context.new_page();page.route('**/*',route_request)
  try:
   page.goto(url,wait_until='domcontentloaded',timeout=20000)
   page.wait_for_timeout(2500)
   safe_url(page.url)
   return page.content()
  finally:browser.close()
def _read_url_direct(url):
 try:
  import requests
  current=safe_url(url);response=None
  headers={
   'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36',
   'Accept':'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
   'Accept-Language':'zh-CN,zh;q=0.9,en;q=0.5','Referer':'https://www.baidu.com/',
  }
  # Follow redirects ourselves so every destination still passes the SSRF check.
  for _ in range(6):
   response=requests.get(current,headers=headers,timeout=(5,12),allow_redirects=False,stream=True)
   if response.is_redirect or response.is_permanent_redirect:
    current=safe_url(urllib.parse.urljoin(current,response.headers.get('Location','')));response.close();continue
   break
  if response is None or response.status_code!=200:raise ValueError(FALLBACK)
  if 'text/html' not in response.headers.get('Content-Type',''):raise ValueError(FALLBACK)
  raw=response.raw.read(2*1024*1024+1,decode_content=True);response.close()
  if len(raw)>2*1024*1024:raise ValueError(FALLBACK)
  response.encoding=response.encoding or response.apparent_encoding or 'utf-8'
  source=raw.decode(response.encoding,errors='replace')
  structured=[]
  for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',source,re.I|re.S):
   try:
    obj=json.loads(html.unescape(block));nodes=obj if isinstance(obj,list) else [obj]
    for node in nodes:
     if isinstance(node,dict) and (node.get('@type')=='JobPosting' or 'job' in str(node.get('@type','')).lower()):
      title=node.get('title','');company=(node.get('hiringOrganization') or {}).get('name','') if isinstance(node.get('hiringOrganization'),dict) else ''
      location=node.get('jobLocation','');location=json.dumps(location,ensure_ascii=False) if not isinstance(location,str) else location
      description=html.unescape(re.sub('<[^>]+>','\n',str(node.get('description',''))))
      structured.extend([f'职位名称：{title}' if title else '',f'公司名称：{company}' if company else '',f'工作地点：{location}' if location else '',description])
   except Exception:pass
  structured_text=extract_job_payload(source);parser=HTMLText();parser.feed(source)
  text=html.unescape(''.join(parser.parts))
  text=re.sub(r'[ \t\u00a0]+',' ',text);text=re.sub(r'\n\s*\n+','\n',text).strip()
  if any(structured):text='\n'.join(x for x in structured if x)+'\n'+text
  if structured_text:text=structured_text+'\n'+text
  blocked=re.search(r'安全验证|访问验证|滑动验证|验证码|Security Verification|请登录后',text,re.I)
  has_job_terms=re.search(r'职位(?:描述|介绍|要求)|岗位(?:职责|要求)|任职要求|工作职责|responsibilit|requirement',text,re.I)
  if blocked or len(text)<100 or not has_job_terms:
   source=read_url_browser(current)
   structured_text=extract_job_payload(source);parser=HTMLText();parser.feed(source)
   text=html.unescape(''.join(parser.parts))
   text=re.sub(r'[ \t\u00a0]+',' ',text);text=re.sub(r'\n\s*\n+','\n',text).strip()
   if structured_text:text=structured_text+'\n'+text
   blocked=re.search(r'安全验证|访问验证|滑动验证|验证码|Security Verification|请登录后',text,re.I)
   has_job_terms=re.search(r'职位(?:描述|介绍|要求)|岗位(?:职责|要求)|任职要求|工作职责|responsibilit|requirement',text,re.I)
   if blocked or len(text)<100 or not has_job_terms:raise ValueError(FALLBACK)
  platform=platform_for(current)
  # Popular Chinese job pages encode useful identity fields in their document title.
  prefix=[]
  title_match=re.search(r'【(?:[^【】\s]+\s+)?(.+?)招聘】',text[:500])
  if title_match:prefix.append('职位名称：'+title_match.group(1).strip())
  company_match=re.search(r'】[-_－—]([^\n_-]{2,50}?)(?:招聘信息)?[-_－—]',text[:500])
  if company_match:prefix.append('公司名称：'+company_match.group(1).strip())
  prefix.append('来源平台：'+platform)
  return ('\n'.join(prefix)+'\n'+text)[:30000]
 except ValueError:raise
 except Exception as exc:raise ValueError(FALLBACK) from exc
def read_url_reader(url):
 """Last-resort reader for a public job URL; never sends resume or user profile data."""
 import requests
 original=urllib.parse.urlparse(url);host=(original.hostname or '').lower()
 if original.scheme not in ('http','https') or not any(host==d or host.endswith('.'+d) for d in JOB_PLATFORMS):raise ValueError(FALLBACK)
 reader='https://r.jina.ai/http://'+original.netloc+original.path
 if original.query:reader+='?'+original.query
 try:
  response=requests.get(reader,headers={'Accept':'text/plain','User-Agent':'JobFit/3.0'},timeout=(5,25))
  if response.status_code!=200:raise ValueError(FALLBACK)
  response.encoding='utf-8';text=response.text.strip();prefix=[]
  title_line=re.search(r'^Title:\s*(.+)$',text,re.M)
  if title_line:
   page_title=title_line.group(1).strip();prefix.append('页面标题：'+page_title)
   company_match=re.search(r'_([^_\-—|]{2,60}?)招聘(?:信息)?(?:\s*[-—|]|$)',page_title)
   if company_match:prefix.append('公司名称：'+company_match.group(1).strip())
  if prefix:text='\n'.join(prefix)+'\n'+text
  if len(text)<100 or not re.search(r'职位描述|职位介绍|岗位职责|任职要求|工作职责|responsibilit|requirement',text,re.I):raise ValueError(FALLBACK)
  return text[:30000]
 except ValueError:raise
 except Exception as exc:raise ValueError(FALLBACK) from exc
def read_url(url):
 try:return _read_url_direct(url)
 except ValueError:return read_url_reader(url)
def image_mime(item):
 mime=str(item.get('mime') or '').lower().strip()
 if mime=='image/jpg':mime='image/jpeg'
 if not mime:
  ext=os.path.splitext(str(item.get('name') or ''))[1].lower()
  mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}.get(ext,'')
 return mime
def ocr_engine():
 global _OCR
 if _OCR is None:
  with _OCR_LOCK:
   if _OCR is None:
    from rapidocr import RapidOCR
    _OCR=RapidOCR(params={'Global.use_cls':False,'Global.log_level':'error','EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1})
 return _OCR
def optimize_ocr_image(data,max_pixels=600000):
 from PIL import Image,ImageOps
 try:
  image=ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
  if image.width*image.height>40000000:raise ValueError('截图像素过大，请先裁剪后上传。')
  scale=min(1,(max_pixels/max(1,image.width*image.height))**.5)
  if scale<1:image=image.resize((max(1,int(image.width*scale)),max(1,int(image.height*scale))),Image.Resampling.LANCZOS)
  image=image.convert('RGB');stream=io.BytesIO();image.save(stream,'JPEG',quality=88,optimize=True)
  return stream.getvalue()
 except ValueError:raise
 except Exception as exc:raise ValueError('图片格式无法读取，请改用清晰的 JPG 或 PNG 截图。') from exc
def vision(images):
 """Run fully local OCR for one or more JD screenshots."""
 if not isinstance(images,list) or not 1<=len(images)<=10:raise ValueError('请选择 1～10 张岗位截图。')
 total=0;parts=[]
 try:
  ocr=ocr_engine()
  for index,item in enumerate(images,1):
   mime=image_mime(item);data=base64.b64decode(item.get('data',''),validate=True)
   if mime not in ('image/png','image/jpeg','image/webp'):raise ValueError('截图支持 PNG、JPG、WEBP。')
   if len(data)>8*1024*1024:raise ValueError('每张截图不得超过 8 MB。')
   total+=len(data)
   if total>24*1024*1024:raise ValueError('全部截图合计不得超过 24 MB。')
   optimized=optimize_ocr_image(data)
   with _OCR_RUN_LOCK:text='\n'.join(_ocr_lines(ocr(optimized))).strip()
   if text:parts.append('【截图 '+str(index)+'】\n'+text)
 except ValueError:raise
 except Exception as exc:raise ValueError('本地 OCR 识别失败，请确认截图清晰完整。') from exc
 content='\n\n'.join(parts)
 if len(content.strip())<30:raise ValueError('截图中没有识别到足够文字，请上传更清晰的截图。')
 return content

def full_analysis(resume,jds,supplements=None,days=7):
 legacy=analyze(resume,jds);intel=analyze_intelligence(resume,jds,supplements or [],days)
 advanced_jobs={j.get('jobDescription',''):j for f in intel['families'] for j in f['jobs']}
 for family in legacy['families']:
  for job in family['jobs']:
   extra=advanced_jobs.get(job.get('jobDescription') or job.get('rawJD',''))
   if extra:
    job['evidenceMatch']=extra;job['matchScore']=extra['matchScore']
    rows=[]
    labels={'strong':'强证据','medium':'中等证据','transferable':'可迁移','weak':'较弱','none':'暂无'}
    for tier,weight in (('core',60),('important',25),('bonus',10)):
     aligned=extra.get('requirementAlignment',{}).get(tier,[])
     for item in aligned:
      rows.append({'requirement':item.get('requirement',''),'requirementMeaning':item.get('requirement',''),'judgmentLabel':labels.get(item.get('status'),'暂无'),'evidence':item.get('evidence',''),'reason':f"{tier} 要求，按真实证据状态计入匹配参考。",'contribution':round(weight/max(1,len(aligned))*{'strong':1,'medium':.72,'transferable':.5,'weak':.22,'none':0}.get(item.get('status'),0),1)})
    job['matchBreakdown']=rows
  family['jobs'].sort(key=lambda x:x.get('matchScore',0),reverse=True)
  family['familyMatchScore']=round(sum(x.get('matchScore',0) for x in family['jobs'])/max(1,len(family['jobs'])))
 legacy['families'].sort(key=lambda x:x.get('familyMatchScore',0),reverse=True)
 legacy.update({k:intel[k] for k in ('careerDirections','comparison','gaps','actionPlan','weeklyFocus')});legacy['candidateProfile']=intel['profile'];return legacy
class Handler(BaseHTTPRequestHandler):
 def send(self,status,obj):
  raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/health':return self.send(200,{'status':'ok'})
  if path=='/api/config':return self.send(200,{'visionConfigured':True,'visionMode':'local-ocr','maxJdImages':10})
  if path=='/':path='/index.html'
  if path not in ('/index.html','/app.js','/style.css'):return self.send(404,{'error':'Not found'})
  with open(os.path.join(ROOT,'static',path[1:]),'rb') as f:data=f.read()
  self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[path.rsplit('.',1)[1]]);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length>36*1024*1024:raise ValueError('上传内容过大。')
   body=json.loads(self.rfile.read(length))
   if self.path=='/api/parse-resume':
    data=base64.b64decode(body['data']);text=read_file(body['name'],data)
    if len(text.strip())<40:raise ValueError('简历没有提取到足够文字，请使用文字版文件。')
    return self.send(200,{'text':text})
   if self.path=='/api/parse-jd':
    source=body.get('source')
    source_url=body.get('url') or body.get('sourceUrl','')
    if source=='url':
     try:content=read_url(source_url)
     except ValueError as exc:return self.send(200,{'needsSupplement':True,'sourceUrl':source_url,'sourcePlatform':platform_for(source_url),'message':str(exc)})
    elif source=='image':
     images=body.get('images') or [{'data':body.get('data',''),'mime':body.get('mime','')}]
     content=vision(images)
    elif source=='text':content=body.get('text','')
    else:raise ValueError('请选择 JD 输入方式。')
    if len(content.strip())<35:raise ValueError('JD 内容不足，请补充岗位职责和任职要求。')
    jd_id=body.get('jdId') or uuid.uuid4().hex
    metadata={'jdId':jd_id,'sourceUrl':source_url,'sourcePlatform':platform_for(source_url) or ('岗位截图' if source=='image' else '手动 JD'),'sourceImage':[x.get('name','截图') for x in body.get('images',[])]}
    return self.send(200,{'jd':parse_jd(content,source,source_url,metadata)})
   if self.path=='/api/analyze':
    resume=body.get('resume','');jds=body.get('jds',[])
    if len(resume.strip())<40:raise ValueError('请先上传简历。')
    if not 1<=len(jds)<=10:raise ValueError('请添加 1～10 个岗位 JD。')
    return self.send(200,full_analysis(resume,jds,body.get('supplements',[]),body.get('days',7)))
   return self.send(404,{'error':'Not found'})
  except ValueError as e:return self.send(400,{'error':str(e)})
  except Exception as e:return self.send(500,{'error':'处理失败，请检查文件或重试。'})
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765'));ocr_engine();print(f'JobFit http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
