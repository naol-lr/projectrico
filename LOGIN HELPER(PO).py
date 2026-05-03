import asyncio
from playwright.async_api import async_playwright

async def manual_login():
    async with async_playwright() as p:
        print("🚀 Launching browser...")
        
        # Using a standard User Agent helps bypass some socket/security blocks
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        context = await p.chromium.launch_persistent_context(
            user_data_dir="my_profile",
            headless=False,
            user_agent=user_agent,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--ignore-certificate-errors" # Bypasses potential SSL socket hangs
            ]
        )

        page = context.pages[0]
        # Set a longer timeout for slow Chromebook connections
        page.set_default_navigation_timeout(90000) 

        print("🌍 Attempting to reach Pocket Option...")
        try:
            # Try login page first
            await page.goto("https://pocketoption.com/en/login/", wait_until="domcontentloaded")
        except Exception as e:
            print(f"⚠️ Login page failed, trying mirror/main page... ({e})")
            await page.goto("https://po6.cash/en/login/", wait_until="domcontentloaded")

        print("\n--- ACTION REQUIRED ---")
        print("1. Log in manually.")
        print("2. Once you are at the DASHBOARD/CHART, stay there for 10 seconds.")
        print("3. CLOSE THE BROWSER WINDOW to save.")
        print("------------------------\n")

        while True:
            try:
                if len(context.pages) == 0:
                    break
                await asyncio.sleep(1)
            except:
                break

        print("✅ Session saved to 'my_profile'!")
        await context.close()

if __name__ == "__main__":
    asyncio.run(manual_login())