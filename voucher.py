import os
import json
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import bcrypt
import logging  # Standard library logging
import psycopg2
import base64
import uuid
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file, get_flashed_messages
from flask import flash as flask_flash  # Import flash with alias to avoid conflicts
from flask_session import Session
from datetime import datetime, timedelta
from io import BytesIO
from email.message import EmailMessage
import smtplib
from PyPDF2 import PdfReader, PdfWriter

# Shared storage for session data
voucher_data = {}

# Import user management functions
from database import init_db, register_user, get_user_by_email, get_user_by_username, get_pending_users, update_user_status, get_user_by_id, get_accepted_users, get_rejected_users, register_admin, get_admin_by_email, add_email, get_all_emails, update_email, delete_email, email_exists_in_list

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
                receiver_signature TEXT,
                signature_image BYTEA,
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
            
        # ⭐ NEW: Check and add signature_image column if it doesn't exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='brochure' AND column_name='signature_image';
        """)
        
        if not cur.fetchone():
            cur.execute('''
                ALTER TABLE brochure 
                ADD COLUMN signature_image BYTEA;
            ''')
            logging.info("✅ Added signature_image column to brochure table")
            
        # ⭐ NEW: Check and add additional_receipt2 column if it doesn't exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='brochure' AND column_name='additional_receipt2';
        """)
        
        if not cur.fetchone():
            cur.execute('''
                ALTER TABLE brochure 
                ADD COLUMN additional_receipt2 BYTEA;
            ''')
            logging.info("✅ Added additional_receipt2 column to brochure table")
        
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
    
    if request.method == "POST":
        try:
            # Get form data
            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            esignature = request.form.get("esignature")
            
            # Handle signature data - could be base64 image or plain text
            signature_image_data = None
            if esignature and esignature.startswith('data:image/') and ';base64,' in esignature:
                # It's a base64 image, extract the image data
                try:
                    # Extract base64 data from data URL
                    header, encoded = esignature.split(',', 1)
                    signature_image_data = base64.b64decode(encoded)
                    # Use placeholder text for display
                    processed_signature = "[Drawn Signature]"
                except Exception as e:
                    logging.error(f"Error decoding signature image: {e}")
                    processed_signature = "[Drawn Signature]"  # Fallback
            else:
                # It's plain text, use as-is
                processed_signature = esignature
            
            # Validate required fields
            if not all([username, email, password, confirm_password]):
                flask_flash("All fields are required!", "error")
                return render_template("signup.html", transaction_id=transaction_id, voucher_type=voucher_type)
            
            # Check if passwords match
            if password != confirm_password:
                flask_flash("Passwords do not match!", "error")
                return render_template("signup.html", transaction_id=transaction_id, voucher_type=voucher_type)
            
            # Check if user already exists
            if get_user_by_email(email) or get_user_by_username(username):
                flask_flash("User already exists with this email or username!", "error")
                return render_template("signup.html", transaction_id=transaction_id, voucher_type=voucher_type)
            
            # Hash the password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Check if email exists in email list
            if email_exists_in_list(email):
                # Auto-accept user if email is in the list
                status = "accepted"
                flash_message = "Signup successful! Your account has been automatically approved."
                flash_category = "success"
            else:
                # Put user in pending status if email is not in the list
                status = "pending"
                flash_message = "This mail is not authorized by compny so contact to Admin"
                flash_category = "error"
            
            # Register the user with the determined status
            user_id = register_user(username, email, hashed_password, processed_signature, signature_image_data, status)
            
            if user_id:
                flask_flash(flash_message, flash_category)
                if status == "accepted":
                    # For accepted users, show success message and redirect to login
                    # They will be able to access voucher page after login
                    return redirect(url_for("login"))
                else:
                    # For pending users, redirect to login page
                    return redirect(url_for("login"))
            else:
                flask_flash("Registration failed. Please try again.", "error")
                return render_template("signup.html", transaction_id=transaction_id, voucher_type=voucher_type)
                
        except Exception as e:
            logging.error(f"❌ Registration error: {e}")
            flask_flash("An error occurred during registration. Please try again.", "error")
            return render_template("signup.html", transaction_id=transaction_id, voucher_type=voucher_type)
    
    # Pass through transaction parameters to signup form
    return render_template('signup.html', transaction_id=transaction_id, voucher_type=voucher_type)

