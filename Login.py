from telethon import TelegramClient

api_id = 38859657
api_hash = "YOUR_API_HASH"

client = TelegramClient("signal_session", api_id, api_hash)

with client:
    client.start()
    print("✅ Logged in as USER")