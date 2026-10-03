# JobFit · Candidate Intelligence

一份 Master Resume 与 1～10 个 JD 的证据型匹配分析。简历、历史分析和用户确认保存的补充证据保存在当前浏览器本地；服务端不持久化简历，也不调用云端模型。

## 启动

需要 Python 3.10+。普通 PDF 由 PyMuPDF 直接提取文字；没有可用文字层的页面会自动使用本地 RapidOCR，不会上传到云端。

```bash
cd jobfit
python -m pip install -r requirements.txt
$env:PLAYWRIGHT_BROWSERS_PATH=".playwright"  # PowerShell
python -m playwright install chromium
python server.py
```

浏览器打开 `http://127.0.0.1:8765`。可用 `PORT=8766 python server.py` 更改端口。手机和电脑在同一局域网时，可用电脑的局域网 IP 加端口访问；请勿未经访问控制直接公开部署上传接口。

## 输入和配置

- 简历：PDF、DOCX、TXT，最多 8 MB；扫描版 PDF 会自动使用本地 OCR。
- JD 文字：直接粘贴职位信息，至少 35 字。
- JD 截图：可一次选择 1～10 张 PNG、JPG、WEBP 或浏览器可读取的 HEIC/HEIF 连续截图。超长截图会在浏览器内按顺序切片并保留重叠区域，再由本地 RapidOCR 识别；图片不会上传至第三方服务。浏览器无法解码 HEIC/HEIF 时，请使用系统截图或从相册导出 JPG/PNG。
- JD 链接：适配 BOSS 直聘、猎聘、智联招聘、前程无忧、拉勾、看准等公开岗位页，并兼容其他公开 HTML 页面。依次尝试公开 HTML、浏览器渲染和公开 URL 文本读取；备用读取仅发送岗位 URL，不发送简历或个人资料。平台要求登录、验证码、岗位失效或正文不足时会明确提示改用截图或文字，不会编造 JD。

## 分析口径

Resume 同时生成事实层、能力层与事实保护表；每段经历独立记录 Ownership 和 Evidence Strength，并识别有原文依据的隐藏能力、可迁移能力、总年限与相关年限。用户可通过“我其实做过”补充真实证据，选择仅用于当前分析或保存到能力档案，Master Resume 始终不变。

JD 解析为核心使命、Core / Important / Bonus Requirements、约束和成功信号。Evidence Match V1 固定使用 Core 60%、Important 25%、Bonus 10%、Context/Risk 5%，可迁移证据最多按中等匹配处理，Core 缺失不能被 Bonus 抵消。结果页还包含 Career Direction、多 JD 横向比较、Gap ROI、3～60 天行动计划和“这周先做什么”。所有标签只作参考，不替用户决定是否投递。

岗位名与公司名只在标题标签、页面标题或独立的高置信文本行中识别。信息不足时保留“未命名岗位 / 公司未注明”，不会从职责句中猜测。

Job Family 保持连续分组，组内按可靠岗位分数排序；Family Match Score 只使用可靠岗位，并显示已评分数量。相似岗位只使用当前已添加、具有可验证详情 URL 且城市一致的岗位，找不到时不会生成虚构岗位。

当前版本使用可检查的本地语义归一、行为证据和规则降级，**未启用 LLM，也不使用云端服务**。它不会伪造 AI 分析结果；分数用于比较证据覆盖，不代表招聘方录用概率。首次体验建议使用信息完整的中文简历和 JD，并在详情页核对原文证据。

## Render 部署

仓库已包含 `render.yaml`。在 Render 中创建 Blueprint 并连接此仓库即可部署；服务会监听 Render 提供的 `PORT`，健康检查地址为 `/api/health`。生产依赖不包含 Playwright 浏览器，岗位链接读取失败时仍会明确提示改用截图或文字。

Render Free 实例休眠后的首次请求包含服务与 OCR 模型冷启动，可能明显慢于后续请求；OCR 引擎会在同一服务进程内只初始化并复用一次。

简历、JD 与分析记录默认保存在用户当前浏览器的 IndexedDB / localStorage 中。上传文件仅在请求处理期间用于解析，应用本身不建立服务端用户数据库。公开部署仍应避免在不可信设备上传敏感简历。
