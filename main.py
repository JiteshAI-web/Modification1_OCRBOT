
import os
import time
import re
import logging
import requests
import uuid
import base64
import threading
import numpy as np
from io import BytesIO
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from word2number import w2n

# OCR Libraries
from PIL import Image, ImageEnhance, ImageFilter
from paddleocr import PaddleOCR
import cv2

# Flask apps
from flask import Flask
from voucher import voucher_app, run_voucher_app, get_last_24h_status

# DB operations
from database import init_db, insert_extracted_receipt, insert_or_update_brochure, register_user, get_user_by_email

from apscheduler.schedulers.background import BackgroundScheduler

# Load environment
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# State management
user_images = {}
user_state = {}
CHAT_IDS = [-1003283341507]

# Initialize PaddleOCR with optimized settings
logger.info("Initializing PaddleOCR...")
try:
    ocr_engine = PaddleOCR(
        use_angle_cls=True,
        lang='en',
        show_log=False,
        use_gpu=False,
        det_db_thresh=0.2,
        det_db_box_thresh=0.3,
        rec_batch_num=8,
        drop_score=0.3
    )
    logger.info("✅ PaddleOCR initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize PaddleOCR: {e}")
    raise


# ---------- Keyboards ----------
def main_category_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 UPI", callback_data="upi")],
        [InlineKeyboardButton("📄 Voucher", callback_data="voucher")],
        [InlineKeyboardButton("🧾 GST Bill", callback_data="gstbill")]
    ])


def upi_subtype_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F7E3 PhonePe", callback_data="PhonePe"),
         InlineKeyboardButton("\U0001F537 Paytm", callback_data="Paytm"),
         InlineKeyboardButton("\U0001F535 GooglePay", callback_data="GooglePay"),
         InlineKeyboardButton("\U0001F7E2 Others", callback_data="Others")]
    ])


