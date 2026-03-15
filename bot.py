import base64
import logging
from telegram import Update # type: ignore
from telegram.constants import ChatAction # type: ignore
from telegram.ext import ( # type: ignore
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
import config # type: ignore
from llm import generate_response # type: ignore

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# In-memory session management
# user_sessions[user_id] = [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]
user_sessions = {}


from datetime import datetime

def get_session(user_id: int) -> list:
    """Retrieves or initializes the chat session for a user."""
    if user_id not in user_sessions:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Initializing with a system prompt if desired
        user_sessions[user_id] = [
            {"role": "system", "content": f"You are a helpful and friendly assistant. The current date and time is {now_str}."}
        ]
    return user_sessions[user_id]


def reset_session(user_id: int):
    """Resets the chat session for a user."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_sessions[user_id] = [
        {"role": "system", "content": f"You are a helpful and friendly assistant. The current date and time is {now_str}."}
    ]


async def check_whitelist(update: Update) -> bool:
    """Checks if the user is in the ALLOWED_USER_IDS list."""
    user = update.effective_user
    if user is None:
        return False
    if config.ALLOWED_USER_IDS and user.id not in config.ALLOWED_USER_IDS:
        logger.warning(
            f"Unauthorized access attempt from user: {user.id} ({user.username})"
        )
        await update.message.reply_text("권한이 없습니다.")
        return False
    return True


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_whitelist(update):
        return
    reset_session(update.effective_user.id)
    await update.message.reply_text("안녕! 대화가 초기화되었어. 무엇을 도와줄까?")


async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_whitelist(update):
        return
    reset_session(update.effective_user.id)
    await update.message.reply_text(
        "대화 문맥이 초기화되었어. 새로운 주제로 이야기해보자!"
    )


async def send_long_message(update: Update, text: str):
    """
    Helper function to send messages that exceed Telegram's 4096 character limit.
    Splits the text into chunks and sends them sequentially.
    """
    MAX_LENGTH = 4050 # Leaving a small buffer
    for i in range(0, len(text), MAX_LENGTH):
        chunk = text[i:i + MAX_LENGTH] # type: ignore
        await update.message.reply_text(chunk)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_whitelist(update):
        return

    user_id = update.effective_user.id
    user_text = update.message.text
    session = get_session(user_id)

    # Send typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Append user message
    session.append({"role": "user", "content": user_text})

    # Generate response from Local LLM
    bot_response = await generate_response(session)

    # Append bot response
    session.append({"role": "assistant", "content": bot_response})

    # Send reply in chunks if necessary
    await send_long_message(update, bot_response)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_whitelist(update):
        return

    user_id = update.effective_user.id
    session = get_session(user_id)

    # Send typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Get the highest resolution photo
    photo_file = await update.message.photo[-1].get_file()

    # Download photo as byte array
    byte_array = await photo_file.download_as_bytearray()

    # Convert to base64 string
    base64_image = base64.b64encode(byte_array).decode("utf-8")
    mime_type = "image/jpeg"  # Telegram photos are mostly JPEG
    image_url = f"data:{mime_type};base64,{base64_image}"

    caption = update.message.caption

    # Construct combined content (vision message format)
    content = []

    if caption:
        content.append({"type": "text", "text": caption})
    else:
        # Fallback question if no caption is provided
        content.append(
            {
                "type": "text",
                "text": "오빠, 이 이미지로 뭘 도와줄까? 요약이나 분석 필요해?",
            }
        )

    content.append({"type": "image_url", "image_url": {"url": image_url}})

    session.append({"role": "user", "content": content})

    bot_response = await generate_response(session)

    session.append({"role": "assistant", "content": bot_response})

    # Send reply in chunks if necessary
    await send_long_message(update, bot_response)


if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        exit(1)

    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("new", new_cmd))

    # Message handlers
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Bot is starting...")
    application.run_polling()