@voucher_app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        user = get_user_by_email(email)
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            # Check user status
            if user['status'] == 'accepted':
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['email'] = user['email']
                
                # Get transaction parameters if they exist in the session or URL
                transaction_id = request.args.get('transaction_id') or session.get('transaction_id')
                voucher_type = request.args.get('type') or session.get('voucher_type')
                
                # Clear transaction parameters from session
                session.pop('transaction_id', None)
                session.pop('voucher_type', None)
                
                # Redirect to voucher page with parameters if they exist
                if transaction_id and voucher_type:
                    return redirect(url_for("display_voucher", transaction_id=transaction_id, type=voucher_type))
                else:
                    return redirect(url_for("display_voucher"))
            elif user['status'] == 'pending':
                flask_flash("Your account is pending administrator authorization. Please wait for approval before logging in.", "warning")
                return render_template("login.html")
            elif user['status'] == 'rejected':
                flask_flash("Your account has been rejected by the administrator.", "error")
                return render_template("login.html")
        else:
            # Check if email exists in email list
            if email_exists_in_list(email):
                # Email is in the list but credentials are wrong
                flask_flash("Invalid email or password!", "error")
            else:
                # Email is not in the approved list
                flask_flash("This email is not authorized by the company. Please contact the administrator.", "error")
            return render_template("login.html")
    
    # Store transaction parameters in session if they exist in URL
    transaction_id = request.args.get('transaction_id')
    voucher_type = request.args.get('type')
    if transaction_id and voucher_type:
        session['transaction_id'] = transaction_id
        session['voucher_type'] = voucher_type
    
    return render_template("login.html")

# Admin Dashboard Routes
@voucher_app.route("/admin/approve_user/<int:user_id>")
def approve_user(user_id):
    # Simple admin check - in production, implement proper authentication
    if update_user_status(user_id, 'accepted'):
        return jsonify({'success': True, 'message': 'User approved successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to approve user'}), 500

@voucher_app.route("/admin/reject_user/<int:user_id>")
def reject_user(user_id):
    # Simple admin check - in production, implement proper authentication
    if update_user_status(user_id, 'rejected'):
        return jsonify({'success': True, 'message': 'User rejected successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to reject user'}), 500

# Admin Authentication Routes
@voucher_app.route("/admin/signup", methods=["GET", "POST"])
def admin_signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        company_name = request.form['company_name']
        role = request.form['role']
        
        # Validate passwords match
        if password != confirm_password:
            return render_template('admin_signup.html', error="Passwords do not match")
        
        # Register admin
        admin_id = register_admin(username, email, password, company_name, role)
        if admin_id:
            return render_template('admin_signup.html', success="Admin registered successfully! You can now login.")
        else:
            return render_template('admin_signup.html', error="Registration failed. Please try again.")
    
    return render_template('admin_signup.html')

@voucher_app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        admin = get_admin_by_email(email)
        if admin and admin['password'] == password:  # In production, use proper password hashing
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            session['admin_company'] = admin['company_name']
            session['admin_role'] = admin['role']
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid credentials")
    
    return render_template('admin_login.html')

@voucher_app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

# Email Management Routes
@voucher_app.route("/admin/emails")
def email_management():
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
        
    # Get all emails
    emails = get_all_emails()
    return render_template('email_management.html', emails=emails)

