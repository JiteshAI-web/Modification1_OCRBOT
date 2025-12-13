# database.py
import os
import logging
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Database Configuration ===
DATABASE_CONFIG = {
    'host': os.getenv("DB_HOST", '192.168.1.140'),
    'database': os.getenv("DB_NAME", 'Bfl_ocr'),
    'user': os.getenv("DB_USER", 'vertoxl'),
    'password': os.getenv("DB_PASSWORD", 'vertoxlabs'),
}

def init_db():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()

        # Table 1: extracted_receipts
        cur.execute('''
            CREATE TABLE IF NOT EXISTS extracted_receipts (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                category VARCHAR(50),
                amount TEXT,
                datetime TEXT,
                transaction_id TEXT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                person_name TEXT,
                upi_id TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Table 2: brochure
        cur.execute('''
            CREATE TABLE IF NOT EXISTS brochure (
                id SERIAL PRIMARY KEY,
                session_id UUID UNIQUE,
                slno TEXT,
                date TEXT,
                account_name TEXT,
                debit TEXT,
                credit TEXT,
                amount TEXT,
                time TEXT,
                reason TEXT,
                procured_from TEXT NULL,
                location TEXT NULL,
                additional_receipt BYTEA NULL,
                additional_receipt2 BYTEA NULL,
                upload_stamp BYTEA,
                receiver_signature TEXT,
                image BYTEA,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Table 3: users
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                esignature TEXT,
                signature_image BYTEA,
                status VARCHAR(10) DEFAULT 'pending',  -- New column for accept/reject status
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # Table 4: admins - New table for admin users
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                company_name VARCHAR(100),
                role VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # Table 5: email - New table for email management
        cur.execute('''
            CREATE TABLE IF NOT EXISTS email (
                id SERIAL PRIMARY KEY,
                email_address VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # Check and add status column if it doesn't exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='status';
        """)
        
        if not cur.fetchone():
            cur.execute('''
                ALTER TABLE users 
                ADD COLUMN status VARCHAR(10) DEFAULT 'pending';
            ''')
            logging.info("✅ Added status column to users table")
            
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ Database initialized successfully.")
    except Exception as e:
        logging.error(f"❌ Error initializing database: {e}")

def add_signature_image_column():
    """Add signature_image column to users table if it doesn't exist"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # Check if signature_image column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='signature_image';
        """)
        
        if not cur.fetchone():
            cur.execute('''
                ALTER TABLE users 
                ADD COLUMN signature_image BYTEA;
            ''')
            logging.info("✅ Added signature_image column to users table")
            
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ Error adding signature_image column: {e}")

# Call this function after init_db to ensure column exists
add_signature_image_column()

def insert_extracted_receipt(user_id, category, fields):
    """Insert extracted receipt data and return the record ID"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # ✅ FIXED: Add RETURNING id to get the inserted record ID
        cur.execute('''
            INSERT INTO extracted_receipts (
                user_id, category, amount, datetime, transaction_id, person_name, upi_id, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            user_id,
            category,
            fields.get("Amount"),
            fields.get("Date & Time"),
            fields.get("Transaction ID"),
            fields.get("Person Name"),
            fields.get("UPI ID"),
            fields.get("status", "pending")  # Default to 'pending'
        ))
        
        # ✅ FIXED: Get the returned record ID
        record_id = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"📝 Receipt inserted into database with ID: {record_id}")
        return record_id  # ✅ FIXED: Return the record ID
        
    except Exception as e:
        logging.error(f"❌ Failed to insert receipt: {e}")
        return None  # Return None if insertion fails

def insert_or_update_brochure(data):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO brochure (
                session_id, slno, date, account_name, debit, credit,
                amount, time , reason, procured_from, location, receiver_signature
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', data)  # ✅ FIXED: Removed extra parentheses
         
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"✅ Brochure created ")
    except Exception as e:
        logging.error(f"❌ Failed to create brochure: {e}")

# ✅ NEW FUNCTION: Get specific receipt data by transaction_id
def get_receipt_by_transaction_id(transaction_id):
    """Get receipt data by transaction_id"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, transaction_id, amount, datetime, person_name, upi_id, status
            FROM extracted_receipts
            WHERE transaction_id = %s
            ORDER BY created_at DESC
            LIMIT 1;
        ''', (transaction_id,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'transaction_id': row[1],
                'amount': row[2],
                'datetime': row[3],
                'person_name': row[4],
                'upi_id': row[5],
                'status': row[6]
            }
        else:
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to get receipt by transaction_id {transaction_id}: {e}")
        return None

# User Management Functions
def register_user(username, email, password, esignature, signature_image=None, status="pending"):
    """
    Register a new user with optional signature image and status
    
    Args:
        username (str): Username
        email (str): Email address
        password (str): Hashed password
        esignature (str): Processed signature text (placeholder for drawn signatures)
        signature_image (bytes, optional): Actual signature image data
        status (str): User status ('pending', 'accepted', 'rejected')
    
    Returns:
        int: User ID if successful, None if failed
    """
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # Insert user with signature image if provided
        if signature_image:
            cur.execute('''
                INSERT INTO users (username, email, password, esignature, signature_image, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
            ''', (username, email, password, esignature, signature_image, status))
        else:
            cur.execute('''
                INSERT INTO users (username, email, password, esignature, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            ''', (username, email, password, esignature, status))
        
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ User {username} ({email}) registered successfully with ID: {user_id} and status: {status}")
        return user_id
        
    except Exception as e:
        logging.error(f"❌ Failed to register user {username} ({email}): {e}")
        return None

def get_user_by_email(email):
    """Get user by email"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, password, esignature, signature_image, status
            FROM users
            WHERE email = %s;
        ''', (email,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'password': row[3],
                'esignature': row[4],
                'signature_image': row[5],
                'status': row[6]
            }
        else:
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to get user by email {email}: {e}")
        return None

def get_user_by_username(username):
    """Get user by username"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, password, esignature, signature_image, status
            FROM users
            WHERE username = %s;
        ''', (username,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'password': row[3],
                'esignature': row[4],
                'signature_image': row[5],
                'status': row[6]
            }
        else:
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to get user by username {username}: {e}")
        return None

def get_pending_users():
    """Get all users with pending status"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, esignature, created_at
            FROM users
            WHERE status = 'pending'
            ORDER BY created_at DESC;
        ''')
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'esignature': row[3],
                'created_at': row[4]
            })
            
        return users
        
    except Exception as e:
        logging.error(f"❌ Failed to get pending users: {e}")
        return []

def get_accepted_users():
    """Get all users with accepted status"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, esignature, created_at
            FROM users
            WHERE status = 'accepted'
            ORDER BY created_at DESC;
        ''')
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'esignature': row[3],
                'created_at': row[4]
            })
            
        return users
        
    except Exception as e:
        logging.error(f"❌ Failed to get accepted users: {e}")
        return []

def get_rejected_users():
    """Get all users with rejected status"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, esignature, created_at
            FROM users
            WHERE status = 'rejected'
            ORDER BY created_at DESC;
        ''')
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'esignature': row[3],
                'created_at': row[4]
            })
            
        return users
        
    except Exception as e:
        logging.error(f"❌ Failed to get rejected users: {e}")
        return []

