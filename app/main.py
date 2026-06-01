from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.ai_service import get_ai_provider
from app.executors import ExecutorError, ExecutorRegistry
from app.models import (
    AiAnalysisRequest,
    AiAnalysisResult,
    ApprovalLog,
    ApprovalRequest,
    CalcExecution,
    CalcInputRef,
    CalcNode,
    CalcResult,
    CalcStep,
    ComparisonGroup,
    ComparisonItem,
    GlobalParam,
    Project,
    ProjectFeedback,
    ProjectItem,
    ProjectParam,
)
from app.schemas import (
    AiAnalysisCreate,
    AiAnalysisRequestOut,
    AiAnalysisResultOut,
    ApprovalAction,
    ApprovalCreate,
    ApprovalLogOut,
    ApprovalRequestOut,
    CalcInputRefCreate,
    CalcInputRefOut,
    CalcNodeCreate,
    CalcNodeMove,
    CalcNodeOut,
    CalcNodeUpdate,
    CalcStepCreate,
    CalcStepOut,
    CalcStepUpdate,
    CalcModuleTemplateInstall,
    ComparisonGroupCreate,
    ComparisonGroupOut,
    ComparisonItemCreate,
    ComparisonItemOut,
    ExecutionOut,
    GlobalParamOut,
    LoginRequest,
    ParamCreate,
    ParamUpdate,
    ProjectCreate,
    ProjectFeedbackCreate,
    ProjectFeedbackOut,
    ProjectItemCreate,
    ProjectItemOut,
    ProjectParamOut,
    ProjectOut,
    ProjectUpdate,
    ProjectWorkspaceOut,
    ResultOut,
    RunNodeRequest,
    RunTreeRequest,
)
from app.walking_beam_level2_offline import DEFAULT_CASE as STEP_FURNACE_DEFAULT_CASE
from app.walking_beam_level2_offline import run as run_step_furnace_offline_model


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    yield


app = FastAPI(title="Calc Platform API", version="0.1.0", lifespan=lifespan)

ALLOWED_STEP_LANGUAGES = {"python", "csharp"}
executor_registry = ExecutorRegistry()
ai_provider = get_ai_provider()

FURNACE_MODULE_GROUPS = [
    "加热曲线",
    "水梁计算",
    "排烟计算",
    "传热计算",
    "蓄热计算",
    "空气管道",
    "换热器",
    "煤气管道",
    "多工况",
]

MENU_ICON_ASSETS = {
    "步进炉计算": "/assets/e007f0e1-image-1.png",
    "辊底炉计算": "/assets/fca7ed82-image-1.png",
    "环形炉计算": "/assets/98e27005-image-1.png",
    "反馈填报": "/assets/475b82b7-1666b628f0ec254626fbd2f5cd074f75-1.png",
    "计算数据分析": "/assets/1680ffb1-image-1.png",
    "反馈数据分析": "/assets/475b82b7-1666b628f0ec254626fbd2f5cd074f75-1.png",
}

STEP_FURNACE_OFFLINE_ARTIFACT = str(Path(__file__).with_name("walking_beam_level2_offline.py"))
DEFAULT_DIRECT_RUN_PROJECT_NAME = "步进炉默认测试项目"
DEFAULT_DIRECT_RUN_ITEM_NAME = "步进炉默认测试名目"
DEFAULT_DIRECT_RUN_ITEM_CODE = "STEP-FURNACE-DEFAULT"


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "approval_requests" not in table_names:
        return
    column_names = {column["name"] for column in inspector.get_columns("approval_requests")}
    if "total_stages" in column_names:
        pass
    else:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE approval_requests ADD COLUMN total_stages INTEGER NOT NULL DEFAULT 1"
            )
    if "project_feedback" not in table_names:
        ProjectFeedback.__table__.create(bind=engine, checkfirst=True)
    else:
        feedback_column_names = {column["name"] for column in inspector.get_columns("project_feedback")}
        with engine.begin() as connection:
            if "project_item_id" not in feedback_column_names:
                connection.exec_driver_sql(
                    "ALTER TABLE project_feedback ADD COLUMN project_item_id INTEGER"
                )
            if "node_id" not in feedback_column_names:
                connection.exec_driver_sql(
                    "ALTER TABLE project_feedback ADD COLUMN node_id INTEGER"
                )


def resolve_menu_icon(label: str) -> str:
    return MENU_ICON_ASSETS.get(label, "/assets/1680ffb1-image-1.png")