@voucher_app.route("/admin/emails/add", methods=["POST"])
def add_email_route():
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        email_address = data.get('email_address')
        description = data.get('description', '')
        
        if not email_address:
            return jsonify({'success': False, 'message': 'Email address is required'}), 400
            
        email_id = add_email(email_address, description)
        if email_id:
            return jsonify({'success': True, 'message': 'Email added successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to add email'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@voucher_app.route("/admin/emails/update/<int:email_id>", methods=["PUT"])
def update_email_route(email_id):
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        email_address = data.get('email_address')
        description = data.get('description', '')
        
        if not email_address:
            return jsonify({'success': False, 'message': 'Email address is required'}), 400
            
        success = update_email(email_id, email_address, description)
        if success:
            return jsonify({'success': True, 'message': 'Email updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update email'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@voucher_app.route("/admin/emails/delete/<int:email_id>", methods=["DELETE"])
def delete_email_route(email_id):
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        success = delete_email(email_id)
        if success:
            return jsonify({'success': True, 'message': 'Email deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete email'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Protect admin dashboard route
@voucher_app.route("/admin/dashboard")
def admin_dashboard():
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    # Get user statistics
    pending_users = get_pending_users()
    accepted_users = get_accepted_users()
    rejected_users = get_rejected_users()
    
    return render_template('admin_dashboard.html', 
                         pending_users=pending_users,
                         accepted_users=accepted_users,
                         rejected_users=rejected_users)

@voucher_app.route("/admin/users")
def admin_user_management():
    # Check if admin is authenticated
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    # Get all users
    pending_users = get_pending_users()
    accepted_users = get_accepted_users()
    rejected_users = get_rejected_users()
    
    return render_template('admin_users.html', 
                         pending_users=pending_users,
                         accepted_users=accepted_users,
                         rejected_users=rejected_users)

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

        # Get user's e-signature and signature image from the users table
        user_esignature = ''
        user_signature_image_base64 = ''
        if 'user_id' in session:
            cur.execute('''
                SELECT esignature, signature_image
                FROM users
                WHERE id = %s
            ''', (session['user_id'],))
            user_row = cur.fetchone()
            if user_row:
                user_esignature = user_row[0] or ''
                # Convert signature image to base64 if it exists
                if user_row[1]:
                    user_signature_image_base64 = 'data:image/png;base64,' + base64.b64encode(user_row[1]).decode('utf-8')

        cur.close()
        conn.close()
        
        logging.info(f"Fetched row for transaction_id '{transaction_id}': {row}")
        
        data = {
            "Sl No": next_slno,
            "transaction_id": row[0] if row else '',
            "amount": row[1] if row else '',
            "user_esignature": user_esignature,
            "user_signature_image": user_signature_image_base64
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

        # ⭐ NEW: Get location data
        location = data.get('location', '')
        location_lat = data.get('location_lat', '')
        location_lng = data.get('location_lng', '')
        
        # Convert string coordinates to float if they exist
        lat = float(location_lat) if location_lat else None
        lng = float(location_lng) if location_lng else None

        # ⭐ NEW: Get user's signature image from database if available
        signature_image_data = None
        if 'user_id' in session:
            try:
                conn_users = psycopg2.connect(**DATABASE_CONFIG)
                cur_users = conn_users.cursor()
                cur_users.execute('''
                    SELECT signature_image
                    FROM users
                    WHERE id = %s
                ''', (session['user_id'],))
                user_row = cur_users.fetchone()
                if user_row and user_row[0]:
                    signature_image_data = user_row[0]
                cur_users.close()
                conn_users.close()
            except Exception as e:
                logging.error(f"Error fetching user signature image: {e}")

        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # ⭐ CHANGED: Updated INSERT statement with location_lat and location_lng and signature_image
        # Also added logic to extract last page of PDF if it's a GST bill
        last_page_pdf_bytes = None
        if additional_receipt and data.get('voucher_type') == 'gstbill':
            try:
                # Read the uploaded PDF
                pdf_bytes = additional_receipt.read()
                additional_receipt.seek(0)  # Reset file pointer for database storage
                
                # Extract the last page of the PDF
                from PyPDF2 import PdfReader, PdfWriter
                from io import BytesIO
                
                # Create a PDF reader object
                pdf_reader = PdfReader(BytesIO(pdf_bytes))
                
                # Get the last page
                if len(pdf_reader.pages) > 0:
                    # Create a PDF writer object for the last page
                    pdf_writer = PdfWriter()
                    last_page = pdf_reader.pages[-1]  # Get the last page
                    pdf_writer.add_page(last_page)
                    
                    # Write the last page to bytes
                    last_page_buffer = BytesIO()
                    pdf_writer.write(last_page_buffer)
                    last_page_pdf_bytes = last_page_buffer.getvalue()
            except Exception as e:
                logging.error(f"❌ Error extracting last page from PDF: {e}")
                # If we can't extract the last page, we'll just store None

        cur.execute('''
            INSERT INTO brochure (
                slno, date, account_name, debit, credit, amount, time,
                reason, procured_from, location, location_lat, location_lng,
                additional_receipt, additional_receipt2, receiver_signature, signature_image, image
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
            last_page_pdf_bytes,  # Store the last page of the PDF for GST bills
            data['receiver_signature'],
            signature_image_data,  # Add signature image data
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

# New route to fetch the last page of the uploaded PDF
@voucher_app.route('/get_last_page_pdf/<int:record_id>')
def get_last_page_pdf(record_id):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('SELECT additional_receipt2 FROM brochure WHERE id = %s', (record_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row and row[0]:
            return send_file(BytesIO(row[0]), mimetype='application/pdf', as_attachment=False)
        else:
            return "No last page PDF found", 404
    except Exception as e:
        logging.error(f"❌ Error retrieving last page PDF: {e}")
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

@voucher_app.route('/upload_generated_pdf', methods=['POST'])
def upload_generated_pdf():
    try:
        data = request.get_json()
        pdf_base64 = data.get('pdfBase64')
        record_id = data.get('recordId')
        
        if not pdf_base64 or not record_id:
            return jsonify({'success': False, 'error': 'Missing PDF data or record ID'}), 400
        
        # Decode the base64 PDF
        pdf_bytes = base64.b64decode(pdf_base64)
        
        # Extract the last page of the PDF
        last_page_pdf_bytes = None
        try:
            # Create a PDF reader object
            pdf_reader = PdfReader(BytesIO(pdf_bytes))
            
            # Get the last page
            if len(pdf_reader.pages) > 0:
                # Create a PDF writer object for the last page
                pdf_writer = PdfWriter()
                last_page = pdf_reader.pages[-1]  # Get the last page
                pdf_writer.add_page(last_page)
                
                # Write the last page to bytes
                last_page_buffer = BytesIO()
                pdf_writer.write(last_page_buffer)
                last_page_pdf_bytes = last_page_buffer.getvalue()
        except Exception as e:
            logging.error(f"❌ Error extracting last page from PDF: {e}")
            # If we can't extract the last page, we'll just use the full PDF
            last_page_pdf_bytes = pdf_bytes
        
        # Update the brochure table with the generated PDF
        # For GST bills, we'll store the full PDF in additional_receipt
        # and the last page in additional_receipt2 (if extraction was successful)
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        if last_page_pdf_bytes and last_page_pdf_bytes != pdf_bytes:
            # We successfully extracted the last page, store both
            cur.execute('''
                UPDATE brochure 
                SET additional_receipt = %s, additional_receipt2 = %s
                WHERE id = %s
            ''', (psycopg2.Binary(pdf_bytes), psycopg2.Binary(last_page_pdf_bytes), record_id))
        else:
            # Either extraction failed or resulted in the same PDF, store only the full PDF
            cur.execute('''
                UPDATE brochure 
                SET additional_receipt = %s
                WHERE id = %s
            ''', (psycopg2.Binary(pdf_bytes), record_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ Generated PDF uploaded for record ID: {record_id}")
        return jsonify({'success': True, 'message': 'PDF uploaded successfully'})
        
    except Exception as e:
        logging.error(f"❌ Error uploading generated PDF: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# New endpoint to modify PDF and attach voucher image
@voucher_app.route('/modify_pdf_with_voucher', methods=['POST'])
def modify_pdf_with_voucher():
    try:
        # Get the uploaded PDF file
        uploaded_pdf = request.files.get('uploadedPdf')
        voucher_image_data = request.form.get('voucherImage')
        transaction_id = request.form.get('transactionId')
        
        if not uploaded_pdf or not voucher_image_data:
            return jsonify({'success': False, 'error': 'Missing PDF or voucher image'}), 400
        
        # Read the uploaded PDF
        pdf_bytes = uploaded_pdf.read()
        
        # Decode the voucher image (it's a data URL)
        if voucher_image_data.startswith('data:image'):
            header, encoded = voucher_image_data.split(',', 1)
            voucher_image_bytes = base64.b64decode(encoded)
        else:
            voucher_image_bytes = base64.b64decode(voucher_image_data)
        
        # Modify the PDF to add the voucher image as the last page
        from PyPDF2 import PdfReader, PdfWriter
        from io import BytesIO
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import tempfile
        import os
        
        # Create a PDF reader object
        pdf_reader = PdfReader(BytesIO(pdf_bytes))
        
        # Create a PDF writer object
        pdf_writer = PdfWriter()
        
        # Copy all existing pages
        for page in pdf_reader.pages:
            pdf_writer.add_page(page)
        
        # Create a new page with the voucher image
        # Create a temporary PDF with the image
        temp_pdf_buffer = BytesIO()
        c = canvas.Canvas(temp_pdf_buffer, pagesize=letter)
        width, height = letter
        
        # Add the voucher image to the new page
        # Save voucher image to temporary file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
            tmp_img.write(voucher_image_bytes)
            tmp_img_path = tmp_img.name
        
        # Calculate image size to fit the page
        img_width = width * 0.8
        img_height = height * 0.8
        img_x = (width - img_width) / 2
        img_y = (height - img_height) / 2
        
        c.drawImage(tmp_img_path, img_x, img_y, width=img_width, height=img_height)
        c.showPage()
        c.save()
        
        # Clean up temporary image file
        os.unlink(tmp_img_path)
        
        # Add the new page with voucher image to the PDF
        temp_pdf_buffer.seek(0)
        temp_pdf_reader = PdfReader(temp_pdf_buffer)
        for page in temp_pdf_reader.pages:
            pdf_writer.add_page(page)
        
        # Write the modified PDF to bytes
        output_buffer = BytesIO()
        pdf_writer.write(output_buffer)
        modified_pdf_bytes = output_buffer.getvalue()
        
        # Return the modified PDF
        return send_file(
            BytesIO(modified_pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'GST_Bill_{transaction_id}_with_voucher.pdf'
        )
        
    except Exception as e:
        logging.error(f"❌ Error modifying PDF with voucher image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Run
def run_voucher_app(host='0.0.0.0', port=5000, use_reloader=False):
    init_db()
    voucher_app.run(host=host, port=port, use_reloader=use_reloader)