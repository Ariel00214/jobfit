import os,json,re,zipfile,io,base64,uuid,threading,time,subprocess,sys
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
from xml.etree import ElementTree as ET
from engine import parse_jd,analyze
from intelligence import analyze as analyze_intelligence
from job_links import read_job, platform_for, normalize_url

ROOT=os.path.dirname(__file__)
_OCR=None
_OCR_LOCK=threading.Lock()
_OCR_RUN_LOCK=threading.Lock()
def memory_stats():
 """Small, content-free cgroup snapshot for diagnosing OCR resource failures."""
 stats={}
 for key,path in (('current','/sys/fs/cgroup/memory.current'),('peak','/sys/fs/cgroup/memory.peak'),('limit','/sys/fs/cgroup/memory.max')):
  try:
   with open(path) as file:value=file.read().strip()
   if value.isdigit():stats[key+'Mb']=round(int(value)/1024/1024,1)
  except OSError:pass
 try:
  with open('/sys/fs/cgroup/memory.events') as file:
   events=dict(line.split() for line in file)
  stats['oomKills']=int(events.get('oom_kill',0))
 except (OSError,ValueError):pass
 return stats
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
def optimize_ocr_image(data):
 """Decode and normalize an OCR part without another lossy JPEG round-trip."""
 from PIL import Image,ImageOps
 import numpy as np
 try:
  image=ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
  if image.width*image.height>80000000:raise ValueError('截图像素过大，请先裁剪后上传。')
  if image.width>2000:
   scale=2000/image.width;image=image.resize((2000,max(1,round(image.height*scale))),Image.Resampling.LANCZOS)
  return np.asarray(image.convert('RGB'))
 except ValueError:raise
 except Exception as exc:raise ValueError('图片格式无法读取，请改用清晰的 JPG 或 PNG 截图。') from exc
def ocr_tiles(data):
 """Bound the pixels and text density passed to each OCR inference."""
 from PIL import Image,ImageOps
 import numpy as np
 try:
  with Image.open(io.BytesIO(data)) as source:
   if source.width*source.height>80000000:raise ValueError('截图像素过大，请先裁剪后上传。')
   orientation=source.getexif().get(274,1)
   image=ImageOps.exif_transpose(source) if orientation!=1 else source
   scale=min(1,1200/image.width)
   source_height=max(1,int(900/scale));overlap=max(1,int(80/scale))
   top=0
   while top<image.height:
    bottom=min(image.height,top+source_height)
    tile=image.crop((0,top,image.width,bottom))
    if scale<1:tile=tile.resize((max(1,round(tile.width*scale)),max(1,round(tile.height*scale))),Image.Resampling.LANCZOS)
    yield np.asarray(tile.convert('RGB'))
    if bottom==image.height:break
    top=bottom-overlap
 except ValueError:raise
 except Exception as exc:raise ValueError('图片格式无法读取，请改用清晰的 JPG 或 PNG 截图。') from exc
def isolated_ocr_tile(prepared):
 """Release OCR's native memory after each tile; never risk the web process."""
 height,width=prepared.shape[:2]
 try:
  result=subprocess.run([sys.executable,os.path.join(ROOT,'ocr_worker.py'),str(width),str(height)],
                        input=prepared.tobytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=45,check=False)
  if result.returncode!=0:
   print(f'[OCR] tile worker exited {result.returncode}: {result.stderr[-500:].decode(errors="replace")}',flush=True)
   raise ValueError('图片识别资源不足，请重试或分开上传截图。')
  return json.loads(result.stdout)['text']
 except subprocess.TimeoutExpired as exc:raise ValueError('图片单片识别超时，请重试或分开上传截图。') from exc
 except (OSError,ValueError,KeyError,UnicodeError) as exc:
  if isinstance(exc,ValueError):raise
  raise ValueError('图片识别暂时失败，请重试。') from exc
def merge_adjacent_ocr(previous,current):
 """Remove only exact line overlap at adjacent slice boundaries."""
 left=[x.strip() for x in previous.splitlines() if x.strip()]
 right=[x.strip() for x in current.splitlines() if x.strip()]
 normal=lambda value:re.sub(r'[\s，。；：、,.!?！？;:\-]+','',value).lower()
 overlap=0
 for size in range(min(12,len(left),len(right)),0,-1):
  if [normal(x) for x in left[-size:]]==[normal(x) for x in right[:size]]:
   overlap=size;break
 return '\n'.join(left+right[overlap:])