def update_user_status(user_id, status):
    """Update user status to accepted or rejected"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE users
            SET status = %s
            WHERE id = %s;
        ''', (status, user_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ User {user_id} status updated to {status}")
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to update user {user_id} status: {e}")
        return False

def get_user_by_id(user_id):
    """Get user by ID"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, password, esignature, signature_image, status
            FROM users
            WHERE id = %s;
        ''', (user_id,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'password': row[3],
                'esignature': row[4],
                'signature_image': row[5],
                'status': row[6]
            }
        else:
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to get user by ID {user_id}: {e}")
        return None

def register_admin(username, email, password, company_name, role):
    """Register a new admin user"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO admins (username, email, password, company_name, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (username, email, password, company_name, role))
        
        admin_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ Admin {username} registered successfully with ID: {admin_id}")
        return admin_id
        
    except Exception as e:
        logging.error(f"❌ Failed to register admin {username}: {e}")
        return None

def get_admin_by_email(email):
    """Get admin by email"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, username, email, password, company_name, role
            FROM admins
            WHERE email = %s;
        ''', (email,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'password': row[3],
                'company_name': row[4],
                'role': row[5]
            }
        else:
            return None
            
    except Exception as e:
        logging.error(f"❌ Failed to get admin by email {email}: {e}")
        return None

def add_email(email_address, description=""):
    """Add a new email to the email list"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO email (email_address, description)
            VALUES (%s, %s)
            RETURNING id;
        ''', (email_address, description))
        
        email_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ Email {email_address} added successfully with ID: {email_id}")
        return email_id
        
    except Exception as e:
        logging.error(f"❌ Failed to add email {email_address}: {e}")
        return None

def get_all_emails():
    """Get all emails from the email list"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, email_address, description, created_at, updated_at
            FROM email
            ORDER BY created_at DESC;
        ''')
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        emails = []
        for row in rows:
            emails.append({
                'id': row[0],
                'email_address': row[1],
                'description': row[2],
                'created_at': row[3],
                'updated_at': row[4]
            })
            
        return emails
        
    except Exception as e:
        logging.error(f"❌ Failed to get emails: {e}")
        return []

def update_email(email_id, email_address, description=""):
    """Update an existing email in the email list"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            UPDATE email
            SET email_address = %s, description = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        ''', (email_address, description, email_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ Email ID {email_id} updated successfully")
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to update email ID {email_id}: {e}")
        return False

def delete_email(email_id):
    """Delete an email from the email list"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            DELETE FROM email
            WHERE id = %s;
        ''', (email_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info(f"✅ Email ID {email_id} deleted successfully")
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to delete email ID {email_id}: {e}")
        return False

def email_exists_in_list(email_address):
    """Check if an email exists in the email list"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            SELECT COUNT(*) FROM email
            WHERE email_address = %s;
        ''', (email_address,))
        
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        return count > 0
        
    except Exception as e:
        logging.error(f"❌ Failed to check email existence {email_address}: {e}")
        return False
