import asyncio
import re
import os
import time
import random
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from playwright.async_api import async_playwright
import os

# ==========================================
# 🔐 CONFIGURATION
# ==========================================
API_ID = int(os.environ.get("API_ID", 38859657))
API_HASH = os.environ.get("API_HASH", "96c90da3f365759523898fae8ee7fdc7")

# Channels to monitor
ALL_CHANNELS = [-1002074799242, -1003584508030, -1002281357812]

MY_USER_ID = int(os.environ.get("MY_USER_ID", 6045847400))
POCKET_URL = "https://pocketoption.com/en/cabinet/demo-quick-high-low/"

# Base timezone for the script logic (UTC-4 is common for signals)
SIGNAL_TZ = timezone(timedelta(hours=-4)) 

SESSION_STRING = os.environ.get("SESSION_STRING")

# Only use StringSession if a string is provided; otherwise, fallback to file
if SESSION_STRING:
    print(f"🚀 Using StringSession. Length: {len(SESSION_STRING)}")
    try:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    except Exception as e:
        print(f"❌ Failed to initialize StringSession: {e}")
        print("Falling back to file-based session.")
        client = TelegramClient("railway_session", API_ID, API_HASH)
else:
    print("📁 Using file-based session.")
    client = TelegramClient("railway_session", API_ID, API_HASH)

