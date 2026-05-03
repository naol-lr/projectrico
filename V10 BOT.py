import asyncio
import re
import os
import time
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from playwright.async_api import async_playwright

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

client = TelegramClient("signal_session", API_ID, API_HASH)

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
                        await asyncio.sleep(0.5)
        except: pass

    async def safe_click(self, selector, timeout=10000):
        """Standardized click with popup handling and retry."""
        try:
            await self.handle_popups()
            locator = self.page.locator(selector).first
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.click(force=True, timeout=timeout)
            return True
        except Exception as e:
            # Try one more time after a forced popup check and escape
            await self.page.keyboard.press("Escape")
            await self.handle_popups()
            try:
                locator = self.page.locator(selector).first
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
        """Robust balance extraction with retries and comma handling"""
        for _ in range(5):
            try:
                selectors = ["span.js-balance-demo", ".balance-info-block__balance", ".balance-value"]
                for selector in selectors:
                    locator = self.page.locator(selector).first
                    if await locator.is_visible(timeout=1000):
                        text = await locator.inner_text()
                        clean_text = re.sub(r'[^\d.]', '', text)
                        if clean_text: return float(clean_text)
                await asyncio.sleep(0.5)
            except: pass
        return 0.0

    async def verify_result_via_history(self, asset_name):
        """Checks the 'Closed Trades' panel for the actual profit of the last trade for a specific asset."""
        try:
            await self.page.keyboard.press("Alt+T") 
            await asyncio.sleep(3) 
            
            # Find the first history item that matches the asset name
            items = self.page.locator(".closed-trades-list__item")
            count = await items.count()
            
            for i in range(count):
                item = items.nth(i)
                asset_label = await item.locator(".pair").inner_text()
                if asset_name.replace(" OTC", "").replace("/", "").upper() in asset_label.replace("/", "").upper():
                    profit_text = await item.locator(".profit").inner_text()
                    val = float(re.sub(r'[^\d.]', '', profit_text))
                    await self.page.keyboard.press("Alt+T")
                    return "WIN" if val > 0 else "LOSS"
            
            await self.page.keyboard.press("Alt+T")
            return "UNKNOWN"
        except:
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
                "--disable-blink-features=AutomationControlled"
            ]
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Less aggressive blocking - some icons/UI elements might be svgs or small images
        await self.page.route("**/*.{mp4,webm,avi,ogg}", lambda route: route.abort())

        for attempt in range(3):
            try:
                await self.notify(f"🚀 Navigation Attempt {attempt+1}...")
                # Full 'load' state is safer for complex SPAs
                await self.page.goto(POCKET_URL, wait_until="load", timeout=120000)
                await asyncio.sleep(30) # Give it more time to settle
                
                await self.page.keyboard.press("Escape")
                await self.handle_popups()
                
                # Wait for the main trading container to be visible
                try:
                    await self.page.wait_for_selector(".traderoom", timeout=30000)
                except:
                    await self.notify("⚠️ Dashboard container not found, continuing anyway...")

                bal = await self.get_balance()
                if bal > 0 or await self.page.locator(".balance-info-block").is_visible():
                    self.is_ready = True
                    await self.notify(f"✅ ENGINE READY. Initial Balance: ${bal}")
                    await self.snap("Engine_Startup")
                    return
                
            except Exception as e:
                await self.notify(f"⚠️ Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(5)
        
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
                await asyncio.sleep(1)
                await self.snap(f"Slot_{slot_id}_Asset_Search")
                
                # The search field is usually global or opens in a modal
                search_locator = self.page.locator("input.search__field").first
                await search_locator.wait_for(state="visible", timeout=10000)
                await search_locator.click()
                await search_locator.fill(query)
                await asyncio.sleep(2)

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
            if is_mg:
                # Set MG amount - targeting the correct input for the slot
                amount_input = self.page.locator(amount_selector)
                curr_val_str = await amount_input.get_attribute("value") or "1"
                # Clean commas for calculation
                curr_val = float(curr_val_str.replace(",", ""))
                await amount_input.fill(str(round(curr_val * 2.2, 2))) # Standard MG multiplier

            await self.notify(f"⏲️ [Slot {slot_id}] Precision wait for {target_h:02d}:{target_m:02d}:00")
            
            while True:
                now = datetime.now(SIGNAL_TZ)
                if now.hour == target_h and now.minute == target_m:
                    break
                if (now.hour == target_h and now.minute > target_m) or now.hour > target_h:
                    break
                await asyncio.sleep(0.01)

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
                            start_bal = curr_bal
                            await engine.internal_precision_fire(sig["direction"], mh, mm, slot_id, is_mg=True)
                            await engine.snap(f"Slot_{slot_id}_MG_Entry_{mg_time}")

                # Reset logic for the slot
                await asyncio.sleep(40) # Wait 40s for the last trade to settle
                amount_input = engine.page.locator(f"#put-call-buttons-chart-{slot_id} .block--bet-amount input")
                await amount_input.fill("1") # Reset to base amount
                await engine.notify(f"📊 [Slot {slot_id}] Cycle Finished. Bal: ${await engine.get_balance()}")
                await engine.snap(f"Slot_{slot_id}_Cycle_Finished")
        finally:
            await engine.release_slot(slot_id)

# =========================
# ⏱️ SMART PARSING
# =========================
def parse_signal(text, channel_id):
    try:
        # Require asset and at least one time indicator in the message
        asset_match = re.search(r"([A-Z]{3}/?[A-Z]{3})", text)
        time_match = re.search(r"(\d{2}:\d{2})", text)
        
        # Only proceed if we have both an asset and a time, and a directional keyword
        direction_keywords = ["SELL", "PUT", "BUY", "CALL", "🔴", "🟥", "🔽", "DOWN", "🟢", "🟩", "🔼", "UP"]
        if not (asset_match and time_match and any(keyword in text.upper() for keyword in direction_keywords)):
            return None
            
        asset = asset_match.group(1).replace("/", "") + (" OTC" if "OTC" in text.upper() else "")
        direction = "SELL" if any(x in text.upper() for x in ["SELL", "PUT", "🔴", "🟥", "🔽", "DOWN"]) else "BUY"
        times = re.findall(r"(\d{2}:\d{2})", text)
        
        raw_h, raw_m = map(int, times[0].split(":"))
        now = datetime.now(SIGNAL_TZ)
        
        best_shift = 0
        found = False
        for shift in range(-12, 13):
            test_h = (raw_h + shift) % 24
            target = now.replace(hour=test_h, minute=raw_m, second=0, microsecond=0)
            diff = (target - now).total_seconds()
            if diff < -43200: target += timedelta(days=1)
            elif diff > 43200: target -= timedelta(days=1)
            diff = (target - now).total_seconds()
            if 0 <= diff <= 2700: 
                best_shift = shift
                found = True
                break
        
        local_entry = f"{(raw_h + (best_shift if found else 0)) % 24:02d}:{raw_m:02d}"
        
        # Fixed MG mapping - avoid map indexing errors
        mg = []
        for t_str in times[1:]:
            parts = t_str.split(':')
            if len(parts) == 2:
                mh = int(parts[0])
                mm = int(parts[1])
                shifted_h = (mh + (best_shift if found else 0)) % 24
                mg.append(f"{shifted_h:02d}:{mm:02d}")
            
        return {"asset": asset, "direction": direction, "entry": local_entry, "mg": mg}
    except Exception as e: 
        print(f"Parse Error: {e}")
        return None

@client.on(events.NewMessage(chats=ALL_CHANNELS))
async def handler(event):
    msg = str(event.message.message or "")
    # Restrict triggering to messages that clearly look like trade signals
    if any(x in msg.upper() for x in ["ENTRY", "BUY", "SELL", "PUT", "CALL"]) and any(re.findall(r"\d{2}:\d{2}", msg)):
        sig = parse_signal(msg, event.chat_id)
        if sig: asyncio.create_task(signal_task(sig))

async def main():
    await client.start()
    await engine.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
