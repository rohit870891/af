import asyncio
import logging
from pyrogram import Client, filters
from database import db
from .regix import is_allowed_message, custom_caption, media
from .test import get_configs, CLIENT, start_clone_bot, parse_buttons
from config import temp

logger = logging.getLogger(__name__)

# Cache for pairs to avoid excessive DB queries
# Structure: {source_chat_id: [pair_document, ...]}
PAIRS_CACHE = {}

async def update_pairs_cache():
    global PAIRS_CACHE
    all_pairs = await db.get_all_pairs().to_list(length=1000)
    new_cache = {}
    for pair in all_pairs:
        sid = pair['source_id']
        if sid not in new_cache:
            new_cache[sid] = []
        new_cache[sid].append(pair)
    PAIRS_CACHE = new_cache

@Client.on_message(filters.group | filters.channel, group=10)
async def auto_forward_handler(client, message):
    if not PAIRS_CACHE:
        await update_pairs_cache()
    
    chat_id = message.chat.id
    pairs = PAIRS_CACHE.get(chat_id) or PAIRS_CACHE.get(str(chat_id))
    
    if not pairs:
        return

    for pair in pairs:
        user_id = pair['user_id']
        target_id = pair['target_id']
        
        # Check if the message is coming from the user's own client to avoid loops
        # if message.from_user and message.from_user.id == client.me.id: continue

        configs = await get_configs(user_id)
        
        if not is_allowed_message(message, configs):
            continue
        
        try:
            if configs.get('forward_tag'):
                await message.forward(target_id)
            else:
                caption = configs.get('caption')
                new_caption = custom_caption(message, caption)
                button_raw = configs.get('button')
                button = parse_buttons(button_raw) if button_raw else None
                
                await message.copy(
                    target_id,
                    caption=new_caption,
                    reply_markup=button,
                    protect_content=configs.get('protect')
                )
        except Exception as e:
            logger.error(f"Auto forward error for user {user_id} from {chat_id} to {target_id}: {e}")

# Task to refresh cache periodically
async def refresh_cache_loop():
    while True:
        await update_pairs_cache()
        await asyncio.sleep(60) # Refresh every minute

# Mechanism to start user clients
async def start_user_clients(bot):
    all_pairs = await db.get_all_pairs().to_list(length=1000)
    uids = set(p['user_id'] for p in all_pairs)
    
    for uid in uids:
        bot_data = await db.get_bot(uid)
        if bot_data:
            try:
                # We start the client using the same plugins so it also runs this handler
                user_client = CLIENT().client(bot_data)
                # Ensure it loads plugins
                user_client.plugins = {"root": "plugins"}
                await start_clone_bot(user_client)
                logger.info(f"Started auto-forward client for user {uid}")
            except Exception as e:
                logger.error(f"Failed to start auto-forward client for {uid}: {e}")

# This will be called once when the main bot starts
# Note: In Pyrogram, we can't easily run a background task from a plugin 
# unless we use a specific trick or call it from bot.py