def vision(images):
 """Run fully local OCR for ordered slices from one to ten JD screenshots."""
 if not isinstance(images,list) or not 1<=len(images)<=60:raise ValueError('请选择 1～10 张岗位截图。')
 started=time.perf_counter();decode_ms=prepare_ms=run_ms=0;total=0;grouped={};tile_count=0
 try:
  ordered=sorted(enumerate(images),key=lambda pair:(int(pair[1].get('imageIndex',pair[0])),int(pair[1].get('partIndex',0))))
  image_indexes={int(item.get('imageIndex',position)) for position,item in enumerate(images)}
  if len(image_indexes)>10:raise ValueError('请选择 1～10 张岗位截图。')
  for fallback_index,item in ordered:
   image_index=int(item.get('imageIndex',fallback_index));mime=image_mime(item);tick=time.perf_counter()
   try:data=base64.b64decode(item.get('data',''),validate=True)
   except Exception as exc:raise ValueError('图片数据损坏，请重新选择截图。') from exc
   decode_ms+=(time.perf_counter()-tick)*1000
   if mime not in ('image/png','image/jpeg','image/webp'):raise ValueError('截图支持 PNG、JPG、WEBP。')
   if len(data)>12*1024*1024:raise ValueError('单个图片分片不得超过 12 MB。')
   total+=len(data)
   if total>32*1024*1024:raise ValueError('全部截图合计不得超过 32 MB。')
   text='';tick=time.perf_counter()
   for prepared in ocr_tiles(data):
    prepare_ms+=(time.perf_counter()-tick)*1000;tile_count+=1
    tick=time.perf_counter()
    with _OCR_RUN_LOCK:piece=isolated_ocr_tile(prepared).strip()
    run_ms+=(time.perf_counter()-tick)*1000
    del prepared
    if piece:text=merge_adjacent_ocr(text,piece)
    tick=time.perf_counter()
   if text:grouped[image_index]=merge_adjacent_ocr(grouped.get(image_index,''),text)
 except ValueError:raise
 except Exception as exc:raise ValueError('本地 OCR 处理失败，请稍后重试或上传更清晰的截图。') from exc
 content='\n\n'.join('【截图 '+str(index+1)+'】\n'+grouped[index] for index in sorted(grouped))
 total_ms=(time.perf_counter()-started)*1000
 print(f'[OCR] images={len(image_indexes)} parts={len(images)} tiles={tile_count} decode={decode_ms:.0f}ms prepare={prepare_ms:.0f}ms run={run_ms:.0f}ms total={total_ms:.0f}ms',flush=True)
 if len(re.sub(r'\s+','',content))<30:raise ValueError('这张截图没有识别到足够的 JD 文字，请尝试上传更清晰的截图。')
 return content
def recognize_slice(item):
 """OCR one browser-sized slice so long screenshots do not hold one HTTP request."""
 mime=image_mime(item)
 if mime not in ('image/png','image/jpeg','image/webp'):raise ValueError('截图支持 PNG、JPG、WEBP。')
 try:data=base64.b64decode(item.get('data',''),validate=True)
 except Exception as exc:raise ValueError('图片数据损坏，请重新选择截图。') from exc
 if len(data)>12*1024*1024:raise ValueError('单个图片分片不得超过 12 MB。')
 text=''
 for prepared in ocr_tiles(data):
  with _OCR_RUN_LOCK:piece=isolated_ocr_tile(prepared).strip()
  if piece:text=merge_adjacent_ocr(text,piece)
 return text