# =========================
# 🤖 ULTIMATE TRADE ENGINE
# =========================
class TradeEngine:
    def __init__(self, t_client):
        self.pw = None
        self.context = None
        self.page = None
        self.semaphore = asyncio.Semaphore(4)
        self.available_slots = {1, 2, 3, 4}
        self.slot_lock = asyncio.Lock()
        self.search_lock = asyncio.Lock()
        self.t_client = t_client
        self.is_ready = False
        os.makedirs("screenshots", exist_ok=True)

    async def get_slot(self):
        async with self.slot_lock:
            if not self.available_slots:
                return None
            slot = sorted(list(self.available_slots))[0]
            self.available_slots.remove(slot)
            return slot

    async def release_slot(self, slot):
        async with self.slot_lock:
            self.available_slots.add(slot)

    async def handle_popups(self):
        """Checks for and closes common popups/ads."""
        try:
            selectors = [
                "a.modal-close", ".modal-close", "svg.modal-close-icon", 
                "[data-modal-close]", "[data-dismiss='modal']", ".btn-close"
            ]
            for selector in selectors:
                locators = self.page.locator(selector)
                count = await locators.count()
                for i in range(count):
                    locator = locators.nth(i)
                    if await locator.is_visible(timeout=500):
                        await self.notify(f"🧹 Closing popup ({selector})...")
                        await locator.click(force=True)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
        except: pass

    async def safe_click(self, selector, timeout=10000):
        """Standardized click with popup handling and retry with randomized delay."""
        try:
            await self.handle_popups()
            locator = self.page.locator(selector).first
            await locator.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await locator.click(force=True, timeout=timeout)
            return True
        except Exception as e:
            await self.page.keyboard.press("Escape")
            await self.handle_popups()
            try:
                locator = self.page.locator(selector).first
                await asyncio.sleep(random.uniform(0.2, 0.6))
                await locator.click(force=True, timeout=timeout)
                return True
            except:
                return False

    async def ensure_multi_chart_layout(self):
        """No longer needed as the layout is set to 4-chart by default."""
        pass

    async def notify(self, text, file_path=None):
        stamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{stamp}] {text}")
        try:
            if file_path and os.path.exists(file_path):
                await self.t_client.send_file(MY_USER_ID, file_path, caption=text)
            else:
                await self.t_client.send_message(MY_USER_ID, text)
        except: pass

    async def snap(self, name):
        try:
            path = f"screenshots/{name}_{datetime.now().strftime('%H%M%S')}.png"
            await self.page.screenshot(path=path)
            await self.notify(f"📸 {name}", file_path=path)
        except: pass

    async def get_balance(self):
        """Robust balance extraction with retries and verification of value."""
        selectors = [
            "span.js-balance-demo", 
            ".balance-info-block__balance", 
            ".balance-value", 
            ".cabinet-balance__value", 
            ".user-balance-value"
        ]
        
        for attempt in range(8):
            try:
                for selector in selectors:
                    locators = self.page.locator(selector)
                    count = await locators.count()
                    for i in range(count):
                        locator = locators.nth(i)
                        if await locator.is_visible(timeout=2000):
                            text = (await locator.inner_text()).strip()
                            clean_text = re.sub(r'[^\d.]', '', text.replace(',', ''))
                            if clean_text:
                                try:
                                    return float(clean_text)
                                except ValueError:
                                    continue
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"Balance Extraction Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(1.0)
        
        await self.snap("Balance_Extraction_Failure")
        raise Exception("Failed to extract a valid balance from the UI")

    async def verify_result_via_history(self, asset_name):
        """Checks the 'Closed Trades' panel with extended wait and robust validation."""
        try:
            await self.page.keyboard.press("Alt+T") 
            await asyncio.sleep(8) # Increased wait for trade settlement
            
            # Find the first history item that matches the asset name
            items = self.page.locator(".closed-trades-list__item")
            count = await items.count()
            
            # Check the last 3 items to be sure we find the most recent trade
            for i in range(min(count, 3)):
                item = items.nth(i)
                asset_label = await item.locator(".pair").inner_text()
                if asset_name.replace(" OTC", "").replace("/", "").upper() in asset_label.replace("/", "").upper():
                    profit_text = await item.locator(".profit").inner_text()
                    # Look for actual positive/negative profit value
                    val = float(re.sub(r'[^\d.-]', '', profit_text))
                    await self.page.keyboard.press("Alt+T")
                    return "WIN" if val > 0 else "LOSS"
            
            await self.page.keyboard.press("Alt+T")
            return "UNKNOWN"
        except Exception as e:
            print(f"History Check Error: {e}")
            try: await self.page.keyboard.press("Alt+T")
            except: pass
            return "UNKNOWN"

    async def start(self):
        await self.notify("🌐 Booting V9-GOLD 'Hyper-Smart' Engine (Multi-Chart Support)...")
        self.pw = await async_playwright().start()
        self.context = await self.pw.chromium.launch_persistent_context(
            user_data_dir="my_profile",
            headless=True,
            viewport={'width': 1920, 'height': 1080},
            args=[
                "--no-sandbox", 
                "--disable-gpu", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080"
            ]
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.set_viewport_size({"width": 1920, "height": 1080})
        
        await self.page.route("**/*.{mp4,webm,avi,ogg}", lambda route: route.abort())

        for attempt in range(3):
            try:
                await self.notify(f"🚀 Navigation Attempt {attempt+1}...")
                await self.page.goto(POCKET_URL, wait_until="domcontentloaded", timeout=120000)
                await self.notify(f"DEBUG: Navigated to {self.page.url}")
                if "login" in self.page.url:
                    await self.notify("DEBUG: Attempting to snap STUCK_AT_LOGIN"); await self.snap("STUCK_AT_LOGIN"); await self.notify("DEBUG: Snap complete")
                    await self.notify("❌ CRITICAL: Bot is at LOGIN page")
                await asyncio.sleep(20) 
                
                await self.handle_popups()
                await self.page.keyboard.press("Escape")
                await self.handle_popups()
                
                traderoom_visible = await self.page.locator(".traderoom, .cabinet-layout").is_visible(timeout=45000)
                if not traderoom_visible:
                    await self.notify("⚠️ Dashboard not found, attempting to force refresh...")
                    await self.page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(15)

                bal = await self.get_balance()
                self.is_ready = True
                await self.notify(f"✅ ENGINE READY. Initial Balance: ${bal}")
                await self.snap("Engine_Startup")
                return
                
            except Exception as e:
                await self.notify(f"⚠️ Attempt {attempt+1} failed: {e}")
                await self.snap(f"Startup_Failure_Attempt_{attempt+1}")
                await asyncio.sleep(10)
        
        await self.notify("❌ Engine failed to stabilize after 3 attempts.")

    async def internal_switch_asset(self, asset_name, slot_id):
        """Logic for switching asset on a specific chart slot."""
        try:
            await self.notify(f"🔍 [Slot {slot_id}] Switching to {asset_name}...")
            query = asset_name.replace(" OTC", "").replace("/", "").strip()
            is_otc = "OTC" in asset_name.upper()
            
            # Target the pair selector for the specific slot
            pair_selectors = [
                f".chart-item:nth-of-type({slot_id}) .pair",
                f".chart-item:nth-of-type({slot_id}) .asset-selector",
                f".chart-item:nth-of-type({slot_id}) .trading-panel__pair"
            ]

            async with self.search_lock:
                clicked = False
                for selector in pair_selectors:
                    if await self.safe_click(selector):
                        clicked = True
                        break

                if not clicked:
                    raise Exception(f"Could not click any pair selector for Slot {slot_id}")
                await asyncio.sleep(random.uniform(0.5, 1.2))
                await self.snap(f"Slot_{slot_id}_Asset_Search")
                
                # The search field is usually global or opens in a modal
                search_locator = self.page.locator("input.search__field").first
                await search_locator.wait_for(state="visible", timeout=10000)
                await search_locator.click()
                await search_locator.fill(query)
                await asyncio.sleep(random.uniform(0.8, 1.5))

                items = self.page.locator("ul.assets-block__alist li.alist__item")
                count = await items.count()
                
                for i in range(count):
                    try:
                        label_el = items.nth(i).locator(".alist__label")
                        label = (await label_el.inner_text(timeout=2000)).upper()
                        if query.upper() in label.replace("/", ""):
                            if is_otc == ("OTC" in label):
                                await items.nth(i).click(force=True)
                                await asyncio.sleep(1)
                                await self.notify(f"✅ [Slot {slot_id}] Asset {asset_name} Selected")
                                await self.snap(f"Slot_{slot_id}_Asset_Selected")
                                return True
                    except: continue
            
            await self.notify(f"⚠️ [Slot {slot_id}] Asset {asset_name} NOT found")
            await self.snap(f"Slot_{slot_id}_Asset_Not_Found")
            return False
        except Exception as e:
            await self.notify(f"❌ [Slot {slot_id}] Switch Error: {e}")
            await self.snap(f"Slot_{slot_id}_Switch_Error")
            return False

    async def internal_precision_fire(self, direction, target_h, target_m, slot_id, is_mg=False):
        """Logic for precision firing using slot-specific selectors."""
        try:
            amount_selector = f"#put-call-buttons-chart-{slot_id} .block--bet-amount input"
            amount_input = self.page.locator(amount_selector)
            
            if not is_mg:
                # First entry: force base stake
                await amount_input.fill("5.0")
            else:
                # MG: use standard multiplier logic
                curr_val_str = await amount_input.get_attribute("value") or "5"
                curr_val = float(curr_val_str.replace(",", ""))
                await amount_input.fill(str(round(curr_val * 2.2, 2)))
            
            await asyncio.sleep(random.uniform(0.2, 0.5))

            await self.notify(f"⏲️ [Slot {slot_id}] Precision wait for {target_h:02d}:{target_m:02d}:00")
            
            while True:
                now = datetime.now(SIGNAL_TZ)
                # Add a tiny bit of random buffer time before the target minute
                if now.hour == target_h and now.minute == target_m and now.second >= random.randint(0, 2):
                    break
                if (now.hour == target_h and now.minute > target_m) or now.hour > target_h:
                    break
                await asyncio.sleep(random.uniform(0.05, 0.15))

            # Targeted CSS Click using slot-specific ID
            btn_selector = f"#put-call-buttons-chart-{slot_id} .btn-{'call' if 'BUY' in direction.upper() else 'put'}"
            await self.page.locator(btn_selector).click(force=True)
            
            await self.notify(f"⚡ [Slot {slot_id}] {direction} FIRED AT {datetime.now(SIGNAL_TZ).strftime('%H:%M:%S.%f')}")
            await self.snap(f"Slot_{slot_id}_{direction}_Fired")
        except Exception as e:
            await self.notify(f"⚠️ [Slot {slot_id}] Fire Error: {e}")
            await self.snap(f"Slot_{slot_id}_Fire_Error")

# =========================
# 📡 SIGNAL PROCESSING
# =========================
engine = TradeEngine(client)

async def signal_task(sig):
    if not engine.is_ready: return
    
    # Wait exactly 10 seconds after receiving the signal
    await asyncio.sleep(10)

    h, m = map(int, sig['entry'].split(":"))
    now = datetime.now(SIGNAL_TZ)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    
    if (target - now).total_seconds() < -43200: target += timedelta(days=1)
    elif (target - now).total_seconds() > 43200: target -= timedelta(days=1)
    
    wait = (target - now).total_seconds()
    if wait < -60 or wait > 7200: return

    # Acquire Semaphore AND Slot
    async with engine.semaphore:
        slot_id = await engine.get_slot()
        if not slot_id:
            await engine.notify("⚠️ No available slots for signal")
            return

        try:
            await engine.notify(f"🎯 [Slot {slot_id}] PROCESSING: {sig['asset']} | {sig['direction']} | {sig['entry']}")
            
            if await engine.internal_switch_asset(sig["asset"], slot_id):
                await engine.snap(f"Slot_{slot_id}_Asset_Loaded_{sig['asset']}")
                
                start_bal = await engine.get_balance()
                await engine.internal_precision_fire(sig["direction"], h, m, slot_id)
                await asyncio.sleep(1)
                await engine.snap(f"Slot_{slot_id}_Entry_{sig['asset']}")

                # Martingale Logic
                for mg_time in sig["mg"]:
                    mh, mm = map(int, mg_time.split(":"))
                    now_mg = datetime.now(SIGNAL_TZ)
                    target_mg = now_mg.replace(hour=mh, minute=mm, second=0, microsecond=0)
                    if (target_mg - now_mg).total_seconds() < -43200: target_mg += timedelta(days=1)
                    
                    m_wait = (target_mg - now_mg).total_seconds()
                    if m_wait > 0:
                        await asyncio.sleep(m_wait + 40) # Wait 40s after trade should have closed
                        
                        history_result = await engine.verify_result_via_history(sig["asset"])
                        curr_bal = await engine.get_balance()
                        
                        await engine.snap(f"Slot_{slot_id}_Result_Check")
                        
                        is_win = (history_result == "WIN") or (history_result == "UNKNOWN" and curr_bal > (start_bal + 0.1))

                        if is_win:
                            await engine.notify(f"💰 [Slot {slot_id}] WIN: {sig['asset']} | Bal: ${curr_bal}")
                            await engine.snap(f"Slot_{slot_id}_Win_{sig['asset']}")
                            break
                        else:
                            await engine.notify(f"🔄 [Slot {slot_id}] LOSS: Running Martingale @ {mg_time}")
                            await engine.internal_precision_fire(sig["direction"], mh, mm, slot_id, is_mg=True)
                            await engine.snap(f"Slot_{slot_id}_MG_Entry_{mg_time}")

                # Reset logic for the slot
                await asyncio.sleep(40) # Wait 40s for the last trade to settle
                amount_input = engine.page.locator(f"#put-call-buttons-chart-{slot_id} .block--bet-amount input")
                await amount_input.fill("5.0") # Reset to base amount
                await engine.notify(f"📊 [Slot {slot_id}] Cycle Finished. Bal: ${await engine.get_balance()}")
                await engine.snap(f"Slot_{slot_id}_Cycle_Finished")
        finally:
            await engine.release_slot(slot_id)

# =========================
# ⏱️ SMART PARSING
# =========================
def parse_signal(text, channel_id):
    """
    Stricter signal parsing for two accepted formats:
    1. 🪙 NZD/USD OTC | ⏳ Expiration 5 minutes | ✅ Entry at 19:15 | 🔴 SELL ...
    2. 🇬🇧 GBP/USD 🇺🇸 OTC | 🕘 Expiration 5M | ⏺ Entry at 01:30 | 🟥 SELL ...
    """
    try:
        # Check for required trigger markers
        if not ("Entry at" in text or "ENTRY AT" in text.upper()):
            return None
        
        # Regex to capture asset, entry time, and direction
        # Matches: ASSET | Time | Direction
        # Support formats like "NZD/USD OTC" or "GBP/USD 🇺🇸 OTC"
        asset_match = re.search(r"([A-Z]{3}/?[A-Z]{3}(?:.*?OTC)?)", text)
        time_match = re.search(r"(?:Entry at|ENTRY AT)\s*(\d{2}:\d{2})", text, re.IGNORECASE)
        direction_match = re.search(r"(SELL|BUY|CALL|PUT)", text, re.IGNORECASE)
        
        if not (asset_match and time_match and direction_match):
            return None
            
        asset_raw = asset_match.group(1).strip()
        # Clean up asset name for the bot's internal selector
        # Remove flags/emojis, normalize "OTC"
        asset = re.sub(r"[^\w/ ]", "", asset_raw).replace(" ", "")
        if "OTC" not in asset.upper() and "OTC" in asset_raw.upper():
            asset += "OTC"
            
        direction = "SELL" if direction_match.group(1).upper() in ["SELL", "PUT"] else "BUY"
        entry_time = time_match.group(1)
        
        # Capture Martingale times
        # Look for patterns like "1️⃣ ... 01:35" or "1. ... 01:35" or just a time on a new line
        mg_times = re.findall(r"(?:\d[️⃣.)])\s*(?:\w+\s+at\s+)?(\d{2}:\d{2})", text)
        
        # Timezone shift logic (assumed to be constant across the session)
        h, m = map(int, entry_time.split(":"))
        now = datetime.now(SIGNAL_TZ)
        
        # Validate that the entry time is in the near future (e.g. next 2 hours)
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if (target - now).total_seconds() < -60: # Past by more than a minute
            target += timedelta(days=1)
        
        # Adjust MG times based on the same shift
        mg = [f"{mh:02d}:{mm:02d}" for mh, mm in [map(int, t.split(":")) for t in mg_times]]
        
        return {"asset": asset, "direction": direction, "entry": entry_time, "mg": mg}
    except Exception as e: 
        print(f"Parse Error: {e}")
        return None

@client.on(events.NewMessage(chats=ALL_CHANNELS))
async def handler(event):
    msg = str(event.message.message or "")
    # Check for signal entry markers
    if ("ENTRY AT" in msg.upper()):
        sig = parse_signal(msg, event.chat_id)
        if sig: asyncio.create_task(signal_task(sig))

async def main():
    # If using StringSession, phone needs to be an empty string to skip prompt
    # If using file-based session, it doesn't need to prompt if session is valid
    await client.start(phone=lambda: '') 
    await engine.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
