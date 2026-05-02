import asyncio
import logging
import time
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from database import db
from .regix import is_allowed_message, custom_caption, media
from .test import get_configs, CLIENT, start_clone_bot, parse_buttons
from config import temp

logger = logging.getLogger(__name__)

# Cache for pairs
PAIRS_CACHE = {}
# Per-user queues: {user_id: asyncio.Queue}
USER_QUEUES = {}
# Media group buffers: {(user_id, media_group_id): [messages]}
MG_BUFFERS = {}

async def update_pairs_cache():
    global PAIRS_CACHE
    try:
        all_pairs = await db.get_all_pairs().to_list(length=1000)
        new_cache = {}
        for pair in all_pairs:
            sid = pair['source_id']
            if sid not in new_cache:
                new_cache[sid] = []
            new_cache[sid].append(pair)
        PAIRS_CACHE = new_cache
    except Exception as e:
        logger.error(f"Error updating pairs cache: {e}")

async def safe_forward(client, user_id, target_id, message, configs):
    while True:
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
            return True
        except FloodWait as e:
            logger.warning(f"FloodWait for user {user_id}: {e.value}s. Sleeping...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"Forward error for user {user_id}: {e}")
            return False

async def safe_forward_mg(client, user_id, target_id, messages, configs):
    while True:
        try:
            if configs.get('forward_tag'):
                await client.forward_messages(
                    target_id,
                    messages[0].chat.id,
                    [m.id for m in messages]
                )
            else:
                await client.copy_media_group(
                    target_id,
                    messages[0].chat.id,
                    [m.id for m in messages]
                )
            return True
        except FloodWait as e:
            logger.warning(f"FloodWait for user {user_id} (MG): {e.value}s. Sleeping...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"MG forward error for user {user_id}: {e}")
            return False

async def user_worker(user_id, client):
    queue = USER_QUEUES[user_id]
    logger.info(f"Worker started for user {user_id}")
    while True:
        data, pairs = await queue.get()
        try:
            configs = await get_configs(user_id)
            if not configs.get('auto_fwd', False):
                continue
            
            for pair in pairs:
                target_id = pair['target_id']
                if isinstance(data, list):
                    # Media Group
                    valid_msgs = [m for m in data if is_allowed_message(m, configs)]
                    if valid_msgs:
                        await safe_forward_mg(client, user_id, target_id, valid_msgs, configs)
                else:
                    # Single Message
                    if is_allowed_message(data, configs):
                        await safe_forward(client, user_id, target_id, data, configs)
            
            # Small delay to prevent hitting rate limits too fast
            await asyncio.sleep(1) 
            
        except Exception as e:
            logger.error(f"Worker error for user {user_id}: {e}")
        finally:
            queue.task_done()

async def wait_and_queue_mg(key, pairs, owner_id):
    await asyncio.sleep(2) # Wait for all parts to arrive
    if key in MG_BUFFERS:
        messages = MG_BUFFERS.pop(key)
        # Sort messages by ID to ensure sequence within MG
        messages.sort(key=lambda x: x.id)
        await USER_QUEUES[owner_id].put((messages, pairs))

@Client.on_message(filters.group | filters.channel, group=10)
async def auto_forward_handler(client, message):
    owner_id = getattr(client, "owner_id", None)
    if not owner_id:
        return

    configs = await get_configs(owner_id)
    if not configs.get('auto_fwd', False):
        return

    if not PAIRS_CACHE:
        await update_pairs_cache()
    
    chat_id = message.chat.id
    all_chat_pairs = PAIRS_CACHE.get(chat_id) or PAIRS_CACHE.get(str(chat_id))
    if not all_chat_pairs:
        return
        
    pairs = [p for p in all_chat_pairs if p['user_id'] == owner_id]
    if not pairs:
        return

    if owner_id not in USER_QUEUES:
        USER_QUEUES[owner_id] = asyncio.Queue()
        asyncio.create_task(user_worker(owner_id, client))

    if message.media_group_id:
        key = (owner_id, message.media_group_id)
        if key not in MG_BUFFERS:
            MG_BUFFERS[key] = [message]
            asyncio.create_task(wait_and_queue_mg(key, pairs, owner_id))
        else:
            MG_BUFFERS[key].append(message)
    else:
        await USER_QUEUES[owner_id].put((message, pairs))

async def refresh_cache_loop():
    while True:
        await update_pairs_cache()
        await asyncio.sleep(60)

async def start_user_clients(bot):
    all_pairs = await db.get_all_pairs().to_list(length=1000)
    uids = set(p['user_id'] for p in all_pairs)
    
    for uid in uids:
        bot_data = await db.get_bot(uid)
        if bot_data:
            try:
                user_client = CLIENT().client(bot_data)
                user_client.plugins = {"root": "plugins"}
                user_client.owner_id = uid
                await start_clone_bot(user_client)
                logger.info(f"Started auto-forward client for user {uid}")
            except Exception as e:
                logger.error(f"Failed to start auto-forward client for {uid}: {e}")

# This will be called once when the main bot starts
# Note: In Pyrogram, we can't easily run a background task from a plugin 
# unless we use a specific trick or call it from bot.py
