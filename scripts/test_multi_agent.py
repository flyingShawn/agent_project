import asyncio
from playwright.async_api import async_playwright

async def test_app():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Test 1: Open desk-agent
        print("Test 1: Opening desk-agent...")
        await page.goto("http://localhost:3000/desk-agent")
        await page.wait_for_timeout(3000)
        title = await page.title()
        print(f"  Page title: {title}")
        
        # Check quick options are desk-agent specific
        quick_options = await page.query_selector_all(".quick-option-card")
        if quick_options:
            first_option = await quick_options[0].text_content()
            print(f"  First quick option: {first_option}")
        
        # Check ops report button is visible (desk-agent has reports)
        ops_button = await page.query_selector('button[title="运维简报"]')
        print(f"  Ops report button visible: {ops_button is not None}")
        
        # Test 2: Send a chat message
        print("\nTest 2: Sending chat message to desk-agent...")
        input_box = await page.query_selector('textarea, input[type="text"], [contenteditable="true"]')
        if not input_box:
            input_box = await page.query_selector(".chat-input textarea")
        if not input_box:
            print("  Could not find input box, trying placeholder...")
            input_box = await page.query_selector('[placeholder*="发消息"]')
        
        if input_box:
            await input_box.click()
            await input_box.fill("查看客户端在线状态")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(10000)
            
            # Check for response
            messages = await page.query_selector_all(".message-bubble, .assistant-message, [class*='message']")
            print(f"  Messages found: {len(messages)}")
        else:
            print("  Input box not found")
        
        # Test 3: Switch to ticket-agent
        print("\nTest 3: Switching to ticket-agent...")
        await page.goto("http://localhost:3000/ticket-agent")
        await page.wait_for_timeout(3000)
        
        # Check quick options are ticket-agent specific
        quick_options = await page.query_selector_all(".quick-option-card")
        if quick_options:
            first_option = await quick_options[0].text_content()
            print(f"  First quick option: {first_option}")
        
        # Check ops report button is NOT visible (ticket-agent has no reports)
        ops_button = await page.query_selector('button[title="运维简报"]')
        print(f"  Ops report button visible: {ops_button is not None}")
        
        # Test 4: Send chat to ticket-agent
        print("\nTest 4: Sending chat message to ticket-agent...")
        input_box = await page.query_selector('[placeholder*="发消息"]')
        if not input_box:
            input_box = await page.query_selector('textarea')
        
        if input_box:
            await input_box.click()
            await input_box.fill("最近一周有多少工单")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(10000)
            print("  Message sent to ticket-agent")
        else:
            print("  Input box not found")
        
        # Take screenshot
        await page.screenshot(path="test_screenshot.png")
        print("\nScreenshot saved to test_screenshot.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_app())