def retry_keyboard(callback_data):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Retry", callback_data=callback_data)]
    ])


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["start"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("📸 Send a receipt image (UPI, Voucher, or GST Bill):", reply_markup=reply_markup)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🖼️ Image received. Processing...", reply_markup=ReplyKeyboardRemove())
        user_id = update.message.from_user.id
        photo = update.message.photo[-1]
        file_id = photo.file_id
        context.user_data["last_file_id"] = file_id
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        user_images[user_id] = file_bytes
        user_state[user_id] = {"stage": "main_category"}
        await update.message.reply_text("🔘 Choose the receipt type:", reply_markup=main_category_keyboard())
    except Exception as e:
        logger.error(f"Image error: {e}")
        await update.message.reply_text("Tap Retry:", reply_markup=retry_keyboard("retry_image_upload"))


# ---------- OCR & Parsing ----------
def preprocess_image_advanced(image):
    """Multi-stage preprocessing for better OCR."""
    try:
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        height, width = img_cv.shape[:2]
        if height < 1800 or width < 1800:
            scale = 1800 / max(height, width)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img_cv = cv2.resize(img_cv, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        
        img_cv = cv2.fastNlMeansDenoisingColored(img_cv, None, 10, 10, 7, 15)
        image = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
        
        image = ImageEnhance.Contrast(image).enhance(1.8)
        image = ImageEnhance.Sharpness(image).enhance(2.0)
        image = ImageEnhance.Brightness(image).enhance(1.1)
        
        return image
    except Exception as e:
        logger.error(f"Preprocessing error: {e}")
        if image.mode != 'RGB':
            return image.convert('RGB')
        return image


def extract_text_from_image(image_stream):
    """Extract text using PaddleOCR."""
    try:
        image = Image.open(image_stream)
        image = preprocess_image_advanced(image)
        img_array = np.array(image)
        
        logger.info(f"Processing image shape: {img_array.shape}")
        
        result = ocr_engine.ocr(img_array, cls=True)
        
        if not result or not result[0]:
            logger.warning("PaddleOCR returned no results")
            return ""
        
        text_blocks = []
        for line in result[0]:
            if line and len(line) >= 2:
                box = line[0]
                text = line[1][0]
                confidence = line[1][1]
                
                if confidence > 0.3:
                    y_coord = box[0][1]
                    text_blocks.append((y_coord, text, confidence))
        
        text_blocks.sort(key=lambda x: x[0])
        full_text = "\n".join([block[1] for block in text_blocks])
        
        logger.info(f"✅ Extracted {len(text_blocks)} blocks, {len(full_text)} chars")
        
        return full_text
    
    except Exception as e:
        logger.error(f"❌ OCR Error: {e}", exc_info=True)
        return ""


def extract_limited_fields(text, category):
    """Extract key fields."""
    amount = extract_amount(text)
    datetime = extract_datetime(text)
    transaction_id = extract_transaction_id(text)
    person_name = extract_person_name(text)
    upi_id = extract_upi_id(text)

    logger.info(f"Amount: {amount} | DateTime: {datetime} | TxnID: {transaction_id}")

    return "\n".join([
        f"• Amount: {amount}",
        f"• Date & Time: {datetime}",
        f"• Transaction ID: {transaction_id}",
        f"• Person Name: {person_name}",
        f"• UPI ID: {upi_id}"
    ])


def is_valid_amount(amount_str):
    try:
        clean = amount_str.replace(',', '').replace(' ', '').strip()
        value = float(clean)
        return 10 <= value <= 100000000
    except:
        return False

def extract_amount(text):
    """Enhanced amount extraction."""
    text = text or ""
    
    # 1. ₹ symbol
    matches = re.findall(r'₹\s*([0-9,]+(?:\.[0-9]{1,2})?)', text)
    for match in matches:
        val = match.replace(',', '').replace(' ', '')
        if is_valid_amount(val):
            try:
                fv = float(val)
                return f"₹{int(fv)}" if fv.is_integer() else f"₹{fv:.2f}".rstrip('0').rstrip('.')
            except:
                continue
    
    # 2. Worded amount
    m = re.search(r'Rupees\s+([A-Za-z\s\-]+?)\s+Only', text, re.IGNORECASE)
    if m:
        try:
            num = w2n.word_to_num(m.group(1).strip().lower())
            return f"₹{int(num)}" if float(num).is_integer() else f"₹{float(num):.2f}"
        except:
            pass
    
    # 3. Comma-formatted
    matches = re.findall(r'\b(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?)\b', text)
    for match in matches:
        val = match.replace(',', '')
        if is_valid_amount(val):
            try:
                fv = float(val)
                return f"₹{int(fv)}" if fv.is_integer() else f"₹{fv:.2f}".rstrip('0').rstrip('.')
            except:
                continue
    
    # 4. After keywords
    m = re.search(r'(?:Amount|Total|INR|Rs\.?|Value|Paid|Payment)\s*[:\-]?\s*([0-9,]+(?:\.[0-9]{1,2})?)', text, re.IGNORECASE)
    if m:
        val = m.group(1).replace(',', '')
        if is_valid_amount(val):
            try:
                fv = float(val)
                return f"₹{int(fv)}" if fv.is_integer() else f"₹{fv:.2f}".rstrip('0').rstrip('.')
            except:
                pass
    
    # 5. Standalone numbers
    matches = re.findall(r'\b([0-9]{3,7}(?:\.[0-9]{1,2})?)\b', text)
    for val in matches:
        if not re.match(r'^(19|20)\d{2}$', val) and is_valid_amount(val):
            try:
                fv = float(val)
                return f"₹{int(fv)}" if fv.is_integer() else f"₹{fv:.2f}"
            except:
                continue
    
    return "Not Found"

def extract_transaction_id(text):
    """Enhanced transaction ID extraction."""
    text = text or ""
    
    # PhonePe T-ID
    m = re.search(r'\b(T\d{18,25})\b', text)
    if m:
        return m.group(1)
    
    # Paytm UPI Ref with space
    m = re.search(r'UPI\s*Ref\.?\s*No[:\s\-]*(\d{6,8}\s+\d{5,6})', text, re.IGNORECASE)
    if m:
        return m.group(1).replace(' ', '')
    
    # Paytm UPI Ref no space
    m = re.search(r'UPI\s*Ref\.?\s*No[:\s\-]*(\d{12,13})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    
    # Generic Transaction ID
    m = re.search(r'Transaction\s*ID\s*[:\-\s]*([A-Z0-9\-]{6,60})', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    
    # UTR
    m = re.search(r'UTR[:\s]+(\d{10,15})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    
    # T-prefix fallback
    m = re.search(r'\b(T\d{15,30})\b', text)
    if m:
        return m.group(1)
    
    # Long number
    matches = re.findall(r'\b(\d{12,15})\b', text)
    for match in matches:
        if not match.startswith(('91', '90', '80', '70', '60')):
            return match
    
    return "Not Found"


def clean_name(name):
    if not name:
        return ""
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip(':.')
    name = re.sub(r'[^A-Za-z0-9 &\.\-]', '', name)
    return name.strip()


def extract_person_name(text):
    text = text or ""
    
    m = re.search(r'Paid\s+to\s*[:\-\s]*([A-Z][A-Za-z\s\.\-&]{2,50})', text, re.IGNORECASE)
    if m:
        name = clean_name(m.group(1))
        if name and len(name) > 2:
            return name
    
    m = re.search(r'\bTo\s*[:\-\s]*([A-Z][A-Za-z\s\.\-&]{2,50})', text, re.IGNORECASE)
    if m:
        name = clean_name(m.group(1))
        if name and len(name) > 2 and name.lower() not in ['transaction', 'payment', 'successful']:
            return name
    
    m = re.search(r'(?:Verified|Banking)\s+Name\s*[:\-\s]*([A-Za-z][A-Za-z\s\.\-&]{2,50})', text, re.IGNORECASE)
    if m:
        name = clean_name(m.group(1))
        if name and len(name) > 2:
            return name
    
    return "Not Found"


def extract_upi_id(text):
    m = re.search(r'\b([A-Za-z0-9._\-]+@[A-Za-z0-9._\-]+)\b', text)
    if m:
        return m.group(1).lower()
    return "Not Found"


def extract_datetime(text):
    m = re.search(r'(\d{1,2}:\d{2})\s*(?:am|pm)?\s+on\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} on {m.group(2)}"
    
    m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*,?\s+(\d{1,2}:\d{2}\s*[APap][Mm])', text)
    if m:
        return f"{m.group(2)} on {m.group(1)}"
    
    m = re.search(r'\d{1,2}/\d{1,2}/\d{4}[ \t]+\d{1,2}:\d{2}', text)
    if m:
        return m.group(0).strip()
    
    return "Not Found"


# ---------- Callback handler ----------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    stage = user_state.get(user_id, {}).get("stage")

    if data == "retry_image_upload":
        file_id = context.user_data.get("last_file_id")
        if file_id:
            try:
                file = await context.bot.get_file(file_id)
                file_bytes = await file.download_as_bytearray()
                user_images[user_id] = file_bytes
                user_state[user_id] = {"stage": "main_category"}
                await query.edit_message_text("🔘 Choose the receipt type:", reply_markup=main_category_keyboard())
                return
            except Exception as e:
                logger.error(f"Retry failed: {e}")
        await query.edit_message_text("Tap Retry:", reply_markup=retry_keyboard("retry_image_upload"))
        return

    if data == "retry_upi_menu":
        if user_id in user_images:
            user_state[user_id] = {"stage": "upi_subtype"}
            await query.edit_message_text("💡 Choose UPI type:", reply_markup=upi_subtype_keyboard())
        else:
            await query.edit_message_text("Tap Retry:", reply_markup=retry_keyboard("retry_image_upload"))
        return

    if data.startswith("retry_process_"):
        category = data.replace("retry_process_", "")
        await process_receipt(query, user_id, category)
        return

    if data in ("upi", "voucher", "gstbill", "PhonePe", "Paytm", "GooglePay", "Others"):
        if user_id not in user_images:
            await query.edit_message_text("Tap Retry:", reply_markup=retry_keyboard("retry_image_upload"))
            return

    if stage == "main_category":
        if data == "upi":
            user_state[user_id]["stage"] = "upi_subtype"
            await query.edit_message_text("💡 Choose UPI type:", reply_markup=upi_subtype_keyboard())
            return
        elif data == "gstbill":
            user_state[user_id]["stage"] = "upi_subtype"
            user_state[user_id]["category"] = "gstbill"
            await query.edit_message_text("💡 Choose UPI type for GST Bill:", reply_markup=upi_subtype_keyboard())
            return
        elif data == "voucher":
            await query.edit_message_text("Tap Retry:", reply_markup=retry_keyboard("retry_upi_menu"))
            return

    if stage == "upi_subtype":
        if data in ["PhonePe", "Paytm", "GooglePay", "Others"]:
            context.user_data["last_category"] = data
            user_state[user_id]["stage"] = "final"

            if user_state[user_id].get("category") == "gstbill":
                await process_receipt(query, user_id, category="gstbill_" + data)
            else:
                await process_receipt(query, user_id, category=data)
            return

    await query.edit_message_text("Tap Retry:", reply_markup=retry_keyboard("retry_image_upload"))


async def process_receipt(query, user_id, category):
    try:
        image_stream = BytesIO(user_images[user_id])
        text = extract_text_from_image(image_stream)
        
        if not text or len(text.strip()) < 10:
            logger.warning(f"Insufficient text: {len(text)} chars")
            await query.edit_message_text("⚠️ Could not extract text. Tap Retry:", reply_markup=retry_keyboard(f"retry_process_{category}"))
            return

        formatted = extract_limited_fields(text, category)
        fields = {}
        for line in formatted.splitlines():
            if line.startswith("• "):
                try:
                    key, val = line[2:].split(":", 1)
                    fields[key.strip()] = val.strip()
                except ValueError:
                    continue

        record_id = insert_extracted_receipt(user_id, category, fields)
        if record_id:
            transaction_id = fields.get('Transaction ID', 'unknown')
            type_param = category if not category.startswith("gstbill") else "gstbill"
            link = f"http://192.168.1.41:5000/voucher?transaction_id={transaction_id}&type={type_param}"
            
            success_msg = "✅ Data Saved!"
            # for key, value in fields.items():
                # success_msg += f"• {key}: {value}\n"
            success_msg += f"\n\n fill voucher:🌐 {link}"
            
            await query.edit_message_text(success_msg)
            
            if user_id in user_images:
                del user_images[user_id]
        else:
            await query.edit_message_text("❌ Database error. Tap Retry:", reply_markup=retry_keyboard(f"retry_process_{category}"))
            
    except Exception as e:
        logger.error(f"❌ Processing error: {e}", exc_info=True)
        await query.edit_message_text("❌ Failed. Tap Retry:", reply_markup=retry_keyboard(f"retry_process_{category}"))


# ---------- Telegram Daily Status ----------
def send_daily_status():
    try:
        status_text = get_last_24h_status()
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        for chat_id in CHAT_IDS:
            payload = {"chat_id": chat_id, "text": status_text}
            requests.post(url, json=payload)
            logger.info(f"✅ Status sent to {chat_id}")
    except Exception as e:
        logger.error(f"❌ Status send failed: {e}")


# ---------- Voucher Server ----------
def start_voucher_server():
    try:
        thread = threading.Thread(
            target=run_voucher_app,
            kwargs={'host': '0.0.0.0', 'port': 5000, 'use_reloader': False},
            daemon=True
        )
        thread.start()
        logger.info("✅ Voucher server started on port 5000")
    except Exception as e:
        logger.error(f"❌ Voucher server failed: {e}")


# ---------- Main ----------
if __name__ == "__main__":
    try:
        logger.info("=" * 70)
        logger.info("🚀 Starting OCR Receipt Bot")
        logger.info("=" * 70)
        
        # Check BOT_TOKEN
        if not BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN not found in environment!")
            exit(1)
        
        logger.info("Initializing database...")
        init_db()
        
        logger.info("Starting voucher server...")
        start_voucher_server()
        
        logger.info("Setting up scheduler...")
        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(send_daily_status, "cron", hour=0, minute=0)
        scheduler.start()
        logger.info("✅ Scheduler started")
        
        logger.info("Building Telegram bot...")
        app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
        app_telegram.add_handler(CommandHandler("start", start))
        app_telegram.add_handler(MessageHandler(filters.PHOTO, handle_image))
        app_telegram.add_handler(CallbackQueryHandler(handle_callback))
        app_telegram.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), start))
        
        logger.info("✅ Bot ready! Starting polling...")
        logger.info("=" * 70)
        
        app_telegram.run_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        exit(1)