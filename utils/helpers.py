"""
utils/helpers.py — Shared utility functions for Genesis Peptide Store bot.
"""
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
) -> Optional[Message]:
    """Send a message with error handling. Returns None on failure."""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramForbiddenError:
        logger.warning("Bot was blocked by user %d", chat_id)
    except TelegramBadRequest as e:
        logger.error("Bad request sending to %d: %s", chat_id, e)
    except Exception as e:
        logger.exception("Unexpected error sending to %d: %s", chat_id, e)
    return None


async def safe_send_photo(
    bot: Bot,
    chat_id: int,
    photo: str,
    caption: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
) -> Optional[Message]:
    """Send a photo with caption and error handling. Returns None on failure."""
    try:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramBadRequest as e:
        logger.error("Bad request sending photo to %d: %s | photo_id=%s", chat_id, e, photo)
    except TelegramForbiddenError:
        logger.warning("Bot was blocked by user %d", chat_id)
    except Exception as e:
        logger.exception("Unexpected error sending photo to %d: %s", chat_id, e)
    return None


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
) -> bool:
    """Edit message text with error handling. Returns True on success."""
    try:
        await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.error("Error editing message: %s", e)
    except Exception as e:
        logger.exception("Unexpected error editing message: %s", e)
    return False
