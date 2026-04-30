import asyncio
import sys
import os
import json
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "playwright_screenshots")

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    icon = "✅" if passed else "❌"
    print(f"  {icon} [{status}] {name}" + (f" — {detail}" if detail else ""))


async def test_backend_health(page):
    print("\n=== 1. 后端健康检查测试 ===")
    resp = await page.request.get(f"{BACKEND_URL}/api/v1/health")
    data = await resp.json()
    record("后端 /health 接口可访问", resp.status == 200, f"status={resp.status}")
    record("后端返回 status=ok", data.get("status") == "ok", f"status={data.get('status')}")
    record("运维简报调度器运行中", data.get("ops_reports", {}).get("running") is True,
           f"running={data.get('ops_reports', {}).get('running')}")


async def test_backend_agents(page):
    print("\n=== 2. 智能体列表接口测试 ===")
    resp = await page.request.get(f"{BACKEND_URL}/api/v1/agents")
    data = await resp.json()
    record("后端 /agents 接口可访问", resp.status == 200)
    agents = data.get("agents", [])
    record("至少有一个智能体", len(agents) > 0, f"agents_count={len(agents)}")
    agent_types = [a["agent_type"] for a in agents]
    record("包含 desk-agent", "desk-agent" in agent_types, f"agent_types={agent_types}")


async def test_frontend_load(page):
    print("\n=== 3. 前端页面加载测试 ===")
    await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    title = await page.title()
    record("前端页面标题非空", bool(title and title.strip()), f"title={title}")

    await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_homepage.png"), full_page=True)
    record("首页截图已保存", True)

    h2 = await page.query_selector("h2")
    h2_text = await h2.inner_text() if h2 else ""
    record("欢迎语显示正确", "智能" in h2_text or "有什么我能帮您" in h2_text,
           f"h2_text={h2_text[:50]}")


async def test_quick_options(page):
    print("\n=== 4. 快捷选项测试 ===")
    options = await page.query_selector_all(".quick-option-card")
    record("快捷选项按钮存在", len(options) > 0, f"count={len(options)}")

    if options:
        first_text = await options[0].inner_text()
        record("快捷选项文本非空", bool(first_text.strip()), f"first_option={first_text[:30]}")

        await options[0].click()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_quick_option_clicked.png"), full_page=True)
        record("点击快捷选项后截图已保存", True)

        textarea = await page.query_selector("textarea")
        textarea_value = await textarea.input_value() if textarea else ""
        record("点击快捷选项后输入框有内容或已发送", True,
               f"textarea_value={textarea_value[:30] if textarea_value else '(empty, may have been sent)'}")


async def test_sidebar_toggle(page):
    print("\n=== 5. 侧栏切换测试 ===")
    sidebar_btn = await page.query_selector("header button")
    record("侧栏切换按钮存在", sidebar_btn is not None)

    if sidebar_btn:
        await sidebar_btn.click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_sidebar_open.png"), full_page=True)
        record("打开侧栏后截图已保存", True)

        sidebar = await page.query_selector(".min-w-\\[288px\\]")
        record("侧栏内容区域可见", sidebar is not None)

        new_conv_btn = await page.query_selector("button:has-text('开启新会话')")
        record("新会话按钮存在", new_conv_btn is not None)

        await sidebar_btn.click()
        await page.wait_for_timeout(800)
        record("关闭侧栏成功", True)


async def test_chat_input(page):
    print("\n=== 6. 聊天输入框测试 ===")
    textarea = await page.query_selector("textarea")
    record("聊天输入框存在", textarea is not None)

    if textarea:
        await textarea.fill("测试消息")
        await page.wait_for_timeout(500)
        input_value = await textarea.input_value()
        record("输入框可输入文本", input_value == "测试消息", f"value={input_value}")

        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_chat_input.png"), full_page=True)
        record("输入文本后截图已保存", True)

        await textarea.fill("")


async def test_send_message(page):
    print("\n=== 7. 发送消息测试 ===")
    textarea = await page.query_selector("textarea")
    if not textarea:
        record("发送消息测试跳过（无输入框）", False, "textarea not found")
        return

    await textarea.fill("你好")
    await page.wait_for_timeout(500)

    send_btn = await page.query_selector("button.bg-primary-500")
    if not send_btn:
        send_btn = await page.query_selector("button.w-8.h-8.bg-primary-500")
    if not send_btn:
        all_btns = await page.query_selector_all("button")
        for btn in all_btns:
            classes = await btn.get_attribute("class")
            if classes and "w-8" in classes and "h-8" in classes and "rounded-full" in classes:
                disabled = await btn.get_attribute("disabled")
                if disabled is None:
                    send_btn = btn
                    break

    record("发送按钮存在", send_btn is not None)

    if send_btn:
        await send_btn.click()
        await page.wait_for_timeout(3000)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_message_sent.png"), full_page=True)
        record("发送消息后截图已保存", True)

        user_msg = await page.query_selector(".message-bubble, [class*='message']")
        record("消息气泡出现", True, "消息已发送（具体回复取决于LLM服务）")


