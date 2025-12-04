import os
import logging
import psycopg2
import base64
import uuid
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from flask_session import Session
from datetime import datetime, timedelta
from io import BytesIO
from email.message import EmailMessage
import smtplib
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# Shared storage for session data
voucher_data = {}

# Import user management functions
from database import init_db, register_user, get_user_by_email, get_user_by_username

# Flask app
voucher_app = Flask(__name__)
voucher_app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key in production
voucher_app.config['SESSION_TYPE'] = 'filesystem'
Session(voucher_app)

# Path to your logo file (place logo.png in a folder called 'static')
LOGO_PATH = "static/logo.png"

# Database Config
DATABASE_CONFIG = {
    'host': '192.168.1.140',
    'database': 'Bfl_ocr',
    'user': 'vertoxl',
    'password': 'vertoxlabs',
}

# Logging
logging.basicConfig(level=logging.INFO)

# Initialize the database
def init_db():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS brochure (
                id SERIAL PRIMARY KEY,
                slno TEXT,
                date TEXT,
                account_name TEXT,
                debit TEXT,
                credit TEXT,
                amount TEXT,
                time TEXT,
                reason TEXT,
                procured_from TEXT,
                location TEXT,
                additional_receipt BYTEA,
                additional_receipt2 BYTEA,
                upload_stamp BYTEA,
                receiver_signature TEXT,
                image BYTEA,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # ⭐ NEW: Check and add location columns if they don't exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='brochure' AND column_name='location_lat';
        """)
        
        if not cur.fetchone():
            cur.execute('''
                ALTER TABLE brochure 
                ADD COLUMN location_lat DECIMAL(10, 8),
                ADD COLUMN location_lng DECIMAL(11, 8);
            ''')
            logging.info("✅ Added location columns to brochure table")
        
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ Database initialized.")
    except Exception as e:
        logging.error(f"❌ Failed to init DB: {e}")

def send_telegram_notification(transaction_id, account_name, amount):
    """Send notification to Telegram when voucher is completed"""
    try:
        # Get BOT_TOKEN from environment or hardcode it
        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
        CHAT_IDS = [-1003283341507]  # Your existing chat IDs from main.py
        
        message = (
            f"✅ **Justification Letter Generated**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 **Transaction ID:** {transaction_id}\n"
            f"👤 **Account Name:** {account_name}\n"
            f"💰 **Amount:** {amount}\n"
            f"📄 **Status:** Completed Successfully\n"
            f"🕒 **Time:** {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}"
        )
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        for chat_id in CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logging.info(f"✅ Telegram notification sent to chat {chat_id}")
            else:
                logging.error(f"❌ Failed to send Telegram notification to chat {chat_id}: {response.text}")
                
    except Exception as e:
        logging.error(f"❌ Error sending Telegram notification: {e}")

def send_gst_bill_notification(transaction_id, account_name, amount):
    """Send notification to Telegram when GST Bill voucher is completed"""
    try:
        # Get BOT_TOKEN from environment or hardcode it
        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
        CHAT_IDS = [-1003283341507]  # Your existing chat IDs from main.py
        
        message = (
            f"✅ **GST Bill Generated**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 **Transaction ID:** {transaction_id}\n"
            f"👤 **Account Name:** {account_name}\n"
            f"💰 **Amount:** {amount}\n"
            f"📄 **Status:** Completed Successfully\n"
            f"🕒 **Time:** {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}"
        )
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        for chat_id in CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                logging.info(f"✅ GST Bill notification sent to chat {chat_id}")
            else:
                logging.error(f"❌ Failed to send GST Bill notification to chat {chat_id}: {response.text}")
                
    except Exception as e:
        logging.error(f"❌ Error sending GST Bill notification: {e}")

def get_last_24h_status():
    """Return pending and completed counts from last 24 hours as text, including pending transaction IDs."""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()

        yesterday = datetime.now(pytz.timezone("Asia/Kolkata")) - timedelta(hours=24)

        # Get counts
        cur.execute("""
            SELECT status, COUNT(*)
            FROM extracted_receipts
            WHERE created_at >= %s
            GROUP BY status;
        """, (yesterday,))
        results = cur.fetchall()

        pending_count = 0
        completed_count = 0
        for status, count in results:
            if status and status.lower() == "pending":
                pending_count = count
            elif status and status.lower() == "completed":
                completed_count = count

        # Get transaction IDs for pending tasks
        cur.execute("""
            SELECT transaction_id, person_name
            FROM extracted_receipts
            WHERE created_at >= %s AND LOWER(status) = 'pending'
            ORDER BY created_at DESC;
        """, (yesterday,))
        pending_records = cur.fetchall()

        cur.close()
        conn.close()

        # Format pending IDs (limit to avoid huge messages)
        if pending_records:
            pending_list = "\n".join([f"🔹 {txn} — {name}" for txn, name in pending_records[:10]])
            if len(pending_records) > 10:
                pending_list += f"\n... and {len(pending_records) - 10} more"
        else:
            pending_list = "✅ No pending tasks in last 24h"

        return (
            "📢 **Daily Work Summary (Last 24h)**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🕒 Period: {yesterday.strftime('%d-%b %H:%M')} → Now\n"
            f"📌 Pending: {pending_count}\n"
            f"✅ Completed: {completed_count}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📝 **Waiting For Justification Letter:**\n{pending_list}"
        )

    except Exception as e:
        logging.error(f"❌ Error getting status: {e}")
        return "Error fetching status."

# Render voucher form with specific transaction data
@voucher_app.route("/", methods=["GET"])
def index():
    # Always redirect to login - force authentication every time
    return redirect(url_for('login'))

@voucher_app.route("/signup", methods=["GET", "POST"])
def signup():
    # Get transaction_id and type from URL parameters to pass through after signup
    transaction_id = request.args.get('transaction_id')
    voucher_type = request.args.get('type', '')
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        esignature = request.form['esignature']
        
        # Check if passwords match
        if password != confirm_password:
            return render_template('signup.html', error="Passwords do not match", transaction_id=transaction_id, voucher_type=voucher_type)
        
        # Check if user already exists by EMAIL ONLY (allow duplicate usernames)
        if get_user_by_email(email):
            return render_template('signup.html', error="Email already registered", transaction_id=transaction_id, voucher_type=voucher_type)
        
        # Register user (without checking for duplicate username)
        user_id = register_user(username, email, password, esignature)  # In production, hash the password
        if user_id:
            # Automatically log in the user after successful signup
            session['user_id'] = user_id
            session['username'] = username
            session['user_esignature'] = esignature
            
            # Store transaction info in session temporarily and redirect to display voucher
            if transaction_id and voucher_type:
                session['temp_transaction_id'] = transaction_id
                session['temp_voucher_type'] = voucher_type
                return redirect(url_for('display_voucher'))
            else:
                return redirect(url_for('display_voucher'))
        else:
            return render_template('signup.html', error="Registration failed. Please try again.", transaction_id=transaction_id, voucher_type=voucher_type)
    
    # Pass through transaction parameters to signup form
    return render_template('signup.html', transaction_id=transaction_id, voucher_type=voucher_type)

@voucher_app.route("/login", methods=["GET", "POST"])
def login():
    # Get transaction_id and type from URL parameters to pass through after login
    transaction_id = request.args.get('transaction_id')
    voucher_type = request.args.get('type', '')
    success_msg = request.args.get('success', '')  # Get success message if present
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = get_user_by_email(email)
        if user and user['password'] == password:  # In production, use proper password hashing
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_esignature'] = user['esignature']
            
            # After login, redirect to display voucher page with original parameters
            # Store transaction info in session temporarily
            if transaction_id and voucher_type:
                session['temp_transaction_id'] = transaction_id
                session['temp_voucher_type'] = voucher_type
                return redirect(url_for('display_voucher'))
            else:
                return redirect(url_for('display_voucher'))
        else:
            return render_template('login.html', error="Invalid email or password", transaction_id=transaction_id, voucher_type=voucher_type, success=success_msg)
    
    # Pass through transaction parameters and success message to login form
    return render_template('login.html', transaction_id=transaction_id, voucher_type=voucher_type, success=success_msg)

@voucher_app.route("/display_voucher", methods=["GET"])
def display_voucher():
    # Check if user is authenticated
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()

        # Get next serial number
        cur.execute("SELECT slno FROM brochure ORDER BY id DESC LIMIT 1;")
        last_slno_row = cur.fetchone()

        # Extract number from last slno
        if last_slno_row and last_slno_row[0].startswith("BCPL"):
            last_num = int(''.join(filter(str.isdigit, last_slno_row[0])))
            next_slno = f"BCPL{last_num + 1}"
        else:
            next_slno = "BCPL1"

        # Get transaction_id and type from session (temporary storage)
        transaction_id = session.pop('temp_transaction_id', None)  # Remove after use
        voucher_type = session.pop('temp_voucher_type', None)      # Remove after use
        
        # If not in session, try URL parameters
        if not transaction_id:
            transaction_id = request.args.get('transaction_id')
        if not voucher_type:
            voucher_type = request.args.get('type', '').lower()
        
        if transaction_id and transaction_id != 'unknown':
            # Fetch specific receipt data by transaction_id
            cur.execute('''
                SELECT transaction_id, amount
                FROM extracted_receipts
                WHERE transaction_id = %s
                ORDER BY created_at DESC
                LIMIT 1;
            ''', (transaction_id,))
            row = cur.fetchone()
            
            if not row:
                logging.warning(f"Transaction ID {transaction_id} not found, falling back to latest")
                # Fallback to latest if specific transaction not found
                cur.execute('''
                    SELECT transaction_id, amount
                    FROM extracted_receipts
                    ORDER BY created_at DESC
                    LIMIT 1;
                ''')
                row = cur.fetchone()
        else:
            # Fallback to latest receipt if no specific ID provided
            cur.execute('''
                SELECT transaction_id, amount
                FROM extracted_receipts
                ORDER BY created_at DESC
                LIMIT 1;
            ''')
            row = cur.fetchone()

        cur.close()
        conn.close()
        
        logging.info(f"Fetched row for transaction_id '{transaction_id}': {row}")
        
        # Get user's e-signature from session
        user_esignature = session.get('user_esignature', '')
        
        data = {
            "Sl No": next_slno,
            "transaction_id": row[0] if row else '',
            "amount": row[1] if row else '',
            "user_esignature": user_esignature  # Add user's e-signature to data
        }

        # ⭐ CHANGED: Use render_template instead of render_template_string
        return render_template('voucher.html', data=data, voucher_type=voucher_type)

    except Exception as e:
        logging.error(f"❌ Failed to fetch receipt data: {e}")
        # ⭐ CHANGED: Use render_template instead of render_template_string
        return render_template('voucher.html', data={"Sl No": "BCPL1"}, voucher_type='')

@voucher_app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@voucher_app.route("/voucher", methods=["GET"])
def voucher_form():
    # ALWAYS redirect to login - force authentication every time, regardless of session state
    transaction_id = request.args.get('transaction_id')
    voucher_type = request.args.get('type', '')
    return redirect(url_for('login', transaction_id=transaction_id, type=voucher_type))

# Save voucher to DB after submission
@voucher_app.route('/save_voucher', methods=['POST'])
def save_voucher():
    try:
        data = request.form
        image_data_url = data.get('image_data')
        header, encoded = image_data_url.split(',', 1)
        image_bytes = base64.b64decode(encoded)

        additional_receipt = request.files.get('additional_receipt')
        print("111111111111")
        additional_receipt2 = request.files.get('additional_receipt2')
        print("2222222222222")
        upload_stamp = request.files.get('upload_stamp')
        print("33333333333333")

        # ⭐ NEW: Get location data
        location = data.get('location', '')
        location_lat = data.get('location_lat', '')
        location_lng = data.get('location_lng', '')
        
        # Convert to float or None
        try:
            lat = float(location_lat) if location_lat else None
            lng = float(location_lng) if location_lng else None
        except (ValueError, TypeError):
            lat = None
            lng = None

        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # ⭐ CHANGED: Updated INSERT statement with location_lat and location_lng
        cur.execute('''
            INSERT INTO brochure (
                slno, date, account_name, debit, credit, amount, time,
                reason, procured_from, location, location_lat, location_lng,
                additional_receipt, additional_receipt2,
                upload_stamp, receiver_signature, image
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            data['slno'],
            data['date'],
            data['account_name'],
            data['debit'],
            data['credit'],
            data['amount'],
            data['time'],
            data['reason'],
            data['procured_from'],
            location,          # ⭐ CHANGED: Use location variable
            lat,               # ⭐ NEW: Add latitude
            lng,               # ⭐ NEW: Add longitude
            additional_receipt.read() if additional_receipt else None,
            additional_receipt2.read() if additional_receipt2 else None,
            upload_stamp.read() if upload_stamp else None,
            data['receiver_signature'],
            psycopg2.Binary(image_bytes)
        ))
        print("444444444")
        
        record_id = cur.fetchone()[0]
        
        # Update status in extracted_receipts
        transaction_id = data.get("transaction_id")
        voucher_type = data.get("voucher_type", "")
        
        if transaction_id:
            cur.execute('''
                UPDATE extracted_receipts
                SET status = 'completed'
                WHERE transaction_id = %s;
            ''', (transaction_id,))
            logging.info(f"✅ Status updated to completed for transaction_id: {transaction_id}")

        conn.commit()
        
        # ⭐ NEW: Log location info
        if lat and lng:
            logging.info(f"📍 Location saved: {location} ({lat}, {lng})")
        
        cur.close()
        conn.close()

        # Send Telegram notification for both UPI and GST Bill
        if transaction_id:
            # Customize message based on voucher type
            if voucher_type == 'gstbill':
                send_gst_bill_notification(
                    transaction_id=transaction_id,
                    account_name=data.get('account_name', 'Unknown'),
                    amount=data.get('amount', '0')
                )
            else:
                send_telegram_notification(
                    transaction_id=transaction_id,
                    account_name=data.get('account_name', 'Unknown'),
                    amount=data.get('amount', '0')
                )

        return jsonify({"message": "✅ Voucher saved", "record_id": record_id})
    except Exception as e:
        logging.error(f"❌ Failed to save voucher: {e}")
        return jsonify({"message": "❌ Failed to save voucher."}), 500

# Serves voucher image
@voucher_app.route('/voucher_image/<int:record_id>')
def get_voucher_image(record_id):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('SELECT image FROM brochure WHERE id = %s', (record_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return send_file(BytesIO(row[0]), mimetype='image/png')
        else:
            return "No image found", 404
    except Exception as e:
        logging.error(f"❌ Error retrieving voucher image: {e}")
        return "Server error", 500

# New route to fetch the uploaded PDF
@voucher_app.route('/get_uploaded_pdf/<int:record_id>')
def get_uploaded_pdf(record_id):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('SELECT additional_receipt FROM brochure WHERE id = %s', (record_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row and row[0]:
            return send_file(BytesIO(row[0]), mimetype='application/pdf', as_attachment=False)
        else:
            return "No PDF found", 404
    except Exception as e:
        logging.error(f"❌ Error retrieving PDF: {e}")
        return "Server error", 500

@voucher_app.route('/send_pdf_email', methods=['POST'])
def send_pdf_email():
    try:
        data = request.get_json()
        pdf_base64 = data.get('pdfBase64')
        file_name = data.get('fileName', 'voucher.pdf')
        recipients = data.get('recipients', [])
        logging.info("DEBUG: Recipients received from frontend => %s", recipients)
        logging.info("DEBUG: File being sent => %s", file_name)

        if not pdf_base64 or not recipients:
            return jsonify({'success': False, 'error': 'Missing PDF or recipients'}), 400

        pdf_bytes = base64.b64decode(pdf_base64)

        send_pdf_email_multiple(pdf_bytes, file_name, recipients)

        return jsonify({'success': True, 'message': 'Email sent'})

    except Exception as e:
        logging.error(f"❌ Error sending PDF email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Helper function to send PDF email to multiple recipients
def send_pdf_email_multiple(pdf_bytes, file_name, recipients):
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    SMTP_USER = 'sethytrinatha25@gmail.com'
    SMTP_PASS = 'qoeogdtohzgpoklj'

    msg = EmailMessage()
    msg['Subject'] = 'Payment Voucher PDF'
    msg['From'] = SMTP_USER
    msg['To'] = ", ".join(recipients)
    msg.set_content('Please find the attached payment voucher PDF.')

    msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=file_name)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)

# ⭐ NEW: Endpoint to get location data
@voucher_app.route('/get_location/<int:record_id>')
def get_location(record_id):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('''
            SELECT location, location_lat, location_lng 
            FROM brochure 
            WHERE id = %s
        ''', (record_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return jsonify({
                "location": row[0],
                "latitude": float(row[1]) if row[1] else None,
                "longitude": float(row[2]) if row[2] else None
            })
        else:
            return jsonify({"error": "Location not found"}), 404
    except Exception as e:
        logging.error(f"❌ Error retrieving location: {e}")
        return jsonify({"error": "Server error"}), 500

# Run
def run_voucher_app(host='0.0.0.0', port=5000, use_reloader=False):
    init_db()
    voucher_app.run(host=host, port=port, use_reloader=use_reloader)