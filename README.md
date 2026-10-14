# 拾线 · 本地线索探索台

一个运行在 Windows 本机的小红书 / 闲鱼搜索工作台。使用 Python 标准库提供本地网页，使用 Playwright 读取闲鱼页面；小红书采集接入独立安装的 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)。

## 功能

- 小红书：关键词搜索、扫码登录、进度显示、帖子库和 JSON 导出。
- 闲鱼：独立登录窗口、登录状态检查、每次 1–10 组关键词搜索、停止任务、按帖子 ID 去重。
- 闲鱼结果：区分疑似需求、疑似广告、待判断和历史已核对；查看原文、打开原帖、筛选与导出。
- 只监听 `127.0.0.1:8765`，数据保存在本机；写操作校验本地来源及会话令牌。

## 安装与启动

要求 Windows、Python 3.11+，以及 Chrome 或 Edge。当前闲鱼启动器查找系统级默认安装路径。

```powershell
git clone https://github.com/WSTPjustdo/crawler-workbench.git
cd crawler-workbench
py -3.11 setup_windows.py
.\open-web.cmd
```

若使用其他已安装的 Python 3.11+，也可以执行 `python setup_windows.py`。

启动后打开 [本地网页](http://127.0.0.1:8765/) 或 [闲鱼需求页](http://127.0.0.1:8765/#xianyu)。

### 启用小红书采集

另需 Git、Node.js。安装上游依赖及 Chromium：

```powershell
py -3.11 setup_windows.py --with-xhs
```

安装脚本将 MediaCrawler 固定在提交 `156c602c8d689266e6c5e9130b36f0b70495f5f0`；已有源码目录不会被覆盖。MediaCrawler 保留其自身许可证，使用前请查看上游 LICENSE。本仓库不包含其源码或浏览器运行时。

### 使用闲鱼

1. 打开“闲鱼需求”，点击“打开登录窗口”。
2. 在独立浏览器窗口登录，再回到网页点击“检查登录”。
3. 输入关键词，点击“开始闲鱼搜索”。
4. 按分类或关键词筛选，查看原帖，导出当前筛选结果。

每组关键词只采集第一页，按平台综合排序，每次最多运行 10 分钟。遇到登录或平台验证会停止并提示手动处理。初筛只看用语，可能误判，不代表全站全部帖子或已确认有效需求。挂牌价不等于预算，历史核对不代表当前仍有效。

## 数据与目录

```text
webapp/                 本地 HTTP 服务和网页
work/*.py               采集入口与辅助脚本
work/mediacrawler-venv/  安装后生成的 Python 环境（不上传）
work/source/            可选的上游源码（不上传）
work/crawl-data/        小红书采集结果（不上传）
work/xianyu-browser-profile/  闲鱼登录状态（不上传）
outputs/xianyu/runs/    闲鱼每次运行结果（不上传）
tests/                  不依赖私人数据的基础测试
```

公开版本不包含作者的采集结果、岗位清单、截图、日志、Cookie、登录状态或本地环境。首次启动结果库为空，这是正常现象。可选的本地 `webapp/static/jobs.json` 用于岗位清单；没有该文件时返回空列表。不要提交登录状态或采集数据。

## 验证

```powershell
python -m unittest discover -s tests -v
```

这些测试使用临时目录和模拟子进程，检查空数据启动、请求边界、关键词限制、去重与任务状态，不访问平台。真实采集仍依赖网络、登录状态和平台页面结构。安装脚本的全新依赖安装与上游版本兼容性需在目标机器上验证。