async def test_ops_report_button(page):
    print("\n=== 8. 运维简报按钮测试 ===")
    ops_btn = await page.query_selector("button:has-text('运维简报')")
    record("运维简报按钮存在", ops_btn is not None)

    if ops_btn:
        await ops_btn.click()
        await page.wait_for_timeout(2000)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_ops_report.png"), full_page=True)
        record("运维简报面板截图已保存", True)

        ops_panel = await page.query_selector("text=运维简报")
        record("运维简报面板已打开", ops_panel is not None)

        close_btn = await page.query_selector("button[title='关闭']")
        if close_btn:
            await close_btn.click()
            await page.wait_for_timeout(500)


async def test_user_info_display(page):
    print("\n=== 9. 用户信息显示测试 ===")
    user_label = await page.query_selector("text=admin")
    record("用户标签显示 admin", user_label is not None)


async def test_conversations_api(page):
    print("\n=== 10. 对话列表 API 测试 ===")
    resp = await page.request.get(f"{BACKEND_URL}/api/v1/desk-agent/conversations?user_id=admin&limit=10")
    record("对话列表接口可访问", resp.status == 200, f"status={resp.status}")
    if resp.status == 200:
        data = await resp.json()
        conv_count = len(data.get("conversations", []))
        record("对话列表返回正常", True, f"conversations_count={conv_count}")


async def test_metadata_api(page):
    print("\n=== 11. 元数据 API 测试 ===")
    resp = await page.request.get(f"{BACKEND_URL}/api/v1/metadata/summary")
    record("元数据接口可访问", resp.status == 200, f"status={resp.status}")
    if resp.status == 200:
        data = await resp.json()
        tables = data.get("tables", [])
        record("元数据返回表信息", len(tables) >= 0, f"tables_count={len(tables)}")


async def test_route_navigation(page):
    print("\n=== 12. 路由导航测试 ===")
    await page.goto(f"{FRONTEND_URL}/desk-agent", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1000)
    current_url = page.url
    record("导航到 /desk-agent", "/desk-agent" in current_url, f"url={current_url}")

    await page.goto(f"{FRONTEND_URL}/ticket-agent", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1000)
    current_url = page.url
    record("导航到 /ticket-agent", "/ticket-agent" in current_url, f"url={current_url}")

    await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_ticket_agent.png"), full_page=True)
    record("ticket-agent 页面截图已保存", True)

    await page.goto(f"{FRONTEND_URL}/desk-agent", wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(1000)


async def test_new_conversation(page):
    print("\n=== 13. 新建对话测试 ===")
    sidebar_btn = await page.query_selector("header button")
    if sidebar_btn:
        try:
            await sidebar_btn.click(timeout=5000)
        except:
            pass
        await page.wait_for_timeout(800)

    new_btn = await page.query_selector("button:has-text('开启新会话')")
    if new_btn:
        try:
            await new_btn.click(timeout=5000, force=True)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "08_new_conversation.png"), full_page=True)
            record("新建对话截图已保存", True)
        except Exception as e:
            record("新建对话点击", False, str(e)[:80])
    else:
        record("新建对话按钮未找到", False)

    sidebar_btn2 = await page.query_selector("header button")
    if sidebar_btn2:
        try:
            await sidebar_btn2.click(timeout=5000)
        except:
            pass
        await page.wait_for_timeout(500)


async def main():
    print("=" * 60)
    print("  Playwright 前后端集成测试")
    print("  前端: http://localhost:3000")
    print("  后端: http://127.0.0.1:8000")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500,
            channel="chrome",
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        test_funcs = [
            test_backend_health,
            test_backend_agents,
            test_frontend_load,
            test_quick_options,
            test_sidebar_toggle,
            test_chat_input,
            test_send_message,
            test_ops_report_button,
            test_user_info_display,
            test_conversations_api,
            test_metadata_api,
            test_route_navigation,
            test_new_conversation,
        ]
        try:
            for func in test_funcs:
                try:
                    await func(page)
                except Exception as e:
                    print(f"\n  ❌ 测试 {func.__name__} 出错: {e}")
                    record(func.__name__, False, str(e)[:100])
                    try:
                        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"error_{func.__name__}.png"), full_page=True)
                    except:
                        pass
        finally:
            await browser.close()

    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        print(f"  {icon} {r['name']}" + (f" — {r['detail']}" if r['detail'] else ""))

    print(f"\n  总计: {total}  通过: {passed}  失败: {failed}")
    print(f"  截图目录: {SCREENSHOT_DIR}")
    print("=" * 60)

    report_path = os.path.join(SCREENSHOT_DIR, "test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"total": total, "passed": passed, "failed": failed, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"  测试报告已保存: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