def combine_ocr_parts(parts):
 if not isinstance(parts,list) or not 1<=len(parts)<=60:raise ValueError('请选择 1～10 张岗位截图。')
 grouped={};indexes=set();received={};expected={}
 for item in sorted(parts,key=lambda p:(int(p.get('imageIndex',0)),int(p.get('partIndex',0)))):
  index=int(item.get('imageIndex',0));part_index=int(item.get('partIndex',0));total_parts=int(item.get('totalParts',1));indexes.add(index)
  if index<0 or index>9 or len(indexes)>10:raise ValueError('请选择 1～10 张岗位截图。')
  if part_index<0 or total_parts<1 or total_parts>60 or part_index>=total_parts:raise ValueError('截图分片顺序不正确，请重新选择截图。')
  if index in expected and expected[index]!=total_parts:raise ValueError('截图分片数量不一致，请重新选择截图。')
  expected[index]=total_parts;received.setdefault(index,set()).add(part_index)
  piece=item.get('text','')
  if not isinstance(piece,str) or len(piece)>12000:raise ValueError('截图文字格式不正确。')
  if not piece.strip():raise ValueError('存在未识别成功的截图分片，JD 内容不完整，请重试。')
  grouped[index]=merge_adjacent_ocr(grouped.get(index,''),piece)
 for index in indexes:
  if received[index]!=set(range(expected[index])):raise ValueError('截图分片缺失，JD 内容不完整，请重试。')
 content='\n\n'.join('【截图 '+str(index+1)+'】\n'+grouped[index] for index in sorted(grouped))
 if len(re.sub(r'\s+','',content))<30:raise ValueError('这张截图没有识别到足够的 JD 文字，请尝试上传更清晰的截图。')
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
  try:
   raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  except (BrokenPipeError,ConnectionResetError):pass  # User stopped waiting or closed the page.
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/health':return self.send(200,{'status':'ok',**(memory_stats() if 'stats=1' in self.path else {})})
  if path=='/api/config':return self.send(200,{'visionConfigured':True,'visionMode':'local-ocr','maxJdImages':10})
  if path=='/':path='/index.html'
  if path not in ('/index.html','/app.js','/style.css'):return self.send(404,{'error':'Not found'})
  with open(os.path.join(ROOT,'static',path[1:]),'rb') as f:data=f.read()
  self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[path.rsplit('.',1)[1]]);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length>45*1024*1024:raise ValueError('上传内容过大。')
   body=json.loads(self.rfile.read(length))
   if self.path=='/api/parse-resume':
    data=base64.b64decode(body['data']);text=read_file(body['name'],data)
    if len(text.strip())<40:raise ValueError('简历没有提取到足够文字，请使用文字版文件。')
    return self.send(200,{'text':text})
   if self.path=='/api/ocr-slice':
    return self.send(200,{'text':recognize_slice(body.get('image') or {})})
   if self.path=='/api/parse-jd':
    source=body.get('source')
    source_url=body.get('url') or body.get('sourceUrl','')
    if source=='url':
     reading=read_job(source_url)
     if reading.get('needsSupplement'):return self.send(200,reading)
     content=reading['content'];source_url=reading['sourceUrl']
    elif source=='image':
     if source_url:
      try:source_url=normalize_url(source_url)
      except ValueError:source_url=''
     images=body.get('images') or [{'data':body.get('data',''),'mime':body.get('mime','')}]
     content=combine_ocr_parts(body['ocrParts']) if 'ocrParts' in body else vision(images)
    elif source=='text':
     content=body.get('text','')
     if source_url:
      try:source_url=normalize_url(source_url)
      except ValueError:source_url=''
    else:raise ValueError('请选择 JD 输入方式。')
    if len(content.strip())<35:raise ValueError('JD 内容不足，请补充岗位职责和任职要求。')
    jd_id=body.get('jdId') or uuid.uuid4().hex
    source_names=[]
    for image in body.get('images',[]):
     name=image.get('originalName') or image.get('name','截图')
     if name not in source_names:source_names.append(name)
    metadata={'jdId':jd_id,'sourceUrl':source_url,'sourcePlatform':platform_for(source_url) or ('岗位截图' if source=='image' else '手动 JD'),'sourceImage':source_names}
    return self.send(200,{'readStatus':'success','method':reading.get('method') if source=='url' else source,'jd':parse_jd(content,source,source_url,metadata)})
   if self.path=='/api/analyze':
    resume=body.get('resume','');jds=body.get('jds',[])
    if len(resume.strip())<40:raise ValueError('请先上传简历。')
    if not 1<=len(jds)<=10:raise ValueError('请添加 1～10 个岗位 JD。')
    return self.send(200,full_analysis(resume,jds,body.get('supplements',[]),body.get('days',7)))
   return self.send(404,{'error':'Not found'})
  except ValueError as e:return self.send(400,{'error':str(e)})
  except Exception as e:return self.send(500,{'error':'处理失败，请检查文件或重试。'})
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765'));print(f'JobFit http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