def render_icon_button(title: str, subtitle: str, icon_url: str, action: str, data_group: str = "") -> str:
    group_attr = f' data-group="{data_group}"' if data_group else ""
    return (
        f'<button class="icon-button" type="button" onclick="{action}" draggable="true"{group_attr}>'
        f'<img src="{icon_url}" alt="{title}" class="icon-thumb" />'
        f'<span class="icon-title">{title}</span>'
        f'<span class="icon-subtitle">{subtitle}</span>'
        "</button>"
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _login_page_html()


@app.post("/login")
def login(payload: LoginRequest) -> dict[str, str]:
    if payload.username == "admin" and payload.password == "admin123":
        return {"status": "ok", "redirect": "/home"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")


@app.get("/home", response_class=HTMLResponse)
def home_page() -> str:
    return _home_page_html()


@app.get("/assets/{asset_name}")
def get_asset(asset_name: str) -> FileResponse:
    asset_map = {
        "475b82b7-1666b628f0ec254626fbd2f5cd074f75-1.png": "/workspace/.monkeycode-tmp-files/475b82b7-1666b628f0ec254626fbd2f5cd074f75-1.png",
        "e007f0e1-image-1.png": "/workspace/.monkeycode-tmp-files/e007f0e1-image-1.png",
        "fca7ed82-image-1.png": "/workspace/.monkeycode-tmp-files/fca7ed82-image-1.png",
        "98e27005-image-1.png": "/workspace/.monkeycode-tmp-files/98e27005-image-1.png",
        "1680ffb1-image-1.png": "/workspace/.monkeycode-tmp-files/1680ffb1-image-1.png",
    }
    file_path = asset_map.get(asset_name)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return FileResponse(file_path)


def _login_page_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>系统登录</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #09111f;
        --panel: rgba(15, 23, 42, 0.9);
        --panel-soft: rgba(15, 23, 42, 0.65);
        --text: #eef2ff;
        --muted: #94a3b8;
        --accent: #60a5fa;
        --line: rgba(148, 163, 184, 0.18);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
        background:
          radial-gradient(circle at top left, rgba(96, 165, 250, 0.15), transparent 28%),
          radial-gradient(circle at top right, rgba(34, 197, 94, 0.12), transparent 24%),
          linear-gradient(180deg, #08101e 0%, #101a31 100%);
        color: var(--text);
      }
      .wrap {
        max-width: 1100px;
        margin: 0 auto;
        padding: 32px 20px 80px;
      }
      .hero {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 28px;
      }
      h1 { margin: 0 0 10px; font-size: 38px; }
      p { margin: 0; color: var(--muted); line-height: 1.7; }
      .shell {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .login-card {
        width: min(460px, calc(100vw - 32px));
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 30px;
        box-shadow: 0 30px 80px rgba(0, 0, 0, 0.28);
      }
      .field { display: grid; gap: 6px; margin-top: 16px; }
      .input { width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line); background: rgba(2, 8, 23, 0.45); color: var(--text); }
      .btn {
        display: inline-block;
        padding: 12px 16px;
        border-radius: 12px;
        text-decoration: none;
        font-weight: bold;
      }
      .btn-primary { background: var(--accent); color: #081225; }
      button.btn { width: 100%; border: 0; cursor: pointer; margin-top: 20px; }
      .hint { margin-top: 14px; color: var(--muted); font-size: 13px; }
      .error { margin-top: 12px; color: #fca5a5; min-height: 20px; }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="login-card">
        <h1>工业热工计算系统</h1>
        <p>登录成功后进入主功能菜单首页。</p>
        <form onsubmit="handleLogin(event)">
          <div class="field">
            <label for="username">账号</label>
            <input id="username" class="input" name="username" placeholder="请输入账号" required />
          </div>
          <div class="field">
            <label for="password">密码</label>
            <input id="password" class="input" name="password" type="password" placeholder="请输入密码" required />
          </div>
          <button class="btn btn-primary" type="submit">登录系统</button>
          <div id="login-error" class="error"></div>
          <div class="hint">演示账号：`admin`，演示密码：`admin123`</div>
        </form>
      </section>
    </main>
    <script>
      async function handleLogin(event) {
        event.preventDefault();
        const form = event.target;
        const errorEl = document.getElementById('login-error');
        errorEl.textContent = '';
        const payload = {
          username: form.elements.namedItem('username').value.trim(),
          password: form.elements.namedItem('password').value,
        };
        const res = await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (res.ok) {
          const data = await res.json();
          window.location.href = data.redirect;
          return;
        }
        const data = await res.json().catch(() => ({ detail: '登录失败' }));
        errorEl.textContent = data.detail || '登录失败';
      }
    </script>
  </body>
</html>
"""


def _home_page_html() -> str:
    compute_cards = "".join(
        [
            render_icon_button("步进炉计算", "进入步进炉子模块", resolve_menu_icon("步进炉计算"), "openModulePanel('step-furnace')", "compute"),
            render_icon_button("辊底炉计算", "进入辊底炉子模块", resolve_menu_icon("辊底炉计算"), "openModulePanel('roller-hearth')", "compute"),
            render_icon_button("环形炉计算", "进入环形炉子模块", resolve_menu_icon("环形炉计算"), "openModulePanel('ring-furnace')", "compute"),
        ]
    )
    analysis_cards = "".join(
        [
            render_icon_button("计算数据分析", "计算结果复盘、对标、图表解析", resolve_menu_icon("计算数据分析"), "openAnalysisPanel('calc-analysis')", "analysis"),
            render_icon_button("反馈数据分析", "反馈汇总、故障统计、生产波动分析", resolve_menu_icon("反馈数据分析"), "openAnalysisPanel('feedback-analysis')", "analysis"),
        ]
    )
    feedback_cards = "".join(
        [
            render_icon_button("反馈填报", "现场工况填报、生产异常上报、实际运行参数提交", resolve_menu_icon("反馈填报"), "window.location.href='/feedback'", "feedback"),
        ]
    )
    admin_cards = "".join(
        [
            render_icon_button("用户权限管理", "预留代码挂载位", resolve_menu_icon("计算数据分析"), "showPlaceholder('用户权限管理')", "admin"),
            render_icon_button("炉型配置管理", "炉型与模块绑定", resolve_menu_icon("步进炉计算"), "showPlaceholder('炉型配置管理')", "admin"),
            render_icon_button("计算模块绑定配置", "菜单模块联动配置", resolve_menu_icon("辊底炉计算"), "showPlaceholder('计算模块绑定配置')", "admin"),
            render_icon_button("日志管理", "系统日志与执行日志", resolve_menu_icon("环形炉计算"), "showPlaceholder('日志管理')", "admin"),
        ]
    )
    step_furnace_children = "".join(
        [
            render_icon_button("二级计算离线模型", "直接进入梁式步进炉二级离线模型工作台", resolve_menu_icon("步进炉计算"), "openLevel2StepFurnaceModel()"),
            render_icon_button("加热曲线计算", "预留代码挂载位", resolve_menu_icon("步进炉计算"), "showPlaceholder('加热曲线计算')"),
            render_icon_button("换热器校核", "预留代码挂载位", resolve_menu_icon("步进炉计算"), "showPlaceholder('换热器校核')"),
            render_icon_button("热平衡核算", "预留代码挂载位", resolve_menu_icon("步进炉计算"), "showPlaceholder('热平衡核算')"),
            render_icon_button("烟道阻力计算", "预留代码挂载位", resolve_menu_icon("步进炉计算"), "showPlaceholder('烟道阻力计算')"),
        ]
    )
    roller_children = "".join(
        [
            render_icon_button("加热曲线计算", "预留代码挂载位", resolve_menu_icon("辊底炉计算"), "showPlaceholder('辊底炉加热曲线计算')"),
            render_icon_button("换热器校核", "预留代码挂载位", resolve_menu_icon("辊底炉计算"), "showPlaceholder('辊底炉换热器校核')"),
            render_icon_button("热平衡核算", "预留代码挂载位", resolve_menu_icon("辊底炉计算"), "showPlaceholder('辊底炉热平衡核算')"),
        ]
    )
    ring_children = "".join(
        [
            render_icon_button("加热曲线计算", "预留代码挂载位", resolve_menu_icon("环形炉计算"), "showPlaceholder('环形炉加热曲线计算')"),
            render_icon_button("换热器校核", "预留代码挂载位", resolve_menu_icon("环形炉计算"), "showPlaceholder('环形炉换热器校核')"),
            render_icon_button("热平衡核算", "预留代码挂载位", resolve_menu_icon("环形炉计算"), "showPlaceholder('环形炉热平衡核算')"),
        ]
    )
    return f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>主功能菜单首页</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #08101e;
        --panel: rgba(15, 23, 42, 0.92);
        --panel-soft: rgba(15, 23, 42, 0.72);
        --line: rgba(148, 163, 184, 0.18);
        --text: #eef2ff;
        --muted: #94a3b8;
        --accent: #60a5fa;
        --accent-2: #22c55e;
        --warn: #f59e0b;
      }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #08101e 0%, #101a31 100%); color: var(--text); }}
      .wrap {{ max-width: 1440px; margin: 0 auto; padding: 24px 20px 48px; }}
      .hero, .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; }}
      .hero {{ padding: 24px; }}
      .topbar {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }}
      .nav-tabs {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }}
      .nav-tab {{ border: 1px solid var(--line); background: var(--panel-soft); color: var(--text); border-radius: 16px; padding: 14px 16px; font-size: 16px; font-weight: bold; cursor: pointer; }}
      .nav-tab.active {{ background: rgba(96, 165, 250, 0.18); border-color: rgba(96, 165, 250, 0.45); }}
      .content-grid {{ display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 18px; margin-top: 18px; }}
      .panel {{ padding: 20px; }}
      .section-label {{ margin: 0 0 10px; color: var(--accent); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }}
      .icon-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; }}
      .icon-button {{ display: grid; gap: 8px; align-content: start; justify-items: center; border: 1px solid var(--line); border-radius: 18px; padding: 16px 12px; background: rgba(2, 8, 23, 0.28); color: var(--text); cursor: grab; min-height: 190px; }}
      .icon-button.dragging {{ opacity: 0.55; }}
      .icon-thumb {{ width: 72px; height: 72px; object-fit: cover; border-radius: 18px; border: 1px solid var(--line); background: rgba(255,255,255,0.04); }}
      .icon-title {{ font-weight: bold; text-align: center; }}
      .icon-subtitle {{ color: var(--muted); font-size: 12px; text-align: center; line-height: 1.5; }}
      .module-panel {{ display: none; }}
      .module-panel.active {{ display: block; }}
      .module-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 14px; }}
      .placeholder {{ border: 1px dashed rgba(96, 165, 250, 0.42); border-radius: 18px; padding: 18px; background: rgba(2, 8, 23, 0.2); color: var(--muted); margin-top: 18px; }}
      .quick-links {{ display: grid; gap: 12px; }}
      .quick-link {{ display: block; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--line); color: var(--text); text-decoration: none; background: rgba(2, 8, 23, 0.24); }}
      .row {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
      .chip {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }}
      .small {{ font-size: 12px; color: var(--muted); }}
      .hidden {{ display: none; }}
      .btn {{ display: inline-block; padding: 10px 14px; border-radius: 12px; text-decoration: none; font-weight: bold; border: 1px solid var(--line); color: var(--text); background: transparent; cursor: pointer; }}
      .btn-primary {{ background: var(--accent); color: #081225; border-color: transparent; }}
      @media (max-width: 1080px) {{ .content-grid {{ grid-template-columns: 1fr; }} .nav-tabs {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
      @media (max-width: 720px) {{ .nav-tabs {{ grid-template-columns: 1fr; }} }}
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero">
        <div class="topbar">
          <div>
            <h1 style="margin:0 0 8px;">主功能菜单首页</h1>
            <div class="small">四级结构：登录 -> 首页主菜单 -> 大模块 -> 子功能图标按钮</div>
          </div>
          <div class="row">
            <a class="btn" href="/compute">进入现有计算台</a>
            <a class="btn" href="/feedback">进入反馈台</a>
            <a class="btn" href="/analysis">进入现有分析台</a>
          </div>
        </div>
        <div class="nav-tabs">
          <button class="nav-tab active" type="button" data-tab="compute" onclick="showTopTab('compute')">计算</button>
          <button class="nav-tab" type="button" data-tab="analysis" onclick="showTopTab('analysis')">分析</button>
          <button class="nav-tab" type="button" data-tab="feedback" onclick="showTopTab('feedback')">反馈</button>
          <button class="nav-tab" type="button" data-tab="admin" onclick="showTopTab('admin')">后台管理</button>
        </div>
      </section>

      <section class="content-grid">
        <aside class="panel">
          <div class="section-label">一级菜单导航</div>
          <div class="quick-links">
            <a class="quick-link" href="#" onclick="showTopTab('compute'); return false;">计算模块</a>
            <a class="quick-link" href="#" onclick="showTopTab('analysis'); return false;">分析模块</a>
            <a class="quick-link" href="#" onclick="showTopTab('feedback'); return false;">反馈模块</a>
            <a class="quick-link" href="#" onclick="showTopTab('admin'); return false;">后台管理</a>
          </div>
          <div class="placeholder">
            <div class="section-label">配置规则</div>
            <div>炉型配置只录入炉型名称。</div>
            <div>后台管理负责炉型与可用计算模块绑定。</div>
            <div>分析统一集中在分析菜单内调用 AI。</div>
            <div>反馈菜单只负责现场数据填报和异常上报。</div>
            <div>所有子功能按钮都保留代码挂载位置。</div>
          </div>
        </aside>

        <section class="panel">
          <div id="top-tab-compute" class="top-tab-panel">
            <div class="section-label">计算</div>
            <div class="row"><span class="chip">一级菜单</span><span class="chip">二级炉型入口</span><span class="chip">三级图标按钮</span><span class="chip">四级子功能面板</span></div>
            <div class="icon-grid" id="compute-top-grid">{compute_cards}</div>
            <div id="module-step-furnace" class="module-panel active" style="margin-top:18px;">
              <div class="section-label">步进炉下级功能按钮</div>
              <div class="small" style="margin: 8px 0 14px;">当前缺省打开计算模块，首个计算节点固定为二级计算离线模型。</div>
              <div class="module-grid" data-draggable-grid="step-furnace">{step_furnace_children}</div>
              <div class="placeholder" id="placeholder-step-furnace">当前模块仅搭建 UI 框架，后续在此区域挂接步进炉计算程序代码。</div>
            </div>
            <div id="module-roller-hearth" class="module-panel" style="margin-top:18px;">
              <div class="section-label">辊底炉下级功能按钮</div>
              <div class="module-grid" data-draggable-grid="roller-hearth">{roller_children}</div>
              <div class="placeholder">当前模块仅搭建 UI 框架，后续在此区域挂接辊底炉计算程序代码。</div>
            </div>
            <div id="module-ring-furnace" class="module-panel" style="margin-top:18px;">
              <div class="section-label">环形炉下级功能按钮</div>
              <div class="module-grid" data-draggable-grid="ring-furnace">{ring_children}</div>
              <div class="placeholder">当前模块仅搭建 UI 框架，后续在此区域挂接环形炉计算程序代码。</div>
            </div>
          </div>

          <div id="top-tab-analysis" class="top-tab-panel hidden">
            <div class="section-label">分析</div>
            <div class="icon-grid" data-draggable-grid="analysis">{analysis_cards}</div>
            <div id="analysis-panel-calc-analysis" class="module-panel active" style="margin-top:18px;">
              <div class="section-label">计算数据分析</div>
              <div class="module-grid" data-draggable-grid="calc-analysis">
                {render_icon_button("结果复盘", "预留代码挂载位", resolve_menu_icon("计算数据分析"), "showPlaceholder('结果复盘')")}
                {render_icon_button("对标分析", "预留代码挂载位", resolve_menu_icon("计算数据分析"), "showPlaceholder('对标分析')")}
                {render_icon_button("图表解析", "预留代码挂载位", resolve_menu_icon("计算数据分析"), "showPlaceholder('图表解析')")}
                {render_icon_button("AI 智能分析", "能耗、炉温异常、优化建议", resolve_menu_icon("计算数据分析"), "showPlaceholder('计算数据 AI 智能分析')")}
              </div>
              <div class="placeholder">计算结果统一在这里做复盘、对标和 AI 智能解析。</div>
            </div>
            <div id="analysis-panel-feedback-analysis" class="module-panel" style="margin-top:18px;">
              <div class="section-label">反馈数据分析</div>
              <div class="module-grid" data-draggable-grid="feedback-analysis">
                {render_icon_button("工况汇总", "预留代码挂载位", resolve_menu_icon("反馈数据分析"), "showPlaceholder('工况汇总')")}
                {render_icon_button("故障统计", "预留代码挂载位", resolve_menu_icon("反馈数据分析"), "showPlaceholder('故障统计')")}
                {render_icon_button("生产波动分析", "预留代码挂载位", resolve_menu_icon("反馈数据分析"), "showPlaceholder('生产波动分析')")}
                {render_icon_button("AI 汇总分析", "问题汇总与异常判断", resolve_menu_icon("反馈数据分析"), "showPlaceholder('反馈数据 AI 汇总分析')")}
              </div>
              <div class="placeholder">现场反馈入库后统一在这里做统计、归类和 AI 汇总分析。</div>
            </div>
          </div>

          <div id="top-tab-feedback" class="top-tab-panel hidden">
            <div class="section-label">反馈</div>
            <div class="icon-grid" data-draggable-grid="feedback">{feedback_cards}</div>
            <div class="placeholder">反馈菜单统一负责现场人员工况填报、生产异常上报和实际运行参数提交，数据入库后供分析菜单统一调用。</div>
          </div>

          <div id="top-tab-admin" class="top-tab-panel hidden">
            <div class="section-label">后台管理</div>
            <div class="icon-grid" data-draggable-grid="admin">{admin_cards}</div>
            <div class="placeholder">后台管理包含用户权限管理、炉型配置管理、计算模块绑定配置、日志管理。炉型与模块联动在此菜单继续扩展。</div>
          </div>
        </section>
      </section>
    </main>

    <script>
      let draggedButton = null;
      function showTopTab(tabName) {{
        document.querySelectorAll('.top-tab-panel').forEach((panel) => panel.classList.add('hidden'));
        document.querySelectorAll('.nav-tab').forEach((tab) => tab.classList.remove('active'));
        document.getElementById(`top-tab-${{tabName}}`).classList.remove('hidden');
        document.querySelector(`.nav-tab[data-tab="${{tabName}}"]`).classList.add('active');
      }}

      function openModulePanel(panelName) {{
        document.querySelectorAll('#top-tab-compute .module-panel').forEach((panel) => panel.classList.remove('active'));
        document.getElementById(`module-${{panelName}}`).classList.add('active');
        showTopTab('compute');
      }}

      function openLevel2StepFurnaceModel() {{
        window.location.href = '/step-furnace-level2';
      }}

      function openAnalysisPanel(panelName) {{
        document.querySelectorAll('#top-tab-analysis .module-panel').forEach((panel) => panel.classList.remove('active'));
        document.getElementById(`analysis-panel-${{panelName}}`).classList.add('active');
        showTopTab('analysis');
      }}

      function showPlaceholder(label) {{
        const currentPanel = document.querySelector('.top-tab-panel:not(.hidden) .placeholder');
        if (currentPanel) {{
          currentPanel.textContent = `${{label}} 已保留代码挂载位置，后续可直接嵌入对应程序代码。`;
        }}
      }}

      function enableDragLayout() {{
        document.querySelectorAll('.icon-button').forEach((button) => {{
          button.addEventListener('dragstart', () => {{ draggedButton = button; button.classList.add('dragging'); }});
          button.addEventListener('dragend', () => {{ button.classList.remove('dragging'); draggedButton = null; }});
        }});
        document.querySelectorAll('[data-draggable-grid], #compute-top-grid').forEach((grid) => {{
          grid.addEventListener('dragover', (event) => {{
            event.preventDefault();
            const afterElement = [...grid.querySelectorAll('.icon-button:not(.dragging)')].find((candidate) => event.clientX <= candidate.getBoundingClientRect().left + candidate.offsetWidth / 2);
            if (!draggedButton) return;
            if (afterElement) {{
              grid.insertBefore(draggedButton, afterElement);
            }} else {{
              grid.appendChild(draggedButton);
            }}
          }});
        }});
      }}

      enableDragLayout();
      showTopTab('compute');
      openModulePanel('step-furnace');
    </script>
  </body>
</html>
"""


@app.get("/compute", response_class=HTMLResponse)
def compute_page() -> str:
    return _compute_page_html()


@app.get("/step-furnace-level2", response_class=HTMLResponse)
def step_furnace_level2_page() -> str:
    return _step_furnace_level2_page_html()


@app.post("/api/run")
def run_step_furnace_level2(payload: dict) -> dict:
    mode = str(payload.get("mode", "optimize"))
    model_payload = {
        "billet": payload.get("billet") or {},
        "process": payload.get("process") or {},
        "zones": payload.get("zones") or STEP_FURNACE_DEFAULT_CASE["zones"],
    }
    result = run_step_furnace_offline_model(
        {
            "model_payload": model_payload,
            "run_options": {"mode": mode},
            "node_metadata": {
                "furnace_type": "梁式步进炉",
                "model_level": "二级",
                "model_mode": "offline",
            },
        }
    )
    if result.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result)
    return result


@app.get("/entry", response_class=HTMLResponse)
def entry_page() -> str:
    return _feedback_page_html()


@app.get("/feedback", response_class=HTMLResponse)
def feedback_page() -> str:
    return _feedback_page_html()


def _step_furnace_level2_page_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>梁式步进炉二级离线模型</title>
    <style>
      :root { color-scheme: light; --bg: #08101e; --panel: rgba(15, 23, 42, 0.92); --panel-soft: rgba(2, 8, 23, 0.36); --text: #eef2ff; --muted: #94a3b8; --accent: #60a5fa; --accent-2: #22c55e; --line: rgba(148, 163, 184, 0.2); --danger: #ef4444; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #08101e 0%, #101a31 100%); color: var(--text); }
      .wrap { max-width: 1440px; margin: 0 auto; padding: 24px 20px 80px; }
      .hero, .card, .info-card { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; }
      .hero { padding: 24px; }
      h1, h2, h3 { margin-top: 0; }
      p, .muted { color: var(--muted); }
      .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
      .btn { display: inline-block; padding: 12px 16px; border-radius: 12px; text-decoration: none; font-weight: bold; border: 1px solid var(--line); color: var(--text); background: transparent; cursor: pointer; }
      .btn-primary { background: var(--accent); color: #081225; border-color: transparent; }
      .info-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 18px; }
      .info-card, .card { padding: 18px; }
      .section-label { margin: 0 0 10px; color: var(--accent); font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; }
      .workbench { display: grid; grid-template-columns: minmax(360px, 0.92fr) minmax(0, 1.08fr); gap: 18px; margin-top: 18px; align-items: start; }
      .stack { display: grid; gap: 18px; }
      .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
      .field { display: grid; gap: 6px; }
      label { color: #cbd5e1; font-size: 13px; }
      .input { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(2, 8, 23, 0.5); color: var(--text); }
      .result-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
      .metric { border: 1px solid var(--line); border-radius: 16px; padding: 14px; background: var(--panel-soft); min-height: 86px; }
      .metric-title { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
      .metric-value { font-size: 20px; font-weight: bold; word-break: break-word; }
      .process-list { display: grid; gap: 10px; }
      .process-item { border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; background: rgba(2, 8, 23, 0.24); }
      .code { white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 12px; color: #cbd5e1; background: rgba(2, 8, 23, 0.36); border: 1px solid var(--line); border-radius: 14px; padding: 12px; }
      .ok { color: var(--accent-2); }
      .danger { color: var(--danger); }
      @media (max-width: 1100px) { .workbench, .info-grid { grid-template-columns: 1fr; } }
      @media (max-width: 720px) { .form-grid, .result-grid { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero">
        <h1>梁式步进炉二级离线模型</h1>
        <p>左侧编辑工艺输入 JSON，右侧查看离线仿真或优化结果。</p>
        <div class="actions"><a class="btn" href="/home">返回主菜单</a><a class="btn" href="/compute">计算台</a><button class="btn btn-primary" onclick="runModel()">开始计算</button></div>
        <div class="info-grid">
          <div class="info-card"><div class="section-label">程序入口</div><strong>walking_beam_level2_offline.py</strong></div>
          <div class="info-card"><div class="section-label">服务接口</div><strong>POST /api/run</strong></div>
        </div>
      </section>

      <section class="workbench">
        <aside class="stack">
          <article class="card">
            <div class="section-label">输入参数</div>
            <h2>钢坯参数</h2>
            <div class="form-grid">
              <div class="field"><label>钢坯宽度 m</label><input class="input" id="width_m" type="number" step="0.01" value="0.15" /></div>
              <div class="field"><label>钢坯厚度 m</label><input class="input" id="thickness_m" type="number" step="0.01" value="0.15" /></div>
              <div class="field"><label>钢坯长度 m</label><input class="input" id="length_m" type="number" step="0.1" value="6" /></div>
              <div class="field"><label>密度 kg/m3</label><input class="input" id="density" type="number" step="1" value="7850" /></div>
              <div class="field"><label>比热 J/(kg*K)</label><input class="input" id="specific_heat" type="number" step="1" value="690" /></div>
              <div class="field"><label>导热系数 W/(m*K)</label><input class="input" id="conductivity" type="number" step="1" value="34" /></div>
              <div class="field"><label>黑度</label><input class="input" id="emissivity" type="number" step="0.01" value="0.82" /></div>
              <div class="field"><label>入炉温度 C</label><input class="input" id="entry_temp_c" type="number" step="1" value="30" /></div>
              <div class="field"><label>目标出炉温度 C</label><input class="input" id="target_exit_temp_c" type="number" step="1" value="1180" /></div>
              <div class="field"><label>最大表里温差 C</label><input class="input" id="max_core_surface_delta_c" type="number" step="1" value="30" /></div>
              <div class="field"><label>最大升温速率 C/min</label><input class="input" id="max_rise_rate_c_per_min" type="number" step="1" value="18" /></div>
            </div>
          </article>
          <article class="card">
            <h2>步进参数</h2>
            <div class="form-grid">
              <div class="field"><label>步距 m</label><input class="input" id="step_length_m" type="number" step="0.1" value="0.5" /></div>
              <div class="field"><label>步进周期 s</label><input class="input" id="step_cycle_s" type="number" step="1" value="45" /></div>
            </div>
          </article>
          <article class="card">
            <h2>炉温分区</h2>
            <div class="form-grid">
              <div class="field"><label>预热段设定 C</label><input class="input" id="zone_0_temp" type="number" step="1" value="870" /></div>
              <div class="field"><label>加热一段设定 C</label><input class="input" id="zone_1_temp" type="number" step="1" value="1130" /></div>
              <div class="field"><label>加热二段设定 C</label><input class="input" id="zone_2_temp" type="number" step="1" value="1310" /></div>
              <div class="field"><label>均热段设定 C</label><input class="input" id="zone_3_temp" type="number" step="1" value="1300" /></div>
            </div>
          </article>
        </aside>

        <section class="stack">
          <article class="card">
            <div class="section-label">计算结果</div>
            <h2>最终结果</h2>
            <div id="run-message" class="muted">页面打开后已准备默认工况，点击“开始计算”获取结果。</div>
            <div class="result-grid" id="result-grid" style="margin-top:14px;"></div>
          </article>
          <article class="card">
            <h2>计算过程</h2>
            <div id="process-panel" class="process-list"><div class="muted">暂无计算过程。</div></div>
          </article>
          <article class="card">
            <h2>输入 JSON</h2>
            <div class="code" id="input-json"></div>
          </article>
        </section>
      </section>
    </main>
    <script>
      const zoneNames = ['预热段', '加热一段', '加热二段', '均热段'];
      const zoneLengths = [8, 8, 9, 7];
      const zoneHtc = [115, 150, 175, 145];
      function num(id) { return Number(document.getElementById(id).value || 0); }
      function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
      function buildPayload() {
        return {
          mode: 'optimize',
          billet: {
            width_m: num('width_m'), thickness_m: num('thickness_m'), length_m: num('length_m'), density: num('density'),
            specific_heat: num('specific_heat'), conductivity: num('conductivity'), emissivity: num('emissivity')
          },
          process: {
            entry_temp_c: num('entry_temp_c'), target_exit_temp_c: num('target_exit_temp_c'), max_core_surface_delta_c: num('max_core_surface_delta_c'),
            max_rise_rate_c_per_min: num('max_rise_rate_c_per_min'), step_length_m: num('step_length_m'), step_cycle_s: num('step_cycle_s')
          },
          zones: zoneNames.map((name, index) => ({ name, length_m: zoneLengths[index], furnace_temp_c: num(`zone_${index}_temp`), heat_transfer_coeff: zoneHtc[index] }))
        };
      }
      function renderInputJson() { document.getElementById('input-json').textContent = JSON.stringify(buildPayload(), null, 2); }
      function renderMetric(title, value) { return `<div class="metric"><div class="metric-title">${escapeHtml(title)}</div><div class="metric-value">${escapeHtml(value)}</div></div>`; }
      function renderResults(outputs) {
        const temps = outputs.exit_temperatures || {};
        const setpoints = Object.values(outputs.optimized_setpoints_c || {}).join(' / ');
        document.getElementById('result-grid').innerHTML = [
          renderMetric('模式', outputs.operation_mode === 'optimize' ? '离线优化' : '离线仿真'),
          renderMetric('综合目标值', outputs.objective_value),
          renderMetric('出炉平均温度', `${temps.average_temp_c} C`),
          renderMetric('目标偏差', `${outputs.target_deviation_c} C`),
          renderMetric('表面温度', `${temps.surface_temp_c} C`),
          renderMetric('心部温度', `${temps.core_temp_c} C`),
          renderMetric('表里温差', `${outputs.core_surface_delta_c} C`),
          renderMetric('最大升温速率', `${outputs.max_rise_rate_c_per_min} C/min`),
          renderMetric('炉温设定值', setpoints),
          renderMetric('能耗代理项', outputs.energy_proxy),
          renderMetric('氧化烧损代理项', outputs.oxidation_proxy),
          renderMetric('温升曲线偏差项', Math.round(Math.abs(outputs.target_deviation_c || 0) * 1315.34 * 100) / 100)
        ].join('');
        document.getElementById('process-panel').innerHTML = (outputs.zone_results || []).map((zone) => `<div class="process-item"><strong>${escapeHtml(zone.zone_name)}</strong><div class="muted">停留时间: ${escapeHtml(zone.residence_time_s)} s | 炉温: ${escapeHtml(zone.furnace_setpoint_c)} C</div><div class="muted">出口表面: ${escapeHtml(zone.surface_temp_c)} C | 心部: ${escapeHtml(zone.core_temp_c)} C | 平均: ${escapeHtml(zone.average_temp_c)} C</div></div>`).join('');
      }
      async function runModel() {
        renderInputJson();
        const message = document.getElementById('run-message');
        message.className = 'muted';
        message.textContent = '正在执行梁式步进炉二级离线模型...';
        const res = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildPayload()) });
        if (!res.ok) { message.className = 'danger'; message.textContent = `计算失败: ${res.status}`; return; }
        const data = await res.json();
        renderResults(data.outputs || {});
        message.className = 'ok';
        message.textContent = `计算完成，已调用 ${data.outputs.file_name}`;
      }
      document.querySelectorAll('.input').forEach((input) => input.addEventListener('input', renderInputJson));
      renderInputJson();
      runModel();
    </script>
  </body>
</html>
"""


def _compute_page_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>计算平台计算台</title>
    <style>
      :root { color-scheme: light; --bg: #09111f; --panel: rgba(15, 23, 42, 0.9); --text: #eef2ff; --muted: #94a3b8; --accent: #60a5fa; --accent-2: #22c55e; --line: rgba(148, 163, 184, 0.18); --danger: #ef4444; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #08101e 0%, #101a31 100%); color: var(--text); }
      .wrap { max-width: 1280px; margin: 0 auto; padding: 24px 20px 80px; }
      .hero, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; }
      .hero { padding: 24px; }
      .page-grid { display: grid; grid-template-columns: 380px minmax(0, 1fr); gap: 18px; margin-top: 20px; }
      .stack { display: grid; gap: 18px; }
      .result-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
      .card { padding: 20px; }
      .section-label { margin: 0 0 12px; color: var(--accent); font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; }
      h1, h2 { margin-top: 0; }
      p, .muted { color: var(--muted); }
      .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
      .btn { display: inline-block; padding: 12px 16px; border-radius: 12px; text-decoration: none; font-weight: bold; }
      .btn-primary { background: var(--accent); color: #081225; }
      .btn-secondary { border: 1px solid var(--line); color: var(--text); }
      button.btn { cursor: pointer; }
      .field { display: grid; gap: 6px; margin-top: 12px; }
      .input, .select { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(2, 8, 23, 0.45); color: var(--text); }
      .item { border: 1px solid var(--line); background: rgba(2, 8, 23, 0.22); border-radius: 14px; padding: 12px 14px; }
      .list { display: grid; gap: 10px; margin-top: 12px; }
      .empty { color: var(--muted); font-size: 14px; padding: 8px 0; }
      .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--line); margin-top: 6px; }
      .group-node { border-color: rgba(96, 165, 250, 0.55); background: rgba(30, 41, 59, 0.78); }
      .group-pill { color: #fbbf24; border-color: rgba(251, 191, 36, 0.4); }
      .ok { color: var(--accent-2); }
      .danger { color: var(--danger); }
      .code { white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 12px; color: #cbd5e1; }
      .report-link { margin-top: 10px; display: inline-flex; }
      @media (max-width: 960px) { .page-grid, .result-grid { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero">
        <h1>计算平台计算台</h1>
        <p>左侧只负责执行，右侧只负责结构、执行记录和结果查看。</p>
        <div class="actions"><a class="btn btn-secondary" href="/home">返回主菜单</a><a class="btn btn-secondary" href="/feedback">前往反馈台</a><a class="btn btn-secondary" href="/analysis">前往分析台</a></div>
      </section>
      <section class="page-grid">
        <aside class="stack">
          <article class="card"><div class="section-label">二级离线模型测试区</div><h2>步进炉二级离线模型</h2><div id="context-panel" class="list"><div class="item"><strong>当前正在准备项目与名目</strong><div class="muted">点击步进炉下级功能按钮后，页面会自动补充缺省条目并拉起二级离线模型模块。</div></div></div><div class="actions"><button class="btn btn-primary" onclick="runPreferredOfflineNode()">开始计算</button><button class="btn btn-secondary" onclick="loadComputeData()">刷新</button></div><div id="compute-message" class="empty"></div></article>
          <article class="card"><div class="section-label">挂靠状态区</div><h2>二级离线模型挂靠</h2><div id="binding-panel" class="list"><div class="item"><strong>当前未选择计算节点</strong><div class="muted">安装步进炉模块组后，选择“步进炉二级计算离线模型”可查看真实文件挂靠状态。</div></div></div></article>
          <article class="card"><div class="section-label">模块组安装区</div><h2>计算模块组</h2><div class="muted">页面会自动安装步进炉计算分组，并把二级计算离线模型放在第一个计算节点。</div><div class="list"><div class="item group-node"><strong>步进炉</strong><div class="muted">安装后会生成模块分组树</div></div><div class="item"><strong>二级计算离线模型</strong><div class="muted">挂在步进炉分组下，作为第一个计算节点并支持直接执行</div></div><div class="item"><strong>功能分组</strong><div class="muted">加热曲线、水梁计算、排烟计算、传热计算、蓄热计算、空气管道、换热器、煤气管道、多工况</div></div></div></article>
          <article class="card"><div class="section-label">树结构区</div><h2>当前树节点</h2><div id="compute-tree" class="empty">选择项目和名目后加载</div></article>
        </aside>
        <section class="stack">
          <article class="card"><div class="section-label">执行说明区</div><div class="list"><div class="item"><strong>准备阶段</strong><div class="muted">点击步进炉下级功能按钮后，系统会自动补充缺省项目和缺省名目，并准备二级离线模型模块。</div></div><div class="item"><strong>人工确认</strong><div class="muted">页面准备完成后，由人工点击“开始计算”按钮触发实际计算。</div></div></div></article>
          <section class="result-grid"><article class="card"><div class="section-label">执行记录区</div><h2>最近执行</h2><div id="execution-panel" class="empty">执行后显示摘要</div></article><article class="card"><div class="section-label">结果查看区</div><h2>执行结果</h2><div id="result-panel" class="empty">执行后显示节点结果</div></article></section>
        </section>
      </section>
    </main>
    <script>
      let currentProjectId = null;
      let currentItemId = null;
      function renderContextPanel(content) { document.getElementById('context-panel').innerHTML = content; }
      function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
      async function fetchJson(url, options = {}) { const res = await fetch(url, options); if (!res.ok) { let detail = `${url} -> ${res.status}`; try { const data = await res.json(); if (data?.detail) { detail = `${detail} ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`; } } catch (error) {} throw new Error(detail); } return res.status === 204 ? null : res.json(); }
      function setMessage(text, tone = 'empty') { const el = document.getElementById('compute-message'); el.className = tone; el.textContent = text; }
      function renderBindingPanel(content) { document.getElementById('binding-panel').innerHTML = content; }
      async function ensureDefaultProjectAndItem() { let projects = await fetchJson('/projects'); let project = projects[0] || null; if (!project) { project = await fetchJson('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: '步进炉默认测试项目', owner_user_id: 'direct-button', status: 'draft' }) }); } const items = await fetchJson(`/projects/${project.id}/items`); let item = items[0] || null; if (!item) { item = await fetchJson(`/projects/${project.id}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: '步进炉默认测试名目', code: 'STEP-FURNACE-DEFAULT', description: '点击二级离线模型计算时自动补充的缺省名目' }) }); } return { project, item }; }
      async function loadProjects() { const projects = await fetchJson('/projects'); if (!projects.length) { document.getElementById('compute-tree').innerHTML = '<div class="empty">当前还没有项目与树结构</div>'; document.getElementById('execution-panel').innerHTML = '<div class="empty">暂无执行记录</div>'; document.getElementById('result-panel').innerHTML = '<div class="empty">暂无执行结果</div>'; renderContextPanel('<div class="item"><strong>当前还没有项目</strong><div class="muted">点击二级离线模型后，系统会自动补充缺省项目和缺省名目，并等待人工开始计算。</div></div>'); renderBindingPanel('<div class="item"><strong>当前没有挂靠信息</strong><div class="muted">点击二级离线模型后，系统会自动补全条目并挂靠模型。</div></div>'); return; } currentProjectId = Number(projects[0].id); renderContextPanel(`<div class="item"><strong>当前项目</strong><div class="muted">${escapeHtml(projects[0].name)} (#${projects[0].id})</div></div>`); await loadItems(currentProjectId); }
      async function loadItems(projectId) { const items = await fetchJson(`/projects/${projectId}/items`); if (!items.length) { currentItemId = null; document.getElementById('compute-tree').innerHTML = '<div class="empty">当前项目还没有名目与树结构</div>'; renderContextPanel(`<div class="item"><strong>当前项目</strong><div class="muted">项目 #${projectId}</div></div><div class="item"><strong>当前没有名目</strong><div class="muted">点击二级离线模型后，系统会自动补充缺省名目，并等待人工开始计算。</div></div>`); renderBindingPanel('<div class="item"><strong>当前项目未挂靠二级离线模型</strong><div class="muted">点击二级离线模型后，系统会自动补全条目并挂靠模型。</div></div>'); return; } currentItemId = Number(items[0].id); renderContextPanel(`<div class="item"><strong>当前项目</strong><div class="muted">项目 #${projectId}</div></div><div class="item"><strong>当前名目</strong><div class="muted">${escapeHtml(items[0].name)} (#${items[0].id})</div></div>`); await loadTree(projectId, currentItemId); }
      async function loadSelectedStepBinding(nodes) { const selectedNode = nodes.find((node) => node.name === '步进炉二级计算离线模型') || nodes[0] || null; if (!selectedNode || !selectedNode.calc_step_id) { renderBindingPanel('<div class="item"><strong>当前未挂靠真实模型文件</strong><div class="muted">页面会优先查找步进炉二级计算离线模型，并显示实际绑定的 Python 文件。</div></div>'); return; } const step = await fetchJson(`/calc-steps/${selectedNode.calc_step_id}`); const artifactPath = step.artifact_path || '未配置'; const scriptState = step.script_content ? '内联脚本' : '文件挂靠'; const mountedFile = artifactPath.split('/').pop(); renderBindingPanel(`<div class="item group-node"><strong>${escapeHtml(selectedNode.name)}</strong><div class="muted">步骤 ID: ${step.id} | 类型: ${escapeHtml(step.step_type)}</div><div class="muted">挂靠方式: ${escapeHtml(scriptState)}</div><div class="muted">真实文件: ${escapeHtml(mountedFile)}</div><div class="code">${escapeHtml(artifactPath)}</div></div>`); }
      async function loadTree(projectId, itemId) { const nodes = await fetchJson(`/projects/${projectId}/items/${itemId}/tree`); const panel = document.getElementById('compute-tree'); if (!nodes.length) { panel.innerHTML = '<div class="empty">当前名目下还没有树节点</div>'; renderBindingPanel('<div class="item"><strong>当前名目未挂靠二级离线模型</strong><div class="muted">点击步进炉下级功能按钮后，页面会自动安装并开始计算。</div></div>'); return; } const calcNodes = nodes.filter((node) => node.node_type === 'calc' && node.calc_step_id); const focus = new URLSearchParams(window.location.search).get('focus'); if (focus === 'step-furnace-level2' && calcNodes.some((node) => node.name === '步进炉二级计算离线模型')) { setMessage('已定位到步进炉第二级计算模型'); } panel.innerHTML = nodes.map((node) => { const isLevel2 = node.name === '步进炉二级计算离线模型'; const itemClass = node.node_type === 'group' ? 'item group-node' : isLevel2 ? 'item group-node' : 'item'; const pillClass = node.node_type === 'calc' ? 'pill ok' : node.node_type === 'group' ? 'pill group-pill' : 'pill'; const stepLine = node.node_type === 'calc' ? `<div class="muted">步骤: ${escapeHtml(node.calc_step_id ?? '-')}</div>` : '<div class="muted">模块组节点</div>'; const mountLine = isLevel2 ? `<div class="muted">已挂靠文件: walking_beam_level2_offline.py</div>` : ''; return `<div class="${itemClass}"><strong>${'&nbsp;'.repeat(node.depth * 4)}${escapeHtml(node.name)}</strong><div class="muted">节点 ID: ${node.id} | 深度: ${node.depth}</div><span class="${pillClass}">${escapeHtml(node.node_type)}</span>${stepLine}${mountLine}</div>`; }).join(''); await loadSelectedStepBinding(calcNodes); }
      async function ensurePreferredOfflineNodeId() { if (!currentProjectId || !currentItemId) { const defaults = await ensureDefaultProjectAndItem(); currentProjectId = Number(defaults.project.id); currentItemId = Number(defaults.item.id); renderContextPanel(`<div class="item"><strong>当前项目</strong><div class="muted">${escapeHtml(defaults.project.name)} (#${defaults.project.id})</div></div><div class="item"><strong>当前名目</strong><div class="muted">${escapeHtml(defaults.item.name)} (#${defaults.item.id})</div></div><div class="item"><strong>缺省条目</strong><div class="muted">已自动补充默认项目和默认名目，当前停在二级离线模型模块，等待人工点击开始计算。</div></div>`); } const nodes = await fetchJson(`/projects/${currentProjectId}/items/${currentItemId}/tree`); const level2Node = nodes.find((node) => node.name === '步进炉二级计算离线模型' && node.node_type === 'calc' && node.calc_step_id); if (level2Node) { await loadSelectedStepBinding(nodes.filter((node) => node.node_type === 'calc' && node.calc_step_id)); return Number(level2Node.id); } setMessage('未找到二级离线模型，正在自动安装步进炉模块组...'); const installedNodes = await fetchJson(`/projects/${currentProjectId}/items/${currentItemId}/install-step-furnace-modules`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ create_offline_step: true }) }); await loadTree(currentProjectId, currentItemId); const installedLevel2Node = installedNodes.find((node) => node.name === '步进炉二级计算离线模型' && node.node_type === 'calc' && node.calc_step_id); return installedLevel2Node ? Number(installedLevel2Node.id) : 0; }
      async function preparePreferredOfflineNode() { const nodeId = await ensurePreferredOfflineNodeId(); if (!nodeId) { setMessage('当前没有可准备的步进炉二级离线模型', 'danger'); return; } setMessage('二级离线模型模块已准备完成，请人工点击“开始计算”'); }
      async function runPreferredOfflineNode() { let nodeId = 0; try { nodeId = await ensurePreferredOfflineNodeId(); } catch (error) {} if (!nodeId) { setMessage('当前没有可直接计算的步进炉二级离线模型', 'danger'); return; } setMessage('正在执行步进炉二级计算离线模型...'); try { const execution = await fetchJson(`/tree/nodes/${nodeId}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ started_by: 'direct-button' }) }); renderExecutions([execution]); setMessage(`计算完成，已调用步进炉二级计算离线模型，执行记录 #${execution.id}`, 'ok'); } catch (error) { setMessage(`计算失败: ${error.message}`, 'danger'); } }
      function renderExecutions(executions) { const executionPanel = document.getElementById('execution-panel'); const resultPanel = document.getElementById('result-panel'); if (!executions.length) { executionPanel.innerHTML = '<div class="empty">当前名目下没有可执行计算节点</div>'; resultPanel.innerHTML = '<div class="empty">暂无执行结果</div>'; return; } executionPanel.innerHTML = executions.map((execution) => `<div class="item"><strong>执行 #${execution.id}</strong><div class="muted">根节点: ${execution.root_node_id} | 状态: ${escapeHtml(execution.status)}</div><div class="muted">开始时间: ${escapeHtml(execution.started_at)}</div><div class="actions"><button class="btn btn-secondary" onclick="loadExecutionResults(${execution.id})">查看结果</button><a class="btn btn-secondary report-link" href="/executions/${execution.id}/report" target="_blank">计算报告</a></div></div>`).join(''); loadExecutionResults(executions[executions.length - 1].id); }
      async function loadExecutionResults(executionId) { const results = await fetchJson(`/executions/${executionId}/results`); const panel = document.getElementById('result-panel'); if (!results.length) { panel.innerHTML = '<div class="empty">当前执行没有结果数据</div>'; return; } panel.innerHTML = results.map((result) => `<div class="item"><strong>节点 ${result.node_id}</strong><div class="muted">状态: ${escapeHtml(result.status)} | 步骤: ${result.calc_step_id}</div><div class="code">${escapeHtml(JSON.stringify(result.output_json ?? {}, null, 2))}</div></div>`).join(''); }
      async function loadComputeData() { await loadProjects(); }
      loadComputeData().then(async () => { const prepare = new URLSearchParams(window.location.search).get('prepare'); if (prepare === '1') { await preparePreferredOfflineNode(); } });
    </script>
  </body>
</html>
"""


def _feedback_page_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>反馈台</title>
    <style>
      :root { color-scheme: light; --bg: #09111f; --panel: rgba(15, 23, 42, 0.9); --text: #eef2ff; --muted: #94a3b8; --accent: #60a5fa; --line: rgba(148, 163, 184, 0.18); --danger: #ef4444; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #08101e 0%, #101a31 100%); color: var(--text); }
      .wrap { max-width: 1320px; margin: 0 auto; padding: 24px 20px 80px; }
      .hero, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; }
      .hero { padding: 24px; }
      .section-block { margin-top: 20px; }
      .section-label { margin: 0 0 8px; color: var(--accent); font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; }
      .section-grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
      .section-grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
      .card { padding: 20px; }
      h1, h2, h3 { margin-top: 0; }
      p, .muted { color: var(--muted); }
      .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
      .btn { display: inline-block; padding: 12px 16px; border-radius: 12px; text-decoration: none; font-weight: bold; }
      .btn-primary { background: var(--accent); color: #081225; }
      .btn-secondary { border: 1px solid var(--line); color: var(--text); }
      .form { display: grid; gap: 10px; margin-top: 14px; }
      .field { display: grid; gap: 6px; }
      .input, .select { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(2, 8, 23, 0.45); color: var(--text); }
      .list { display: grid; gap: 10px; margin-top: 14px; }
      .item { border: 1px solid var(--line); background: rgba(2, 8, 23, 0.22); border-radius: 14px; padding: 12px 14px; }
      .message { min-height: 20px; font-size: 13px; }
      .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--line); }
      .ok { color: #22c55e; }
      .danger { color: var(--danger); }
      @media (max-width: 1100px) { .section-grid-3, .section-grid-2 { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero"><h1>反馈台</h1><p>这里统一处理现场人员工况填报、生产异常上报和运行参数提交，数据入库后供分析菜单集中调用。</p><div class="actions"><a class="btn btn-secondary" href="/home">返回主菜单</a><a class="btn btn-primary" href="/compute">前往计算台</a><a class="btn btn-primary" href="/analysis">前往分析台</a></div></section>
      <section class="section-block"><div class="section-label">基础录入区</div><div class="section-grid-3"><article class="card"><h3>创建项目</h3><form class="form" onsubmit="createProject(event)"><div class="field"><label for="project-name">项目名称</label><input id="project-name" class="input" name="name" placeholder="例如：换热计算项目" required /></div><div class="field"><label for="project-owner">负责人</label><input id="project-owner" class="input" name="owner_user_id" placeholder="例如：u1" /></div><button class="btn btn-primary" type="submit">创建项目</button><div id="project-message" class="message muted"></div></form></article><article class="card"><h3>创建全局参数</h3><form class="form" onsubmit="createGlobalParam(event)"><div class="field"><label for="global-param-name">参数名</label><input id="global-param-name" class="input" name="name" placeholder="例如：temperature" required /></div><div class="field"><label for="global-param-type">参数类型</label><select id="global-param-type" class="select" name="value_type"><option value="number">number</option><option value="text">text</option><option value="bool">bool</option></select></div><div class="field"><label for="global-param-value">参数值</label><input id="global-param-value" class="input" name="value_text" placeholder="例如：120" required /></div><button class="btn btn-primary" type="submit">创建全局参数</button><div id="global-param-message" class="message muted"></div></form></article><article class="card"><h3>创建项目参数</h3><form class="form" onsubmit="createProjectParam(event)"><div class="field"><label for="project-param-project-id">项目 ID</label><input id="project-param-project-id" class="input" name="project_id" placeholder="例如：1" required /></div><div class="field"><label for="project-param-name">参数名</label><input id="project-param-name" class="input" name="name" placeholder="例如：pressure" required /></div><div class="field"><label for="project-param-type">参数类型</label><select id="project-param-type" class="select" name="value_type"><option value="number">number</option><option value="text">text</option><option value="bool">bool</option></select></div><div class="field"><label for="project-param-value">参数值</label><input id="project-param-value" class="input" name="value_text" placeholder="例如：5" required /></div><button class="btn btn-primary" type="submit">创建项目参数</button><div id="project-param-message" class="message muted"></div></form></article></div></section>
      <section class="section-block"><div class="section-label">结构录入区</div><div class="section-grid-2"><article class="card"><h3>创建名目</h3><form class="form" onsubmit="createProjectItem(event)"><div class="field"><label for="item-project-id">项目 ID</label><input id="item-project-id" class="input" name="project_id" placeholder="例如：1" required /></div><div class="field"><label for="item-name">名目名称</label><input id="item-name" class="input" name="name" placeholder="例如：换热器 A" required /></div><div class="field"><label for="item-code">名目编码</label><input id="item-code" class="input" name="code" placeholder="例如：ITEM-A" /></div><div class="field"><label for="item-description">说明</label><input id="item-description" class="input" name="description" placeholder="例如：主工段换热名目" /></div><button class="btn btn-primary" type="submit">创建名目</button><div id="item-message" class="message muted"></div></form></article><article class="card"><h3>创建树节点</h3><form class="form" onsubmit="createTreeNode(event)"><div class="field"><label for="node-project-id">项目 ID</label><input id="node-project-id" class="input" name="project_id" placeholder="例如：1" required /></div><div class="field"><label for="node-item-id">名目 ID</label><input id="node-item-id" class="input" name="item_id" placeholder="例如：2" required /></div><div class="field"><label for="node-name">节点名称</label><input id="node-name" class="input" name="name" placeholder="例如：入口换热计算" required /></div><div class="field"><label for="node-type">节点类型</label><select id="node-type" class="select" name="node_type"><option value="folder">folder</option><option value="calc">calc</option></select></div><div class="field"><label for="node-parent-id">父节点 ID</label><input id="node-parent-id" class="input" name="parent_id" placeholder="可选，例如：10" /></div><div class="field"><label for="node-calc-step-id">计算步骤 ID</label><input id="node-calc-step-id" class="input" name="calc_step_id" placeholder="calc 节点可填，例如：3" /></div><div class="field"><label for="node-order-index">排序</label><input id="node-order-index" class="input" name="order_index" placeholder="例如：1" value="0" /></div><button class="btn btn-primary" type="submit">创建树节点</button><div id="node-message" class="message muted"></div></form></article></div></section>
      <section class="section-block"><div class="section-label">现场录入区</div><div class="section-grid-2"><article class="card"><h3>创建现场反馈</h3><form class="form" onsubmit="createFeedback(event)"><div class="field"><label for="feedback-project-id">项目 ID</label><input id="feedback-project-id" class="input" name="project_id" placeholder="例如：1" required /></div><div class="field"><label for="feedback-item-id">名目 ID</label><input id="feedback-item-id" class="input" name="project_item_id" placeholder="可选，例如：3" /></div><div class="field"><label for="feedback-node-id">节点 ID</label><input id="feedback-node-id" class="input" name="node_id" placeholder="可选，例如：12" /></div><div class="field"><label for="feedback-title">反馈标题</label><input id="feedback-title" class="input" name="title" placeholder="例如：现场温度异常" required /></div><div class="field"><label for="feedback-severity">严重度</label><select id="feedback-severity" class="select" name="severity"><option value="info">info</option><option value="warning">warning</option><option value="critical">critical</option></select></div><div class="field"><label for="feedback-reported-by">反馈人</label><input id="feedback-reported-by" class="input" name="reported_by" placeholder="例如：shift-a" /></div><div class="field"><label for="feedback-content">反馈内容</label><input id="feedback-content" class="input" name="content" placeholder="例如：换热器入口波动较大" required /></div><button class="btn btn-primary" type="submit">创建现场反馈</button><div id="feedback-message" class="message muted"></div></form></article><article class="card"><div class="section-label">反馈查看区</div><h3>最近现场反馈</h3><div id="feedback-panel" class="list"></div></article></div></section>
      <section class="section-block"><div class="section-label">最近数据区</div><div class="section-grid-3"><article class="card"><h3>项目</h3><div id="project-list" class="list"></div></article><article class="card"><h3>全局参数</h3><div id="global-param-panel" class="list"></div></article><article class="card"><h3>项目参数</h3><div id="project-param-panel" class="list"></div></article><article class="card"><h3>名目</h3><div id="item-panel" class="list"></div></article><article class="card"><h3>树节点</h3><div id="node-panel" class="list"></div></article></div></section>
    </main>
    <script>
      function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
      async function fetchJson(url, options = {}) { const res = await fetch(url, options); if (!res.ok) { let detail = `${url} -> ${res.status}`; try { const data = await res.json(); if (data?.detail) { detail = `${detail} ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`; } } catch (error) {} throw new Error(detail); } if (res.status === 204) { return null; } return res.json(); }
      function setMessage(elementId, text, tone = 'muted') { const el = document.getElementById(elementId); el.className = `message ${tone}`; el.textContent = text; }
      async function loadProjects() { const projects = await fetchJson('/projects'); const el = document.getElementById('project-list'); if (!projects.length) { el.innerHTML = '<div class="muted">当前还没有项目</div>'; return; } el.innerHTML = projects.map((project) => `<div class="item"><strong>${escapeHtml(project.name)}</strong><div class="muted">ID: ${project.id} | 状态: ${escapeHtml(project.status)}</div></div>`).join(''); }
      async function loadGlobalParams() { const params = await fetchJson('/params/global'); const el = document.getElementById('global-param-panel'); if (!params.length) { el.innerHTML = '<div class="muted">当前还没有全局参数</div>'; return; } el.innerHTML = params.map((param) => `<div class="item"><strong>${escapeHtml(param.name)}</strong><div class="muted">类型: ${escapeHtml(param.value_type)}</div><div class="muted">值: ${escapeHtml(param.value_text)}</div></div>`).join(''); }
      async function loadProjectParamPanel() { const projects = await fetchJson('/projects'); const el = document.getElementById('project-param-panel'); if (!projects.length) { el.innerHTML = '<div class="muted">创建项目后可录入项目参数</div>'; return; } const sections = []; for (const project of projects.slice(0, 5)) { const params = await fetchJson(`/projects/${project.id}/params`); if (!params.length) { continue; } sections.push(`<div class="item"><strong>${escapeHtml(project.name)}</strong><div class="list">${params.slice(0, 3).map((param) => `<div><strong>${escapeHtml(param.name)}</strong><span class="muted">${escapeHtml(param.value_type)} = ${escapeHtml(param.value_text)}</span></div>`).join('')}</div></div>`); } el.innerHTML = sections.length ? sections.join('') : '<div class="muted">当前还没有项目参数</div>'; }
      async function loadProjectItemsPanel() { const projects = await fetchJson('/projects'); const el = document.getElementById('item-panel'); if (!projects.length) { el.innerHTML = '<div class="muted">创建项目后可录入名目</div>'; return; } const sections = []; for (const project of projects.slice(0, 5)) { const items = await fetchJson(`/projects/${project.id}/items`); if (!items.length) { continue; } sections.push(`<div class="item"><strong>${escapeHtml(project.name)}</strong><div class="list">${items.slice(0, 4).map((item) => `<div><strong>${escapeHtml(item.name)}</strong><span class="muted">ID:${item.id} 编码:${escapeHtml(item.code || '-')}</span></div>`).join('')}</div></div>`); } el.innerHTML = sections.length ? sections.join('') : '<div class="muted">当前还没有名目</div>'; }
      async function loadNodePanel() { const projects = await fetchJson('/projects'); const el = document.getElementById('node-panel'); if (!projects.length) { el.innerHTML = '<div class="muted">创建项目和名目后可录入树节点</div>'; return; } const sections = []; for (const project of projects.slice(0, 3)) { const items = await fetchJson(`/projects/${project.id}/items`); for (const item of items.slice(0, 2)) { const nodes = await fetchJson(`/projects/${project.id}/items/${item.id}/tree`); if (!nodes.length) { continue; } sections.push(`<div class="item"><strong>${escapeHtml(project.name)} / ${escapeHtml(item.name)}</strong><div class="list">${nodes.slice(0, 4).map((node) => `<div><strong>${escapeHtml(node.name)}</strong><span class="muted">ID:${node.id} 类型:${escapeHtml(node.node_type)} 步骤:${escapeHtml(node.calc_step_id || '-')}</span></div>`).join('')}</div></div>`); } } el.innerHTML = sections.length ? sections.join('') : '<div class="muted">当前还没有树节点</div>'; }
      async function loadFeedbackPanel() { const projects = await fetchJson('/projects'); const el = document.getElementById('feedback-panel'); if (!projects.length) { el.innerHTML = '<div class="muted">创建项目后可在这里查看最近现场反馈</div>'; return; } const sections = []; for (const project of projects.slice(0, 5)) { const feedback = await fetchJson(`/projects/${project.id}/feedback`); if (!feedback.length) { continue; } sections.push(`<div class="item"><strong>${escapeHtml(project.name)}</strong><div class="muted">项目 ID: ${project.id}</div><div class="list">${feedback.slice(0, 3).map((entry) => `<div><span class="pill ${entry.severity === 'critical' ? 'danger' : entry.severity === 'warning' ? 'warn' : 'ok'}">${escapeHtml(entry.severity)}</span>${escapeHtml(entry.title)}<span class="muted">名目:${escapeHtml(entry.project_item_id || '-')} 节点:${escapeHtml(entry.node_id || '-')}</span></div>`).join('')}</div></div>`); } el.innerHTML = sections.length ? sections.join('') : '<div class="muted">当前还没有现场反馈</div>'; }
      async function loadEntryData() { await Promise.all([loadProjects(), loadGlobalParams(), loadProjectParamPanel(), loadProjectItemsPanel(), loadNodePanel(), loadFeedbackPanel()]); }
      async function createProject(event) { event.preventDefault(); const form = event.target; const nameInput = form.elements.namedItem('name'); const ownerInput = form.elements.namedItem('owner_user_id'); setMessage('project-message', '正在创建项目...'); try { const project = await fetchJson('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: nameInput.value.trim(), owner_user_id: ownerInput.value.trim() || null, status: 'draft' }) }); form.reset(); setMessage('project-message', `已创建项目 #${project.id}`, 'pill ok'); await Promise.all([loadProjects(), loadProjectParamPanel(), loadProjectItemsPanel(), loadNodePanel(), loadFeedbackPanel()]); } catch (error) { setMessage('project-message', `创建失败: ${error.message}`, 'pill danger'); } }
      async function createGlobalParam(event) { event.preventDefault(); const form = event.target; const nameInput = form.elements.namedItem('name'); const typeInput = form.elements.namedItem('value_type'); const valueInput = form.elements.namedItem('value_text'); setMessage('global-param-message', '正在创建全局参数...'); try { const param = await fetchJson('/params/global', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: nameInput.value.trim(), value_type: typeInput.value, value_text: valueInput.value.trim() }) }); form.reset(); typeInput.value = 'number'; setMessage('global-param-message', `已创建全局参数 #${param.id}`, 'pill ok'); await loadGlobalParams(); } catch (error) { setMessage('global-param-message', `创建失败: ${error.message}`, 'pill danger'); } }
      async function createProjectParam(event) { event.preventDefault(); const form = event.target; const projectId = form.elements.namedItem('project_id').value.trim(); setMessage('project-param-message', '正在创建项目参数...'); try { const param = await fetchJson(`/projects/${projectId}/params`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.elements.namedItem('name').value.trim(), value_type: form.elements.namedItem('value_type').value, value_text: form.elements.namedItem('value_text').value.trim() }) }); form.reset(); document.getElementById('project-param-type').value = 'number'; setMessage('project-param-message', `已创建项目参数 #${param.id}`, 'pill ok'); await loadProjectParamPanel(); } catch (error) { setMessage('project-param-message', `创建失败: ${error.message}`, 'pill danger'); } }
      async function createProjectItem(event) { event.preventDefault(); const form = event.target; const projectId = form.elements.namedItem('project_id').value.trim(); setMessage('item-message', '正在创建名目...'); try { const item = await fetchJson(`/projects/${projectId}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.elements.namedItem('name').value.trim(), code: form.elements.namedItem('code').value.trim() || null, description: form.elements.namedItem('description').value.trim() || null }) }); form.reset(); setMessage('item-message', `已创建名目 #${item.id}`, 'pill ok'); await Promise.all([loadProjectItemsPanel(), loadNodePanel(), loadFeedbackPanel()]); } catch (error) { setMessage('item-message', `创建失败: ${error.message}`, 'pill danger'); } }
      async function createTreeNode(event) { event.preventDefault(); const form = event.target; const projectId = form.elements.namedItem('project_id').value.trim(); const itemId = form.elements.namedItem('item_id').value.trim(); const nodeType = form.elements.namedItem('node_type').value; setMessage('node-message', '正在创建树节点...'); try { const node = await fetchJson(`/projects/${projectId}/items/${itemId}/tree/nodes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.elements.namedItem('name').value.trim(), node_type: nodeType, parent_id: form.elements.namedItem('parent_id').value.trim() ? Number(form.elements.namedItem('parent_id').value.trim()) : null, calc_step_id: form.elements.namedItem('calc_step_id').value.trim() ? Number(form.elements.namedItem('calc_step_id').value.trim()) : null, order_index: Number(form.elements.namedItem('order_index').value.trim() || '0') }) }); form.reset(); document.getElementById('node-type').value = 'folder'; document.getElementById('node-order-index').value = '0'; setMessage('node-message', `已创建树节点 #${node.id}`, 'pill ok'); await Promise.all([loadNodePanel(), loadFeedbackPanel()]); } catch (error) { setMessage('node-message', `创建失败: ${error.message}`, 'pill danger'); } }
      async function createFeedback(event) { event.preventDefault(); const form = event.target; const projectId = form.elements.namedItem('project_id').value.trim(); setMessage('feedback-message', '正在创建现场反馈...'); try { const feedback = await fetchJson(`/projects/${projectId}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_item_id: form.elements.namedItem('project_item_id').value.trim() ? Number(form.elements.namedItem('project_item_id').value.trim()) : null, node_id: form.elements.namedItem('node_id').value.trim() ? Number(form.elements.namedItem('node_id').value.trim()) : null, title: form.elements.namedItem('title').value.trim(), severity: form.elements.namedItem('severity').value, reported_by: form.elements.namedItem('reported_by').value.trim() || null, content: form.elements.namedItem('content').value.trim(), source: 'onsite' }) }); form.reset(); document.getElementById('feedback-severity').value = 'info'; setMessage('feedback-message', `已创建现场反馈 #${feedback.id}`, 'pill ok'); await loadFeedbackPanel(); } catch (error) { setMessage('feedback-message', `创建失败: ${error.message}`, 'pill danger'); } }
      loadEntryData();
    </script>
  </body>
</html>
"""


@app.get("/analysis", response_class=HTMLResponse)
def analysis_page() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>计算平台分析台</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #09111f;
        --panel: rgba(15, 23, 42, 0.9);
        --panel-soft: rgba(15, 23, 42, 0.65);
        --text: #eef2ff;
        --muted: #94a3b8;
        --accent: #60a5fa;
        --accent-2: #22c55e;
        --line: rgba(148, 163, 184, 0.18);
        --warn: #f59e0b;
        --danger: #ef4444;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
        background:
          radial-gradient(circle at top left, rgba(96, 165, 250, 0.15), transparent 28%),
          radial-gradient(circle at top right, rgba(34, 197, 94, 0.12), transparent 24%),
          linear-gradient(180deg, #08101e 0%, #101a31 100%);
        color: var(--text);
      }
      .wrap {
        max-width: 1320px;
        margin: 0 auto;
        padding: 24px 20px 80px;
      }
      .hero {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 22px;
        padding: 28px;
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.3);
      }
      h1 {
        margin: 0 0 8px;
        font-size: 36px;
        line-height: 1.1;
      }
      p {
        margin: 0;
        color: var(--muted);
        line-height: 1.7;
      }
      .hero-top {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        align-items: flex-start;
      }
      .hero-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }
      .badge {
        padding: 8px 12px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: rgba(96, 165, 250, 0.08);
        color: var(--text);
        font-size: 13px;
      }
      .grid {
        display: grid;
        grid-template-columns: 300px minmax(0, 1fr);
        gap: 20px;
        margin-top: 24px;
      }
      .side {
        display: grid;
        gap: 16px;
        align-self: start;
      }
      .card {
        background: var(--panel-soft);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 20px;
      }
      .card h2 {
        margin: 0 0 10px;
        font-size: 18px;
      }
      .section-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
      }
      .card ul, .tree-list {
        margin: 0;
        padding-left: 18px;
        color: var(--muted);
        line-height: 1.8;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 28px;
      }
      .btn {
        display: inline-block;
        padding: 12px 16px;
        border-radius: 12px;
        text-decoration: none;
        font-weight: bold;
      }
      .btn-primary {
        background: var(--accent);
        color: #081225;
      }
      .btn-secondary {
        border: 1px solid var(--line);
        color: var(--text);
      }
      button.btn {
        cursor: pointer;
      }
      .status {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-top: 16px;
        color: var(--accent-2);
        font-size: 14px;
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: var(--accent-2);
        box-shadow: 0 0 12px var(--accent-2);
      }
      .foot {
        margin-top: 18px;
        font-size: 14px;
        color: var(--muted);
      }
      .panel-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }
      .panel-grid .card {
        min-height: 240px;
      }
      .toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 18px;
      }
      .stat-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
      }
      .stat {
        padding: 14px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: rgba(2, 8, 23, 0.28);
      }
      .stat strong {
        display: block;
        font-size: 24px;
        margin-bottom: 6px;
      }
      .muted { color: var(--muted); }
      .list {
        display: grid;
        gap: 10px;
        margin-top: 12px;
      }
      .item {
        border: 1px solid var(--line);
        background: rgba(2, 8, 23, 0.22);
        border-radius: 14px;
        padding: 12px 14px;
      }
      .item strong {
        display: block;
        margin-bottom: 6px;
      }
      .empty {
        color: var(--muted);
        font-size: 14px;
        padding: 8px 0;
      }
      .pill {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 999px;
        font-size: 12px;
        border: 1px solid var(--line);
        margin-right: 6px;
        margin-top: 6px;
      }
      .pill.ok { color: var(--accent-2); }
      .pill.warn { color: var(--warn); }
      .pill.danger { color: var(--danger); }
      .code {
        white-space: pre-wrap;
        word-break: break-word;
        font-family: monospace;
        font-size: 12px;
        color: #cbd5e1;
      }
      .form {
        display: grid;
        gap: 10px;
        margin-top: 14px;
      }
      .field {
        display: grid;
        gap: 6px;
      }
      .field label {
        font-size: 13px;
        color: var(--muted);
      }
      .input, .select {
        width: 100%;
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: rgba(2, 8, 23, 0.45);
        color: var(--text);
      }
      .message {
        min-height: 20px;
        font-size: 13px;
      }
      .flow-grid {
        display: grid;
        gap: 8px;
        margin-top: 10px;
      }
      .flow-card {
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: rgba(2, 8, 23, 0.3);
      }
      .flow-card strong {
        display: inline;
        margin: 0;
      }
      @media (max-width: 980px) {
        .grid { grid-template-columns: 1fr; }
        .panel-grid { grid-template-columns: 1fr; }
        .hero-top { flex-direction: column; }
      }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="hero">
        <div class="hero-top">
          <div>
            <h1>计算与现场分析工作台</h1>
            <p>这里统一查看项目结构、计算参数、现场反馈、审批和 AI 分析摘要，适合按项目核对完整业务链路。</p>
            <div class="status"><span class="dot"></span>服务运行中</div>
            <div class="hero-badges">
              <span class="badge">项目编排</span>
              <span class="badge">双语言执行</span>
              <span class="badge">现场反馈</span>
              <span class="badge">审批流</span>
              <span class="badge">AI 分析</span>
            </div>
          </div>
          <div class="actions">
            <a class="btn btn-primary" href="/compute">前往计算台</a>
            <a class="btn btn-secondary" href="/entry">前往录入台</a>
            <a class="btn btn-secondary" href="/">返回门户</a>
            <a class="btn btn-secondary" href="/docs">打开 API 文档</a>
            <a class="btn btn-secondary" href="/redoc">打开 ReDoc</a>
            <a class="btn btn-secondary" href="/health">健康检查</a>
          </div>
        </div>
        <div class="grid">
          <aside class="side">
            <article class="card">
              <h2>概览</h2>
              <div class="stat-grid">
                <div class="stat"><strong id="stat-projects">0</strong><span class="muted">项目数</span></div>
                <div class="stat"><strong id="stat-approvals">0</strong><span class="muted">审批数</span></div>
                <div class="stat"><strong id="stat-ai">0</strong><span class="muted">AI 请求</span></div>
                <div class="stat"><strong id="stat-feedback">0</strong><span class="muted">现场反馈</span></div>
                <div class="stat"><strong id="stat-global-params">0</strong><span class="muted">全局参数</span></div>
              </div>
              <div class="toolbar">
                <button class="btn btn-primary" onclick="loadDashboard()">刷新数据</button>
              </div>
            </article>
            <article class="card">
              <div class="section-head">
                <h2>项目列表</h2>
              </div>
              <div id="project-list" class="list"></div>
            </article>
            <article class="card">
              <h2>结构树</h2>
              <div id="tree-panel" class="empty">选择项目后加载结构树</div>
            </article>
          </aside>
          <section class="panel-grid">
            <article class="card">
              <h2>项目参数</h2>
              <div id="project-param-panel" class="empty">选择项目后加载项目参数</div>
            </article>
            <article class="card">
              <div class="section-head">
                <h2>全局参数</h2>
              </div>
              <div id="global-param-panel" class="empty">加载中...</div>
            </article>
            <article class="card">
              <h2>审批面板</h2>
              <div id="approval-panel" class="empty">加载中...</div>
            </article>
            <article class="card">
              <h2>现场反馈</h2>
              <div id="feedback-panel" class="empty">选择项目后加载现场反馈</div>
            </article>
            <article class="card">
              <h2>AI 分析面板</h2>
              <div id="ai-panel" class="empty">加载中...</div>
            </article>
          </section>
        </div>
        <div class="foot">FastAPI + SQLAlchemy + SQLite/PostgreSQL</div>
      </section>
    </main>
    <script>
      let currentProjectId = null;
      let currentProjectName = null;

      function escapeHtml(value) {
        return String(value ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }

      async function fetchJson(url, options = {}) {
        const res = await fetch(url, options);
        if (!res.ok) {
          let detail = `${url} -> ${res.status}`;
          try {
            const data = await res.json();
            if (data?.detail) {
              detail = `${detail} ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}`;
            }
          } catch (error) {
          }
          throw new Error(detail);
        }
        if (res.status === 204) {
          return null;
        }
        return res.json();
      }

      function setMessage(elementId, text, tone = 'muted') {
        const el = document.getElementById(elementId);
        el.className = `message ${tone}`;
        el.textContent = text;
      }

      function renderList(containerId, items, renderItem, emptyText) {
        const el = document.getElementById(containerId);
        if (!items.length) {
          el.innerHTML = `<div class="empty">${emptyText}</div>`;
          return;
        }
        el.innerHTML = items.map(renderItem).join('');
      }

      function renderThreeFlowFramework(framework) {
        if (!framework) {
          return '<div class="empty">当前分析结果还没有三流理论结构。</div>';
        }
        const flows = Array.isArray(framework.three_flows) ? framework.three_flows : [];
        return `
          <div class="item">
            <strong>${escapeHtml(framework.theory || '三流理论')}</strong>
            <div class="muted">${escapeHtml(framework.three_flow_state?.name || '三流一态')} | ${escapeHtml(framework.three_flow_state?.status || '待分析')}</div>
            <div class="flow-grid">
              ${flows.map((flow) => `
                <div class="flow-card">
                  <div><strong>${escapeHtml(flow.name)}</strong> <span class="pill warn">${escapeHtml(flow.status || 'unknown')}</span></div>
                  <div class="muted">${escapeHtml(flow.focus || '')}</div>
                  <div class="muted">证据: ${escapeHtml((flow.evidence || []).join('；'))}</div>
                  <div class="muted">建议: ${escapeHtml(flow.suggestion || '')}</div>
                </div>
              `).join('')}
            </div>
            <div class="muted" style="margin-top:10px;">${escapeHtml(framework.three_flow_state?.conclusion || '')}</div>
          </div>
        `;
      }

      async function loadProjects() {
        const projects = await fetchJson('/projects');
        document.getElementById('stat-projects').textContent = projects.length;
        renderList(
          'project-list',
          projects,
          (project) => `
            <div class="item">
              <strong>${escapeHtml(project.name)}</strong>
              <div class="muted">ID: ${project.id} | 状态: ${escapeHtml(project.status)}</div>
              <div class="toolbar">
                <button class="btn btn-secondary" onclick="selectProject(${project.id}, '${escapeHtml(project.name)}')">查看详情</button>
              </div>
            </div>
          `,
          '当前还没有项目'
        );
        if (!currentProjectId && projects.length) {
          await selectProject(projects[0].id, projects[0].name);
        }
      }

      async function selectProject(projectId, projectName) {
        currentProjectId = projectId;
        currentProjectName = projectName;
        await Promise.all([
          loadProjectWorkspace(projectId),
          loadProjectTree(projectId),
        ]);
      }

      async function loadProjectWorkspace(projectId) {
        const workspace = await fetchJson(`/projects/${projectId}/workspace`);
        document.getElementById('stat-feedback').textContent = workspace.feedback.length;
        renderList(
          'project-param-panel',
          workspace.project_params,
          (param) => `
            <div class="item">
              <strong>${escapeHtml(param.name)}</strong>
              <div class="muted">类型: ${escapeHtml(param.value_type)}</div>
              <div class="code">${escapeHtml(param.value_text)}</div>
            </div>
          `,
          '当前项目还没有参数'
        );
        renderList(
          'approval-panel',
          workspace.approvals,
          (approval) => `
            <div class="item">
              <strong>${escapeHtml(approval.target_type)} #${approval.target_id}</strong>
              <div class="muted">状态: ${escapeHtml(approval.status)} | 阶段: ${approval.current_stage}/${approval.total_stages}</div>
              <span class="pill ${approval.status === 'approved' ? 'ok' : approval.status === 'rejected' ? 'danger' : 'warn'}">${escapeHtml(approval.status)}</span>
            </div>
          `,
          '当前项目还没有审批记录'
        );
        renderList(
          'feedback-panel',
          workspace.feedback,
          (entry) => `
            <div class="item">
              <strong>${escapeHtml(entry.title)}</strong>
              <div class="muted">严重度: ${escapeHtml(entry.severity)} | 来源: ${escapeHtml(entry.source)}</div>
              <div class="muted">反馈人: ${escapeHtml(entry.reported_by || '未填写')}</div>
              <div class="muted">名目 ID: ${escapeHtml(entry.project_item_id || '-')} | 节点 ID: ${escapeHtml(entry.node_id || '-')}</div>
              <div class="code">${escapeHtml(entry.content)}</div>
              <div class="muted">反馈范围: ${escapeHtml(entry.feedback_scope_id || '项目默认范围')}</div>
            </div>
          `,
          '当前项目还没有现场反馈'
        );
        await renderAiPanelFromRequests(workspace.ai_requests);
      }

      async function loadProjectTree(projectId) {
        const items = await fetchJson(`/projects/${projectId}/items`);
        const panel = document.getElementById('tree-panel');
        if (!items.length) {
          panel.innerHTML = '<div class="empty">该项目下还没有名目与结构树</div>';
          return;
        }
        const sections = [];
        for (const item of items) {
          const nodes = await fetchJson(`/projects/${projectId}/items/${item.id}/tree`);
          sections.push(`
            <div class="item">
              <strong>${escapeHtml(item.name)}</strong>
              <div class="muted">名目 ID: ${item.id}</div>
              <div class="tree-list">
                ${nodes.length ? nodes.map((node) => `<div>${'&nbsp;'.repeat(node.depth * 4)}${escapeHtml(node.name)} <span class="pill ${node.node_type === 'calc' ? 'ok' : 'warn'}">${escapeHtml(node.node_type)}</span></div>`).join('') : '<div class="empty">暂无节点</div>'}
              </div>
            </div>
          `);
        }
        panel.innerHTML = sections.join('');
      }

      async function loadGlobalParams() {
        const params = await fetchJson('/params/global');
        document.getElementById('stat-global-params').textContent = params.length;
        renderList(
          'global-param-panel',
          params,
          (param) => `
            <div class="item">
              <strong>${escapeHtml(param.name)}</strong>
              <div class="muted">类型: ${escapeHtml(param.value_type)}</div>
              <div class="code">${escapeHtml(param.value_text)}</div>
            </div>
          `,
          '当前还没有全局参数'
        );
      }

      async function loadApprovals() {
        const approvals = await fetchJson('/approvals');
        document.getElementById('stat-approvals').textContent = approvals.length;
        return approvals;
      }

      async function loadAiRequests() {
        const requests = await fetchJson('/ai/analysis');
        document.getElementById('stat-ai').textContent = requests.length;
        return requests;
      }

      async function renderAiPanelFromRequests(requests) {
        const panel = document.getElementById('ai-panel');
        if (!requests.length) {
          panel.innerHTML = '<div class="empty">当前项目还没有 AI 分析请求</div>';
          return;
        }
        const sections = [];
        for (const request of requests) {
          const result = await fetchJson(`/ai/analysis/${request.id}/result`);
          const framework = result?.raw_response_json?.analysis_framework;
          sections.push(`
            <div class="item">
              <strong>${escapeHtml(request.analysis_type)}</strong>
              <div class="muted">状态: ${escapeHtml(request.status)} | 请求 ID: ${request.id}</div>
              <div class="muted">${escapeHtml(result?.summary || '')}</div>
              <div class="toolbar">
                <a class="btn btn-secondary" href="/ai/analysis/${request.id}/result" target="_blank">查看结果 JSON</a>
              </div>
              ${renderThreeFlowFramework(framework)}
            </div>
          `);
        }
        panel.innerHTML = sections.join('');
      }

      async function loadDashboard() {
        try {
          document.getElementById('stat-feedback').textContent = '0';
          await Promise.all([loadGlobalParams(), loadApprovals(), loadAiRequests()]);
          await loadProjects();
          const projectList = document.getElementById('project-list');
          if (!projectList.children.length || projectList.textContent.includes('当前还没有项目')) {
            document.getElementById('tree-panel').innerHTML = '<div class="empty">可以先在 /docs 创建项目、名目和树节点，控制台会自动显示结构。</div>';
            document.getElementById('project-param-panel').innerHTML = '<div class="empty">创建项目参数后会显示在这里。</div>';
            document.getElementById('approval-panel').innerHTML = '<div class="empty">创建审批请求后会显示在这里。</div>';
            document.getElementById('feedback-panel').innerHTML = '<div class="empty">创建现场反馈后会显示在这里。</div>';
            document.getElementById('ai-panel').innerHTML = '<div class="empty">创建 AI 分析请求后会显示在这里。</div>';
          }
        } catch (error) {
          document.getElementById('project-list').innerHTML = `<div class="empty">加载失败: ${escapeHtml(error.message)}</div>`;
        }
      }
      loadDashboard();
    </script>
  </body>
</html>
"""


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def build_project_workspace(db: Session, project_id: int) -> ProjectWorkspaceOut:
    project = get_project_or_404(db, project_id)
    items = db.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id).order_by(ProjectItem.id.desc())).all()
    project_params = db.scalars(
        select(ProjectParam).where(ProjectParam.project_id == project_id).order_by(ProjectParam.id.desc())
    ).all()
    feedback = db.scalars(
        select(ProjectFeedback).where(ProjectFeedback.project_id == project_id).order_by(ProjectFeedback.id.desc())
    ).all()
    approvals = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.project_id == project_id).order_by(ApprovalRequest.id.desc())
    ).all()
    ai_requests = db.scalars(
        select(AiAnalysisRequest).where(AiAnalysisRequest.project_id == project_id).order_by(AiAnalysisRequest.id.desc())
    ).all()
    latest_executions = db.scalars(
        select(CalcExecution).where(CalcExecution.project_id == project_id).order_by(CalcExecution.id.desc())
    ).all()
    return ProjectWorkspaceOut(
        project=ProjectOut.model_validate(project),
        items=[ProjectItemOut.model_validate(item) for item in items],
        project_params=[ProjectParamOut.model_validate(param) for param in project_params],
        feedback=[ProjectFeedbackOut.model_validate(entry) for entry in feedback],
        approvals=[ApprovalRequestOut.model_validate(approval) for approval in approvals],
        ai_requests=[AiAnalysisRequestOut.model_validate(request) for request in ai_requests],
        latest_executions=[ExecutionOut.model_validate(execution) for execution in latest_executions],
    )


def get_project_item_or_404(db: Session, project_id: int, item_id: int) -> ProjectItem:
    item = db.get(ProjectItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project item not found")
    return item


def get_node_or_404(db: Session, node_id: int) -> CalcNode:
    node = db.get(CalcNode, node_id)
    if not node or node.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return node


def get_approval_or_404(db: Session, approval_id: int) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return approval


def get_comparison_group_or_404(db: Session, group_id: int) -> ComparisonGroup:
    group = db.get(ComparisonGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison group not found")
    return group


def get_ai_request_or_404(db: Session, request_id: int) -> AiAnalysisRequest:
    request = db.get(AiAnalysisRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI analysis request not found")
    return request


def validate_calc_step_ref(db: Session, node_type: str, calc_step_id: int | None) -> None:
    if node_type == "calc" and calc_step_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Calc node requires calc_step_id")
    if calc_step_id is not None and db.get(CalcStep, calc_step_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Calc step not found")


def get_or_create_step_furnace_offline_step(db: Session) -> CalcStep:
    step = db.scalars(select(CalcStep).where(CalcStep.name == "步进炉二级计算离线模型").order_by(CalcStep.id.asc())).first()
    if step:
        step.language = "python"
        step.entry_point = "run"
        step.artifact_path = STEP_FURNACE_OFFLINE_ARTIFACT
        step.script_content = None
        step.timeout_seconds = 60
        step.is_active = True
        if not step.output_schema_json:
            step.output_schema_json = {
                "type": "object",
                "properties": {
                    "model_name": {"type": "string"},
                    "file_name": {"type": "string"},
                    "furnace_type": {"type": "string"},
                    "model_level": {"type": "string"},
                    "model_mode": {"type": "string"},
                    "operation_mode": {"type": "string"},
                    "optimized_setpoints_c": {"type": "object"},
                    "zone_results": {"type": "array"},
                    "exit_temperatures": {"type": "object"},
                    "target_deviation_c": {"type": "number"},
                    "core_surface_delta_c": {"type": "number"},
                    "max_rise_rate_c_per_min": {"type": "number"},
                    "energy_proxy": {"type": "number"},
                    "oxidation_proxy": {"type": "number"},
                    "objective_value": {"type": "number"},
                    "input_summary": {"type": "object"},
                },
            }
        db.flush()
        return step

    step = CalcStep(
        name="步进炉二级计算离线模型",
        step_type="step_furnace_offline_model",
        language="python",
        entry_point="run",
        script_content=None,
        artifact_path=STEP_FURNACE_OFFLINE_ARTIFACT,
        output_schema_json={
            "type": "object",
            "properties": {
                "model_name": {"type": "string"},
                "file_name": {"type": "string"},
                "furnace_type": {"type": "string"},
                "model_level": {"type": "string"},
                "model_mode": {"type": "string"},
                "operation_mode": {"type": "string"},
                "optimized_setpoints_c": {"type": "object"},
                "zone_results": {"type": "array"},
                "exit_temperatures": {"type": "object"},
                "target_deviation_c": {"type": "number"},
                "core_surface_delta_c": {"type": "number"},
                "max_rise_rate_c_per_min": {"type": "number"},
                "energy_proxy": {"type": "number"},
                "oxidation_proxy": {"type": "number"},
                "objective_value": {"type": "number"},
                "input_summary": {"type": "object"},
            },
        },
        timeout_seconds=60,
        is_active=True,
    )
    db.add(step)
    db.flush()
    return step


def create_template_node(
    db: Session,
    project_id: int,
    item_id: int,
    name: str,
    node_type: str,
    parent: CalcNode | None,
    order_index: int,
    calc_step_id: int | None = None,
    metadata_json: dict | None = None,
) -> CalcNode:
    node = CalcNode(
        project_id=project_id,
        project_item_id=item_id,
        parent_id=parent.id if parent else None,
        name=name,
        node_type=node_type,
        calc_step_id=calc_step_id,
        order_index=order_index,
        metadata_json=metadata_json,
        path="/pending",
        depth=0,
    )
    db.add(node)
    db.flush()
    node.path, node.depth = build_node_path(parent, node.id)
    return node


def install_step_furnace_module_tree(
    db: Session,
    project_id: int,
    item_id: int,
    create_offline_step: bool,
) -> list[CalcNode]:
    created_nodes: list[CalcNode] = []
    step = get_or_create_step_furnace_offline_step(db) if create_offline_step else None

    root_group = create_template_node(
        db,
        project_id,
        item_id,
        name="步进炉",
        node_type="group",
        parent=None,
        order_index=10,
        metadata_json={"furnace_type": "步进炉", "template": "phoenix_calc_v2_2"},
    )
    created_nodes.append(root_group)

    offline_model_group = create_template_node(
        db,
        project_id,
        item_id,
        name="二级计算离线模型",
        node_type="group",
        parent=root_group,
        order_index=10,
        metadata_json={"furnace_type": "步进炉", "model_level": "二级", "model_mode": "offline"},
    )
    created_nodes.append(offline_model_group)

    if step is not None:
        created_nodes.append(
            create_template_node(
                db,
                project_id,
                item_id,
                name="步进炉二级计算离线模型",
                node_type="calc",
                parent=offline_model_group,
                order_index=10,
                calc_step_id=step.id,
                metadata_json={"furnace_type": "步进炉", "model_level": "二级", "model_mode": "offline"},
            )
        )

    for index, group_name in enumerate(FURNACE_MODULE_GROUPS, start=20):
        created_nodes.append(
            create_template_node(
                db,
                project_id,
                item_id,
                name=group_name,
                node_type="group",
                parent=root_group,
                order_index=index,
                metadata_json={"furnace_type": "步进炉", "module_group": group_name},
            )
        )

    db.commit()
    for node in created_nodes:
        db.refresh(node)
    return created_nodes


def validate_step_language(language: str) -> None:
    if language not in ALLOWED_STEP_LANGUAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported step language")


def parse_param_value(value_type: str, value_text: str) -> int | float | str | bool:
    if value_type == "number":
        return float(value_text) if "." in value_text else int(value_text)
    if value_type == "bool":
        return value_text.strip().lower() in {"1", "true", "yes", "y"}
    return value_text


def decode_default_value(value: str | None) -> str | int | float | bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def serialize_feedback_entries(entries: list[ProjectFeedback]) -> list[dict[str, object | None]]:
    return [
        {
            "id": entry.id,
            "project_item_id": entry.project_item_id,
            "node_id": entry.node_id,
            "title": entry.title,
            "severity": entry.severity,
            "source": entry.source,
            "reported_by": entry.reported_by,
            "content": entry.content,
            "feedback_scope_id": entry.feedback_scope_id,
        }
        for entry in entries
    ]


def build_node_context(db: Session, node: CalcNode) -> dict:
    global_params = db.scalars(select(GlobalParam).order_by(GlobalParam.id.asc())).all()
    project_params = db.scalars(
        select(ProjectParam).where(ProjectParam.project_id == node.project_id).order_by(ProjectParam.id.asc())
    ).all()
    project_feedback = db.scalars(
        select(ProjectFeedback)
        .where(
            ProjectFeedback.project_id == node.project_id,
            ProjectFeedback.project_item_id.is_(None),
            ProjectFeedback.node_id.is_(None),
        )
        .order_by(ProjectFeedback.id.desc())
    ).all()
    item_feedback = db.scalars(
        select(ProjectFeedback)
        .where(
            ProjectFeedback.project_id == node.project_id,
            ProjectFeedback.project_item_id == node.project_item_id,
            ProjectFeedback.node_id.is_(None),
        )
        .order_by(ProjectFeedback.id.desc())
    ).all()
    node_feedback = db.scalars(
        select(ProjectFeedback)
        .where(ProjectFeedback.project_id == node.project_id, ProjectFeedback.node_id == node.id)
        .order_by(ProjectFeedback.id.desc())
    ).all()
    return {
        "project_id": node.project_id,
        "project_item_id": node.project_item_id,
        "node_id": node.id,
        "node_name": node.name,
        "node_type": node.node_type,
        "node_metadata": node.metadata_json or {},
        "global_params": {param.name: parse_param_value(param.value_type, param.value_text) for param in global_params},
        "project_params": {param.name: parse_param_value(param.value_type, param.value_text) for param in project_params},
        "feedback_context": {
            "project_feedback": serialize_feedback_entries(project_feedback),
            "item_feedback": serialize_feedback_entries(item_feedback),
            "node_feedback": serialize_feedback_entries(node_feedback),
        },
    }


def resolve_step_inputs(db: Session, step: CalcStep, node: CalcNode) -> dict:
    refs = db.scalars(select(CalcInputRef).where(CalcInputRef.calc_step_id == step.id).order_by(CalcInputRef.id.asc())).all()
    context = build_node_context(db, node)
    resolved: dict[str, object] = {}
    for ref in refs:
        value: object | None = None
        if ref.source_type == "global_param" and ref.source_key:
            value = context["global_params"].get(ref.source_key)
        elif ref.source_type == "project_param" and ref.source_key:
            value = context["project_params"].get(ref.source_key)
        elif ref.source_type == "constant":
            value = decode_default_value(ref.default_value)
        elif ref.source_type == "node_result" and ref.source_node_id and ref.source_key:
            latest_result = db.scalars(
                select(CalcResult)
                .where(CalcResult.node_id == ref.source_node_id)
                .order_by(CalcResult.executed_at.desc(), CalcResult.id.desc())
            ).first()
            if latest_result and latest_result.output_json:
                value = latest_result.output_json.get(ref.source_key)
        elif ref.source_type == "file_meta":
            value = {"source_key": ref.source_key}

        if value is None:
            value = decode_default_value(ref.default_value)
        resolved[ref.input_name] = value
    return resolved


def serialize_output_payload(step: CalcStep, node: CalcNode, payload: dict) -> dict:
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        return outputs
    return {
        "message": "Execution completed",
        "step_type": step.step_type,
        "node_id": node.id,
    }


def build_calc_report(result: CalcResult, execution: CalcExecution, node: CalcNode, step: CalcStep) -> dict:
    output_json = result.output_json or {}
    input_snapshot = result.input_snapshot_json or {}
    return {
        "report_title": f"{node.name} 计算报告",
        "project_id": execution.project_id,
        "project_item_id": execution.project_item_id,
        "execution_id": execution.id,
        "node_id": node.id,
        "node_name": node.name,
        "calc_step_id": step.id,
        "calc_step_name": step.name,
        "step_type": step.step_type,
        "status": result.status,
        "executed_at": result.executed_at.isoformat(),
        "duration_ms": result.duration_ms,
        "summary": {
            "model_name": output_json.get("model_name", step.name),
            "furnace_type": output_json.get("furnace_type", input_snapshot.get("node_metadata", {}).get("furnace_type")),
            "model_level": output_json.get("model_level", input_snapshot.get("node_metadata", {}).get("model_level")),
            "model_mode": output_json.get("model_mode", input_snapshot.get("node_metadata", {}).get("model_mode")),
        },
        "inputs": input_snapshot.get("inputs", {}),
        "project_params": input_snapshot.get("project_params", {}),
        "feedback_context": input_snapshot.get("feedback_context", {}),
        "outputs": output_json,
        "logs": result.log_text,
        "errors": result.error_text,
    }


def execute_node(db: Session, node: CalcNode, started_by: str | None) -> CalcExecution:
    if node.node_type != "calc" or node.calc_step_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Node is not executable")

    step = db.get(CalcStep, node.calc_step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Calc step not found")

    context = build_node_context(db, node)
    context["inputs"] = resolve_step_inputs(db, step, node)
    execution = CalcExecution(
        project_id=node.project_id,
        project_item_id=node.project_item_id,
        trigger_type="single_node",
        root_node_id=node.id,
        status="success",
        started_by=started_by,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(execution)
    db.flush()

    try:
        payload = executor_registry.get(step.language).execute(step, context)
        result = CalcResult(
            execution_id=execution.id,
            node_id=node.id,
            calc_step_id=step.id,
            status=payload.get("status", "success"),
            input_snapshot_json=context,
            output_json=serialize_output_payload(step, node, payload),
            log_text="\n".join(payload.get("logs", [])) if isinstance(payload.get("logs"), list) else None,
            error_text=None,
            duration_ms=int(payload.get("metrics", {}).get("duration_ms", 0)),
            executed_at=datetime.utcnow(),
        )
        execution.status = result.status
    except ExecutorError as exc:
        execution.status = "failed"
        result = CalcResult(
            execution_id=execution.id,
            node_id=node.id,
            calc_step_id=step.id,
            status="failed",
            input_snapshot_json=context,
            output_json={"error_code": exc.error_code},
            log_text=None,
            error_text=str(exc),
            duration_ms=0,
            executed_at=datetime.utcnow(),
        )

    execution.finished_at = datetime.utcnow()
    db.add(result)
    db.commit()
    db.refresh(execution)
    return execution


def collect_tree_nodes(db: Session, project_id: int, item_id: int) -> list[CalcNode]:
    return db.scalars(
        select(CalcNode)
        .where(
            CalcNode.project_id == project_id,
            CalcNode.project_item_id == item_id,
            CalcNode.deleted_at.is_(None),
        )
        .order_by(CalcNode.path.asc(), CalcNode.order_index.asc(), CalcNode.id.asc())
    ).all()


def create_approval_log(db: Session, approval: ApprovalRequest, action: str, actor_user_id: str | None, comment: str | None) -> None:
    db.add(
        ApprovalLog(
            approval_request_id=approval.id,
            action=action,
            stage_no=approval.current_stage,
            actor_user_id=actor_user_id,
            comment=comment,
        )
    )


def build_ai_payload(db: Session, payload: AiAnalysisCreate) -> dict:
    project = get_project_or_404(db, payload.project_id)
    latest_results = db.scalars(
        select(CalcResult)
        .join(CalcExecution, CalcExecution.id == CalcResult.execution_id)
        .where(CalcExecution.project_id == payload.project_id)
        .order_by(CalcResult.executed_at.desc(), CalcResult.id.desc())
    ).all()
    feedback_entries = db.scalars(
        select(ProjectFeedback)
        .where(ProjectFeedback.project_id == payload.project_id)
        .order_by(ProjectFeedback.id.desc())
    ).all()
    return {
        "project_id": payload.project_id,
        "project_item_id": payload.project_item_id,
        "analysis_type": payload.analysis_type,
        "context_scope_json": payload.context_scope_json,
        "input_payload_json": payload.input_payload_json,
        "shared_feedback_scope_id": project.shared_feedback_scope_id,
        "feedback_summary": [
            {
                "id": entry.id,
                "title": entry.title,
                "severity": entry.severity,
                "source": entry.source,
                "feedback_scope_id": entry.feedback_scope_id,
            }
            for entry in feedback_entries[:10]
        ],
        "latest_results": [
            {
                "node_id": result.node_id,
                "calc_step_id": result.calc_step_id,
                "status": result.status,
                "output_json": result.output_json,
            }
            for result in latest_results
        ],
    }


def build_node_path(parent: CalcNode | None, node_id: int) -> tuple[str, int]:
    if parent is None:
        return f"/{node_id}", 0
    return f"{parent.path}/{node_id}", parent.depth + 1


def refresh_subtree_paths(db: Session, node: CalcNode) -> None:
    children = db.scalars(
        select(CalcNode)
        .where(CalcNode.parent_id == node.id, CalcNode.deleted_at.is_(None))
        .order_by(CalcNode.order_index, CalcNode.id)
    ).all()
    for child in children:
        child.path = f"{node.path}/{child.id}"
        child.depth = node.depth + 1
        refresh_subtree_paths(db, child)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return db.scalars(select(Project).order_by(Project.id.desc())).all()


@app.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    return get_project_or_404(db, project_id)


@app.get("/projects/{project_id}/workspace", response_model=ProjectWorkspaceOut)
def get_project_workspace(project_id: int, db: Session = Depends(get_db)) -> ProjectWorkspaceOut:
    return build_project_workspace(db, project_id)


@app.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> Project:
    project = get_project_or_404(db, project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = get_project_or_404(db, project_id)
    db.delete(project)
    db.commit()


@app.get("/projects/{project_id}/items", response_model=list[ProjectItemOut])
def list_project_items(project_id: int, db: Session = Depends(get_db)) -> list[ProjectItem]:
    get_project_or_404(db, project_id)
    return db.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id).order_by(ProjectItem.id.desc())).all()


@app.post("/projects/{project_id}/items", response_model=ProjectItemOut, status_code=status.HTTP_201_CREATED)
def create_project_item(project_id: int, payload: ProjectItemCreate, db: Session = Depends(get_db)) -> ProjectItem:
    get_project_or_404(db, project_id)
    item = ProjectItem(project_id=project_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/params/global", response_model=list[GlobalParamOut])
def list_global_params(db: Session = Depends(get_db)) -> list[GlobalParam]:
    return db.scalars(select(GlobalParam).order_by(GlobalParam.id.desc())).all()


@app.post("/params/global", response_model=GlobalParamOut, status_code=status.HTTP_201_CREATED)
def create_global_param(payload: ParamCreate, db: Session = Depends(get_db)) -> GlobalParam:
    parse_param_value(payload.value_type, payload.value_text)
    param = GlobalParam(**payload.model_dump())
    db.add(param)
    db.commit()
    db.refresh(param)
    return param


@app.put("/params/global/{param_id}", response_model=GlobalParamOut)
def update_global_param(param_id: int, payload: ParamUpdate, db: Session = Depends(get_db)) -> GlobalParam:
    param = db.get(GlobalParam, param_id)
    if not param:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global param not found")
    updates = payload.model_dump(exclude_unset=True)
    next_type = updates.get("value_type", param.value_type)
    next_value = updates.get("value_text", param.value_text)
    parse_param_value(next_type, next_value)
    for key, value in updates.items():
        setattr(param, key, value)
    db.commit()
    db.refresh(param)
    return param


@app.delete("/params/global/{param_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_param(param_id: int, db: Session = Depends(get_db)) -> None:
    param = db.get(GlobalParam, param_id)
    if not param:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global param not found")
    db.delete(param)
    db.commit()


@app.get("/projects/{project_id}/params", response_model=list[ProjectParamOut])
def list_project_params(project_id: int, db: Session = Depends(get_db)) -> list[ProjectParam]:
    get_project_or_404(db, project_id)
    return db.scalars(select(ProjectParam).where(ProjectParam.project_id == project_id).order_by(ProjectParam.id.desc())).all()


@app.post("/projects/{project_id}/params", response_model=ProjectParamOut, status_code=status.HTTP_201_CREATED)
def create_project_param(project_id: int, payload: ParamCreate, db: Session = Depends(get_db)) -> ProjectParam:
    get_project_or_404(db, project_id)
    parse_param_value(payload.value_type, payload.value_text)
    param = ProjectParam(project_id=project_id, **payload.model_dump())
    db.add(param)
    db.commit()
    db.refresh(param)
    return param


@app.get("/projects/{project_id}/feedback", response_model=list[ProjectFeedbackOut])
def list_project_feedback(project_id: int, db: Session = Depends(get_db)) -> list[ProjectFeedback]:
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ProjectFeedback)
        .where(ProjectFeedback.project_id == project_id)
        .order_by(ProjectFeedback.id.desc())
    ).all()


@app.post("/projects/{project_id}/feedback", response_model=ProjectFeedbackOut, status_code=status.HTTP_201_CREATED)
def create_project_feedback(project_id: int, payload: ProjectFeedbackCreate, db: Session = Depends(get_db)) -> ProjectFeedback:
    project = get_project_or_404(db, project_id)
    project_item_id = payload.project_item_id
    if payload.project_item_id is not None:
        get_project_item_or_404(db, project_id, payload.project_item_id)
    if payload.node_id is not None:
        node = get_node_or_404(db, payload.node_id)
        if node.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feedback node is outside project")
        if project_item_id is not None and node.project_item_id != project_item_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feedback node does not belong to project item",
            )
    feedback = ProjectFeedback(
        project_id=project_id,
        feedback_scope_id=payload.feedback_scope_id or project.shared_feedback_scope_id,
        **payload.model_dump(exclude={"feedback_scope_id"}),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@app.put("/projects/{project_id}/params/{param_id}", response_model=ProjectParamOut)
def update_project_param(project_id: int, param_id: int, payload: ParamUpdate, db: Session = Depends(get_db)) -> ProjectParam:
    get_project_or_404(db, project_id)
    param = db.get(ProjectParam, param_id)
    if not param or param.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project param not found")
    updates = payload.model_dump(exclude_unset=True)
    next_type = updates.get("value_type", param.value_type)
    next_value = updates.get("value_text", param.value_text)
    parse_param_value(next_type, next_value)
    for key, value in updates.items():
        setattr(param, key, value)
    db.commit()
    db.refresh(param)
    return param


@app.delete("/projects/{project_id}/params/{param_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_param(project_id: int, param_id: int, db: Session = Depends(get_db)) -> None:
    get_project_or_404(db, project_id)
    param = db.get(ProjectParam, param_id)
    if not param or param.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project param not found")
    db.delete(param)
    db.commit()


@app.get("/calc-steps/{step_id}/input-refs", response_model=list[CalcInputRefOut])
def list_input_refs(step_id: int, db: Session = Depends(get_db)) -> list[CalcInputRef]:
    step = db.get(CalcStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    return db.scalars(select(CalcInputRef).where(CalcInputRef.calc_step_id == step_id).order_by(CalcInputRef.id.asc())).all()


@app.post("/calc-steps/{step_id}/input-refs", response_model=CalcInputRefOut, status_code=status.HTTP_201_CREATED)
def create_input_ref(step_id: int, payload: CalcInputRefCreate, db: Session = Depends(get_db)) -> CalcInputRef:
    step = db.get(CalcStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    input_ref = CalcInputRef(calc_step_id=step_id, **payload.model_dump())
    db.add(input_ref)
    db.commit()
    db.refresh(input_ref)
    return input_ref


@app.delete("/calc-steps/input-refs/{input_ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_input_ref(input_ref_id: int, db: Session = Depends(get_db)) -> None:
    input_ref = db.get(CalcInputRef, input_ref_id)
    if not input_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Input ref not found")
    db.delete(input_ref)
    db.commit()


@app.get("/projects/{project_id}/items/{item_id}/tree", response_model=list[CalcNodeOut])
def get_tree(project_id: int, item_id: int, db: Session = Depends(get_db)) -> list[CalcNode]:
    get_project_item_or_404(db, project_id, item_id)
    return collect_tree_nodes(db, project_id, item_id)


@app.post(
    "/projects/{project_id}/items/{item_id}/install-step-furnace-modules",
    response_model=list[CalcNodeOut],
    status_code=status.HTTP_201_CREATED,
)
def install_step_furnace_modules(
    project_id: int,
    item_id: int,
    payload: CalcModuleTemplateInstall,
    db: Session = Depends(get_db),
) -> list[CalcNode]:
    get_project_item_or_404(db, project_id, item_id)
    return install_step_furnace_module_tree(db, project_id, item_id, payload.create_offline_step)


@app.get("/projects/{project_id}/available_refs")
def get_available_refs(project_id: int, db: Session = Depends(get_db)) -> dict:
    get_project_or_404(db, project_id)
    global_params = db.scalars(select(GlobalParam).order_by(GlobalParam.id.asc())).all()
    project_params = db.scalars(select(ProjectParam).where(ProjectParam.project_id == project_id).order_by(ProjectParam.id.asc())).all()
    feedback_entries = db.scalars(
        select(ProjectFeedback).where(ProjectFeedback.project_id == project_id).order_by(ProjectFeedback.id.desc())
    ).all()
    recent_results = db.scalars(
        select(CalcResult)
        .join(CalcExecution, CalcExecution.id == CalcResult.execution_id)
        .where(CalcExecution.project_id == project_id)
        .order_by(CalcResult.executed_at.desc(), CalcResult.id.desc())
    ).all()
    return {
        "global_params": [param.name for param in global_params],
        "project_params": [param.name for param in project_params],
        "feedback_summary": [
            {
                "id": entry.id,
                "title": entry.title,
                "project_item_id": entry.project_item_id,
                "node_id": entry.node_id,
                "severity": entry.severity,
            }
            for entry in feedback_entries[:20]
        ],
        "node_results": [
            {
                "node_id": result.node_id,
                "keys": list((result.output_json or {}).keys()),
            }
            for result in recent_results
        ],
    }


@app.post("/projects/{project_id}/items/{item_id}/tree/nodes", response_model=CalcNodeOut, status_code=status.HTTP_201_CREATED)
def create_tree_node(project_id: int, item_id: int, payload: CalcNodeCreate, db: Session = Depends(get_db)) -> CalcNode:
    get_project_item_or_404(db, project_id, item_id)
    validate_calc_step_ref(db, payload.node_type, payload.calc_step_id)

    parent = None
    if payload.parent_id is not None:
        parent = get_node_or_404(db, payload.parent_id)
        if parent.project_id != project_id or parent.project_item_id != item_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent node is outside target tree")

    node = CalcNode(
        project_id=project_id,
        project_item_id=item_id,
        parent_id=payload.parent_id,
        name=payload.name,
        node_type=payload.node_type,
        calc_step_id=payload.calc_step_id,
        order_index=payload.order_index,
        metadata_json=payload.metadata_json,
        path="/pending",
        depth=0,
    )
    db.add(node)
    db.flush()
    node.path, node.depth = build_node_path(parent, node.id)
    db.commit()
    db.refresh(node)
    return node


@app.put("/tree/nodes/{node_id}", response_model=CalcNodeOut)
def update_tree_node(node_id: int, payload: CalcNodeUpdate, db: Session = Depends(get_db)) -> CalcNode:
    node = get_node_or_404(db, node_id)
    next_node_type = payload.node_type if payload.node_type is not None else node.node_type
    next_calc_step_id = payload.calc_step_id if "calc_step_id" in payload.model_dump(exclude_unset=True) else node.calc_step_id
    validate_calc_step_ref(db, next_node_type, next_calc_step_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    db.commit()
    db.refresh(node)
    return node


@app.post("/tree/nodes/{node_id}/move", response_model=CalcNodeOut)
def move_tree_node(node_id: int, payload: CalcNodeMove, db: Session = Depends(get_db)) -> CalcNode:
    node = get_node_or_404(db, node_id)
    new_parent = None
    if payload.new_parent_id is not None:
        new_parent = get_node_or_404(db, payload.new_parent_id)
        if new_parent.project_id != node.project_id or new_parent.project_item_id != node.project_item_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target parent is outside current tree")
        if new_parent.path.startswith(f"{node.path}/") or new_parent.id == node.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot move a node into its own subtree")

    node.parent_id = payload.new_parent_id
    node.order_index = payload.new_order_index
    node.path, node.depth = build_node_path(new_parent, node.id)
    refresh_subtree_paths(db, node)
    db.commit()
    db.refresh(node)
    return node


@app.delete("/tree/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tree_node(node_id: int, db: Session = Depends(get_db)) -> None:
    node = get_node_or_404(db, node_id)
    node.deleted_at = datetime.utcnow()
    db.commit()


@app.get("/calc-steps", response_model=list[CalcStepOut])
def list_calc_steps(db: Session = Depends(get_db)) -> list[CalcStep]:
    return db.scalars(select(CalcStep).order_by(CalcStep.id.desc())).all()


@app.post("/calc-steps", response_model=CalcStepOut, status_code=status.HTTP_201_CREATED)
def create_calc_step(payload: CalcStepCreate, db: Session = Depends(get_db)) -> CalcStep:
    validate_step_language(payload.language)
    step = CalcStep(**payload.model_dump())
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@app.get("/calc-steps/{step_id}", response_model=CalcStepOut)
def get_calc_step(step_id: int, db: Session = Depends(get_db)) -> CalcStep:
    step = db.get(CalcStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    return step


@app.put("/calc-steps/{step_id}", response_model=CalcStepOut)
def update_calc_step(step_id: int, payload: CalcStepUpdate, db: Session = Depends(get_db)) -> CalcStep:
    step = db.get(CalcStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    if payload.language is not None:
        validate_step_language(payload.language)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(step, key, value)
    db.commit()
    db.refresh(step)
    return step


@app.delete("/calc-steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calc_step(step_id: int, db: Session = Depends(get_db)) -> None:
    step = db.get(CalcStep, step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    db.delete(step)
    db.commit()


@app.post("/tree/nodes/{node_id}/run", response_model=ExecutionOut, status_code=status.HTTP_201_CREATED)
def run_tree_node(node_id: int, payload: RunNodeRequest, db: Session = Depends(get_db)) -> CalcExecution:
    node = get_node_or_404(db, node_id)
    return execute_node(db, node, payload.started_by)


@app.post("/projects/{project_id}/items/{item_id}/run-tree", response_model=list[ExecutionOut], status_code=status.HTTP_201_CREATED)
def run_project_tree(project_id: int, item_id: int, payload: RunTreeRequest, db: Session = Depends(get_db)) -> list[CalcExecution]:
    get_project_item_or_404(db, project_id, item_id)
    nodes = collect_tree_nodes(db, project_id, item_id)
    executions: list[CalcExecution] = []
    for node in nodes:
        if node.node_type == "calc" and node.calc_step_id is not None:
            executions.append(execute_node(db, node, payload.started_by))
    return executions


@app.get("/executions/{execution_id}", response_model=ExecutionOut)
def get_execution(execution_id: int, db: Session = Depends(get_db)) -> CalcExecution:
    execution = db.get(CalcExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@app.get("/executions/{execution_id}/results", response_model=list[ResultOut])
def get_execution_results(execution_id: int, db: Session = Depends(get_db)) -> list[CalcResult]:
    execution = db.get(CalcExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return db.scalars(select(CalcResult).where(CalcResult.execution_id == execution_id).order_by(CalcResult.id.asc())).all()


@app.get("/executions/{execution_id}/report")
def get_execution_report(execution_id: int, db: Session = Depends(get_db)) -> dict:
    execution = db.get(CalcExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    result = db.scalars(select(CalcResult).where(CalcResult.execution_id == execution_id).order_by(CalcResult.id.asc())).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution result not found")
    node = get_node_or_404(db, result.node_id)
    step = db.get(CalcStep, result.calc_step_id)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calc step not found")
    return build_calc_report(result, execution, node, step)


@app.post("/approvals", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
def create_approval(payload: ApprovalCreate, db: Session = Depends(get_db)) -> ApprovalRequest:
    get_project_or_404(db, payload.project_id)
    if payload.project_item_id is not None:
        get_project_item_or_404(db, payload.project_id, payload.project_item_id)
    approval = ApprovalRequest(**payload.model_dump(exclude={"comment"}))
    db.add(approval)
    db.flush()
    create_approval_log(db, approval, "submit", payload.submitted_by, payload.comment)
    db.commit()
    db.refresh(approval)
    return approval


@app.get("/approvals", response_model=list[ApprovalRequestOut])
def list_approvals(db: Session = Depends(get_db)) -> list[ApprovalRequest]:
    return db.scalars(select(ApprovalRequest).order_by(ApprovalRequest.id.desc())).all()


@app.get("/approvals/{approval_id}", response_model=ApprovalRequestOut)
def get_approval(approval_id: int, db: Session = Depends(get_db)) -> ApprovalRequest:
    return get_approval_or_404(db, approval_id)


@app.get("/approvals/{approval_id}/logs", response_model=list[ApprovalLogOut])
def get_approval_logs(approval_id: int, db: Session = Depends(get_db)) -> list[ApprovalLog]:
    get_approval_or_404(db, approval_id)
    return db.scalars(select(ApprovalLog).where(ApprovalLog.approval_request_id == approval_id).order_by(ApprovalLog.id.asc())).all()


@app.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestOut)
def approve_request(approval_id: int, payload: ApprovalAction, db: Session = Depends(get_db)) -> ApprovalRequest:
    approval = get_approval_or_404(db, approval_id)
    if approval.current_stage < approval.total_stages:
        approval.current_stage += 1
        approval.status = "in_review"
        create_approval_log(db, approval, "approve", payload.actor_user_id, payload.comment)
    else:
        approval.status = "approved"
        approval.closed_at = datetime.utcnow()
        create_approval_log(db, approval, "approve", payload.actor_user_id, payload.comment)
    db.commit()
    db.refresh(approval)
    return approval


@app.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestOut)
def reject_request(approval_id: int, payload: ApprovalAction, db: Session = Depends(get_db)) -> ApprovalRequest:
    approval = get_approval_or_404(db, approval_id)
    approval.status = "rejected"
    approval.closed_at = datetime.utcnow()
    create_approval_log(db, approval, "reject", payload.actor_user_id, payload.comment)
    db.commit()
    db.refresh(approval)
    return approval


@app.get("/projects/{project_id}/approvals", response_model=list[ApprovalRequestOut])
def get_project_approvals(project_id: int, db: Session = Depends(get_db)) -> list[ApprovalRequest]:
    get_project_or_404(db, project_id)
    return db.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id).order_by(ApprovalRequest.id.desc())).all()


@app.get("/comparisons/groups", response_model=list[ComparisonGroupOut])
def list_comparison_groups(db: Session = Depends(get_db)) -> list[ComparisonGroup]:
    return db.scalars(select(ComparisonGroup).order_by(ComparisonGroup.id.desc())).all()


@app.post("/comparisons/groups", response_model=ComparisonGroupOut, status_code=status.HTTP_201_CREATED)
def create_comparison_group(payload: ComparisonGroupCreate, db: Session = Depends(get_db)) -> ComparisonGroup:
    group = ComparisonGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@app.get("/comparisons/groups/{group_id}", response_model=ComparisonGroupOut)
def get_comparison_group(group_id: int, db: Session = Depends(get_db)) -> ComparisonGroup:
    return get_comparison_group_or_404(db, group_id)


@app.post("/comparisons/groups/{group_id}/items", response_model=ComparisonItemOut, status_code=status.HTTP_201_CREATED)
def create_comparison_item(group_id: int, payload: ComparisonItemCreate, db: Session = Depends(get_db)) -> ComparisonItem:
    get_comparison_group_or_404(db, group_id)
    get_project_or_404(db, payload.project_id)
    item = ComparisonItem(comparison_group_id=group_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/comparisons/groups/{group_id}/report")
def get_comparison_report(group_id: int, db: Session = Depends(get_db)) -> dict:
    group = get_comparison_group_or_404(db, group_id)
    items = db.scalars(select(ComparisonItem).where(ComparisonItem.comparison_group_id == group_id).order_by(ComparisonItem.id.asc())).all()
    rows = []
    for item in items:
        result = db.get(CalcResult, item.result_id) if item.result_id else None
        rows.append(
            {
                "item_id": item.id,
                "project_id": item.project_id,
                "node_id": item.node_id,
                "result_id": item.result_id,
                "metrics": result.output_json if result else None,
            }
        )
    return {
        "group": ComparisonGroupOut.model_validate(group).model_dump(),
        "rows": rows,
    }


@app.post("/ai/analysis", response_model=AiAnalysisRequestOut, status_code=status.HTTP_201_CREATED)
def create_ai_analysis(payload: AiAnalysisCreate, db: Session = Depends(get_db)) -> AiAnalysisRequest:
    get_project_or_404(db, payload.project_id)
    if payload.project_item_id is not None:
        get_project_item_or_404(db, payload.project_id, payload.project_item_id)
    request = AiAnalysisRequest(
        **payload.model_dump(),
        status="success",
        requested_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(request)
    db.flush()

    ai_payload = build_ai_payload(db, payload)
    ai_response = ai_provider.analyze(ai_payload)
    raw_response_json = ai_response.get("raw_response_json") or {}
    raw_response_json.update(
        {
            "shared_feedback_scope_id": ai_payload.get("shared_feedback_scope_id"),
            "feedback_summary": ai_payload.get("feedback_summary", []),
        }
    )
    result = AiAnalysisResult(
        request_id=request.id,
        summary=ai_response.get("summary"),
        diagnosis_text=ai_response.get("diagnosis_text"),
        suggestions_json=ai_response.get("suggestions_json"),
        risk_flags_json=ai_response.get("risk_flags_json"),
        raw_response_json=raw_response_json,
    )
    db.add(result)
    db.commit()
    db.refresh(request)
    return request


@app.get("/ai/analysis/{request_id}", response_model=AiAnalysisRequestOut)
def get_ai_analysis(request_id: int, db: Session = Depends(get_db)) -> AiAnalysisRequest:
    return get_ai_request_or_404(db, request_id)


@app.get("/ai/analysis/{request_id}/result", response_model=AiAnalysisResultOut)
def get_ai_analysis_result(request_id: int, db: Session = Depends(get_db)) -> AiAnalysisResult:
    request = get_ai_request_or_404(db, request_id)
    if not request.result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI analysis result not found")
    return request.result


@app.get("/ai/analysis", response_model=list[AiAnalysisRequestOut])
def list_ai_analysis(project_id: int | None = None, db: Session = Depends(get_db)) -> list[AiAnalysisRequest]:
    stmt = select(AiAnalysisRequest).order_by(AiAnalysisRequest.id.desc())
    if project_id is not None:
        stmt = stmt.where(AiAnalysisRequest.project_id == project_id)
    return db.scalars(stmt).all()
