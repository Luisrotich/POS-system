from flask import Flask, request, jsonify, send_file, session, render_template, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
import os
import sqlite3
from io import BytesIO, StringIO
import csv
import threading
import time
import uuid
import requests
import base64
from requests.auth import HTTPBasicAuth

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.permanent_session_lifetime = timedelta(days=7)

# M-Pesa Daraja API credentials (set these as environment variables in production)
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', 'sJWMb8e5xwZ9APh9d8RAWt1VUjBEnmrM50bA8cBE4vwXxXwT')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', 'AecUYi2w8e1Mrjd0tHFAK7Z9WQxKkBN09pXEGs3JM83EGp7ofCJs5PlCI7Jq3KUQ')
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '174379')          # Use your Paybill/Till number
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'https://unelegant-uncombatable-gerald.ngrok-free.dev/api/mpesa/callback')
MPESA_ENVIRONMENT = os.environ.get('MPESA_ENVIRONMENT', 'sandbox')      # 'sandbox' or 'production'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_product_image(file):
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join('static/uploads/products', filename)
        file.save(filepath)
        return f'/static/uploads/products/{filename}'
    return None

# -------------------- M-Pesa Helper Functions --------------------
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_mpesa_access_token(retries=3):
    """Get OAuth token from Safaricom with retry logic."""
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    if MPESA_ENVIRONMENT == 'production':
        url = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=1,  # 1s, 2s, 4s
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    
    try:
        response = session.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET), timeout=30)
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"M-Pesa auth error: {response.text}")
            return None
    except Exception as e:
        print(f"M-Pesa connection error: {e}")
        return None

def generate_mpesa_password(shortcode, passkey, timestamp):
    """Generate password for STK push."""
    data_to_encode = shortcode + passkey + timestamp
    return base64.b64encode(data_to_encode.encode()).decode('utf-8')

def stk_push_request(phone_number, amount, account_reference="POS Payment", transaction_desc="Payment for goods"):
    """Send STK push to customer's phone."""
    access_token = get_mpesa_access_token()
    if not access_token:
        return {'error': 'Failed to get M-Pesa token'}, None
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_mpesa_password(MPESA_SHORTCODE, MPESA_PASSKEY, timestamp)
    
    # Format phone number to 2547XXXXXXXX
    if phone_number.startswith('0'):
        phone_number = '254' + phone_number[1:]
    elif phone_number.startswith('+'):
        phone_number = phone_number[1:]
    
    # Determine transaction type based on shortcode
    transaction_type = "CustomerPayBillOnline" if MPESA_SHORTCODE == '174379' else "CustomerBuyGoodsOnline"
    
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_reference[:12],
        "TransactionDesc": transaction_desc[:13]
    }
    
    url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
    if MPESA_ENVIRONMENT == 'production':
        url = 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
    
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        return None, response.json()
    else:
        return {'error': f'STK push failed: {response.text}'}, None

# -------------------- Database Migration --------------------
def upgrade_db():
    """Add missing columns to existing tables (schema migration)."""
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    c.execute("PRAGMA table_info(products)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    if 'image_url' not in existing_columns:
        print("⚠️ Adding missing column 'image_url' to products table")
        c.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
    
    if 'buying_price' not in existing_columns:
        print("⚠️ Adding missing column 'buying_price' to products table")
        c.execute("ALTER TABLE products ADD COLUMN buying_price REAL DEFAULT 0")
    
    if 'low_stock_threshold' not in existing_columns:
        print("⚠️ Adding missing column 'low_stock_threshold' to products table")
        c.execute("ALTER TABLE products ADD COLUMN low_stock_threshold INTEGER DEFAULT 5")
    
    c.execute("PRAGMA table_info(categories)")
    cat_columns = [col[1] for col in c.fetchall()]
    if 'icon' not in cat_columns:
        print("⚠️ Adding missing column 'icon' to categories table")
        c.execute("ALTER TABLE categories ADD COLUMN icon TEXT")
    if 'color' not in cat_columns:
        print("⚠️ Adding missing column 'color' to categories table")
        c.execute("ALTER TABLE categories ADD COLUMN color TEXT")
    
    conn.commit()
    conn.close()
    print("✅ Database schema up to date")

def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Categories table
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        color TEXT,
        icon TEXT
    )''')
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sku TEXT UNIQUE,
        barcode TEXT,
        category_id INTEGER,
        buying_price REAL,
        selling_price REAL NOT NULL,
        stock_quantity INTEGER DEFAULT 0,
        low_stock_threshold INTEGER DEFAULT 5,
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id)
    )''')
    
    # Sales table
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        customer_name TEXT,
        customer_phone TEXT,
        subtotal REAL,
        tax REAL,
        total REAL,
        payment_method TEXT,
        receipt_number TEXT,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    # Sale items table
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        price_at_time REAL,
        FOREIGN KEY (sale_id) REFERENCES sales(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    
    # M-Pesa transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS mpesa_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checkout_request_id TEXT UNIQUE,
        receipt_number TEXT,
        phone_number TEXT,
        amount REAL,
        status TEXT,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Default categories
    default_categories = [
        ('Food', '#FF6B6B', '🍔'),
        ('Drinks', '#4ECDC4', '🥤'),
        ('Household', '#45B7D1', '🏠'),
        ('Electronics', '#96CEB4', '📱'),
        ('Cosmetics', '#FFEAA7', '💄'),
        ('Stationery', '#DFE6E9', '📚'),
        ('Snacks', '#FDCB6E', '🍿'),
        ('Milk Products', '#6C5CE7', '🥛'),
        ('Cleaning Products', '#A8E6CF', '🧹'),
        ('Others', '#B2C9AB', '📦')
    ]
    for cat in default_categories:
        c.execute("INSERT OR IGNORE INTO categories (name, color, icon) VALUES (?, ?, ?)", cat)
    
    # Default users
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_pass = generate_password_hash('admin123')
        cashier_pass = generate_password_hash('cashier123')
        c.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                  ('admin', admin_pass, 'admin', 'System Administrator'))
        c.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                  ('cashier', cashier_pass, 'cashier', 'Store Cashier'))
        print("✅ Default users created")
    
    # Sample products if empty
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.execute("SELECT id FROM categories WHERE name = 'Food' LIMIT 1")
        food_id = c.fetchone()[0]
        c.execute("SELECT id FROM categories WHERE name = 'Drinks' LIMIT 1")
        drinks_id = c.fetchone()[0]
        sample_products = [
            ('White Bread', 'BREAD001', '123456', food_id, 50, 70, 100, 5),
            ('Fresh Milk 1L', 'MILK001', '123457', food_id, 80, 120, 50, 5),
            ('Coca Cola', 'COLA001', '123458', drinks_id, 40, 60, 200, 5),
            ('Sugar 1kg', 'SUGAR001', '123459', food_id, 100, 180, 75, 5),
            ('Cooking Oil 2L', 'OIL001', '123460', food_id, 250, 350, 40, 5),
            ('Soap Bar', 'SOAP001', '123461', food_id, 30, 50, 150, 5),
            ('Fanta Orange', 'FANTA001', '123462', drinks_id, 40, 60, 180, 5),
            ('Toilet Paper', 'TP001', '123463', food_id, 200, 350, 60, 5),
        ]
        for p in sample_products:
            c.execute("""INSERT INTO products (name, sku, barcode, category_id, buying_price, 
                         selling_price, stock_quantity, low_stock_threshold)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", p)
        print("✅ Sample products added")
    
    conn.commit()
    upgrade_db()   # ensures any missing columns are added
    conn.close()
    print("✅ Database initialized")

init_db()

# -------------------- Authentication Decorators --------------------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

def cashier_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ['admin', 'cashier']:
            return jsonify({'error': 'Cashier access required'}), 403
        return f(*args, **kwargs)
    return decorated

# -------------------- Frontend Routes --------------------
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    username = data.get('username')
    password = data.get('password')
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    if user and check_password_hash(user[2], password):
        session.permanent = True
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['role'] = user[3]
        return jsonify({'success': True, 'role': user[3], 'username': user[1]})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/pos')
def pos():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/admin')
def admin_panel():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html')

# -------------------- API Endpoints --------------------
@app.route('/api/categories')
def get_categories():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT id, name, color, icon FROM categories ORDER BY name")
    categories = [{'id': row[0], 'name': row[1], 'color': row[2], 'icon': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(categories)

@app.route('/api/products')
def get_products():
    category = request.args.get('category')
    search = request.args.get('search', '')
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    query = """SELECT p.id, p.name, p.sku, p.barcode, p.selling_price, p.stock_quantity, 
                      p.image_url, c.name as category_name, p.category_id
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE 1=1"""
    params = []
    if category and category != '':
        query += " AND c.name = ?"
        params.append(category)
    if search:
        query += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    query += " ORDER BY p.name"
    c.execute(query, params)
    products = []
    for row in c.fetchall():
        products.append({
            'id': row[0],
            'name': row[1],
            'sku': row[2],
            'barcode': row[3],
            'selling_price': row[4],
            'stock_quantity': row[5],
            'image_url': row[6],
            'category': row[7] if row[7] else 'Uncategorized',
            'category_id': row[8]
        })
    conn.close()
    return jsonify(products)

@app.route('/api/sale', methods=['POST'])
@cashier_required
def create_sale():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    items = data.get('items', [])
    customer_name = data.get('customer_name', 'Walk-in Customer')
    payment_method = data.get('payment_method', 'cash')
    mpesa_transaction_id = data.get('mpesa_transaction_id', None)
    if not items:
        return jsonify({'error': 'No items in sale'}), 400
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    subtotal = sum(item['price'] * item['quantity'] for item in items)
    tax = subtotal * 0.16
    total = subtotal + tax
    order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    receipt_number = f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    c.execute("""INSERT INTO sales (order_number, user_id, customer_name, subtotal, tax, total, payment_method, receipt_number)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (order_number, session['user_id'], customer_name, subtotal, tax, total, payment_method, receipt_number))
    sale_id = c.lastrowid
    for item in items:
        c.execute("INSERT INTO sale_items (sale_id, product_id, quantity, price_at_time) VALUES (?, ?, ?, ?)",
                  (sale_id, item['id'], item['quantity'], item['price']))
        c.execute("UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?", (item['quantity'], item['id']))
    if payment_method == 'mpesa' and mpesa_transaction_id:
        c.execute("UPDATE mpesa_transactions SET status = 'completed', receipt_number = ? WHERE checkout_request_id = ?",
                  (receipt_number, mpesa_transaction_id))
    conn.commit()
    c.execute("""SELECT p.name, si.quantity, si.price_at_time FROM sale_items si JOIN products p ON si.product_id = p.id WHERE si.sale_id = ?""", (sale_id,))
    sale_items = [{'name': row[0], 'quantity': row[1], 'price': row[2]} for row in c.fetchall()]
    receipt_data = {
        'order_number': order_number,
        'receipt_number': receipt_number,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'customer_name': customer_name,
        'items': sale_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'payment_method': 'M-Pesa' if payment_method == 'mpesa' else 'Cash'
    }
    conn.close()
    return jsonify({'success': True, 'sale_id': sale_id, 'order_number': order_number, 'receipt_number': receipt_number, 'receipt_data': receipt_data})

# -------------------- Real M-Pesa STK Push Endpoint --------------------
@app.route('/api/mpesa/pay', methods=['POST'])
@cashier_required
def mpesa_payment():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    phone_number = data.get('phone_number')
    amount = data.get('amount')

    if not phone_number or not amount:
        return jsonify({'error': 'Phone number and amount required'}), 400

    # Call the real M-Pesa STK push (with retries inside)
    error, response = stk_push_request(phone_number, amount)
    if error:
        # Log the actual error for debugging
        app.logger.error(f"STK Push failed: {error}")
        return jsonify({'error': error.get('error', 'STK push failed. Check your internet connection and try again.')}), 400

    checkout_request_id = response.get('CheckoutRequestID')
    if not checkout_request_id:
        return jsonify({'error': 'No CheckoutRequestID returned from M-Pesa'}), 500

    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("""
        INSERT INTO mpesa_transactions (checkout_request_id, phone_number, amount, status)
        VALUES (?, ?, ?, 'pending')
    """, (checkout_request_id, phone_number, amount))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'checkout_request_id': checkout_request_id,
        'message': 'STK Push sent. Check your phone to complete the payment.'
    })
# -------------------- M-Pesa Callback (from Safaricom) --------------------
@app.route('/api/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Receive callback from Safaricom after user completes payment."""
    data = request.get_json()
    print("M-Pesa Callback received:", data)
    
    body = data.get('Body', {})
    stk_callback = body.get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    result_code = stk_callback.get('ResultCode')
    result_desc = stk_callback.get('ResultDesc')
    
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    if result_code == 0:  # Success
        callback_metadata = stk_callback.get('CallbackMetadata', {})
        items = callback_metadata.get('Item', [])
        receipt_number = None
        amount = None
        for item in items:
            if item.get('Name') == 'MpesaReceiptNumber':
                receipt_number = item.get('Value')
            if item.get('Name') == 'Amount':
                amount = item.get('Value')
        
        c.execute("""
            UPDATE mpesa_transactions 
            SET status = 'completed', receipt_number = ? 
            WHERE checkout_request_id = ?
        """, (receipt_number, checkout_request_id))
        conn.commit()
    else:
        c.execute("""
            UPDATE mpesa_transactions 
            SET status = 'failed' 
            WHERE checkout_request_id = ?
        """, (checkout_request_id,))
        conn.commit()
    
    conn.close()
    # Must return a success response to Safaricom
    return jsonify({'ResultCode': 0, 'ResultDesc': 'Success'})

@app.route('/api/mpesa/status/<checkout_request_id>')
def mpesa_status(checkout_request_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT status, receipt_number FROM mpesa_transactions WHERE checkout_request_id = ?", (checkout_request_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return jsonify({'status': result[0], 'receipt_number': result[1]})
    return jsonify({'status': 'not_found'}), 404

@app.route('/api/print/receipt', methods=['POST'])
def print_receipt():
    data = request.get_json()
    receipt_data = data.get('receipt_data')
    if not receipt_data:
        return '<html><body>No receipt data</body></html>', 400
    receipt_html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Receipt</title><style>
        body {{ font-family: monospace; width: 300px; margin: auto; text-align: center; padding: 20px; }}
        hr {{ border-top: 1px dashed #000; }}
        .item-row {{ display: flex; justify-content: space-between; }}
    </style></head>
    <body>
        <h3>GENERAL SHOP</h3>
        <p>Date: {receipt_data.get('date')}</p>
        <hr/>
        <p>Order: {receipt_data.get('order_number')}<br>Receipt: {receipt_data.get('receipt_number')}<br>Customer: {receipt_data.get('customer_name')}</p>
        <hr/>
    """
    for item in receipt_data.get('items', []):
        receipt_html += f"<div class='item-row'><span>{item['name']} x{item['quantity']}</span><span>Ksh {item['price']*item['quantity']:.2f}</span></div>"
    receipt_html += f"""
        <hr/>
        <div class='item-row'><span>Subtotal:</span><span>Ksh {receipt_data.get('subtotal',0):.2f}</span></div>
        <div class='item-row'><span>VAT 16%:</span><span>Ksh {receipt_data.get('tax',0):.2f}</span></div>
        <div class='item-row'><strong>TOTAL:</strong><strong>Ksh {receipt_data.get('total',0):.2f}</strong></div>
        <hr/>
        <p>Payment: {receipt_data.get('payment_method')}</p>
        <p>Thank you!</p>
        <script>window.print(); setTimeout(()=>window.close(),500);</script>
    </body>
    </html>
    """
    return receipt_html

# ---------- ADMIN API ENDPOINTS ----------
@app.route('/api/dashboard/stats')
@admin_required
def dashboard_stats():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) = ?", (today,))
    today_sales, today_count = c.fetchone()
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) >= ?", (week_ago,))
    weekly_sales, weekly_count = c.fetchone()
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) >= ?", (month_ago,))
    monthly_sales, monthly_count = c.fetchone()
    c.execute("SELECT COUNT(*) FROM products")
    total_products = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT customer_name) FROM sales WHERE customer_name NOT NULL AND customer_name != 'Walk-in Customer'")
    total_customers = c.fetchone()[0]
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM mpesa_transactions WHERE status = 'completed'")
    mpesa_count, mpesa_total = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(total), 0) FROM sales WHERE payment_method = 'cash' AND DATE(sale_date) = ?", (today,))
    cash_count, cash_total = c.fetchone()
    c.execute("SELECT COALESCE(SUM(total), 0) FROM sales")
    total_revenue = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM products WHERE stock_quantity <= low_stock_threshold")
    low_stock_products = c.fetchone()[0]
    conn.close()
    return jsonify({
        'today_sales': {'amount': float(today_sales), 'count': today_count},
        'weekly_sales': {'amount': float(weekly_sales), 'count': weekly_count},
        'monthly_sales': {'amount': float(monthly_sales), 'count': monthly_count},
        'total_products': total_products,
        'total_customers': total_customers,
        'mpesa_transactions': {'count': mpesa_count, 'total': float(mpesa_total)},
        'cash_transactions': {'count': cash_count, 'total': float(cash_total)},
        'total_revenue': float(total_revenue),
        'low_stock_products': low_stock_products
    })

@app.route('/api/mpesa/transactions')
@admin_required
def mpesa_transactions():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT receipt_number, phone_number, amount, status, transaction_date FROM mpesa_transactions ORDER BY transaction_date DESC LIMIT 50")
    transactions = [{'receipt_number': row[0] or '-', 'phone_number': row[1], 'amount': float(row[2]) if row[2] else 0, 'status': row[3], 'date': row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(transactions)

@app.route('/api/export/mpesa/csv')
@admin_required
def export_mpesa_csv():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT receipt_number, phone_number, amount, status, transaction_date FROM mpesa_transactions ORDER BY transaction_date DESC")
    transactions = c.fetchall()
    conn.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Receipt Number', 'Phone Number', 'Amount (KES)', 'Status', 'Date'])
    for t in transactions:
        writer.writerow([t[0] or '-', t[1], t[2], t[3], t[4]])
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f'mpesa_transactions_{datetime.now().strftime("%Y%m%d")}.csv')

@app.route('/api/recent/sales')
@admin_required
def recent_sales():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT order_number, total, payment_method, sale_date FROM sales ORDER BY sale_date DESC LIMIT 10")
    sales = [{'order_number': row[0], 'total': float(row[1]), 'payment_method': row[2], 'date': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(sales)

@app.route('/api/low-stock/products')
@admin_required
def low_stock_products():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT name, sku, stock_quantity, low_stock_threshold FROM products WHERE stock_quantity <= low_stock_threshold ORDER BY stock_quantity ASC LIMIT 10")
    products = [{'name': row[0], 'sku': row[1], 'stock': row[2], 'threshold': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(products)

@app.route('/api/weekly/sales')
@admin_required
def weekly_sales():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    amounts = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        c.execute("SELECT COALESCE(SUM(total), 0) FROM sales WHERE DATE(sale_date) = ?", (date,))
        amounts.append(float(c.fetchone()[0]))
    conn.close()
    return jsonify({'days': days, 'amounts': amounts})

@app.route('/api/sales/report')
@admin_required
def sales_report():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT order_number, customer_name, subtotal, tax, total, payment_method, sale_date FROM sales ORDER BY sale_date DESC LIMIT 100")
    sales = [{'order_number': row[0], 'customer_name': row[1] or 'Walk-in', 'subtotal': float(row[2]), 'tax': float(row[3]), 'total': float(row[4]), 'payment_method': row[5], 'date': row[6]} for row in c.fetchall()]
    conn.close()
    return jsonify({'sales': sales})

@app.route('/api/users')
@admin_required
def get_users():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, created_at FROM users ORDER BY created_at DESC")
    users = [{'id': row[0], 'username': row[1], 'full_name': row[2], 'role': row[3], 'created_at': row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = generate_password_hash(data.get('password'))
    full_name = data.get('full_name', '')
    role = data.get('role', 'cashier')
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)", (username, password, full_name, role))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username exists'}), 400
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ? AND role != 'admin'", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- PRODUCT CRUD ----------
@app.route('/api/products', methods=['POST'])
@admin_required
def create_product():
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip() or None
            barcode = request.form.get('barcode', '').strip() or None
            category_id = request.form.get('category_id')
            buying_price = float(request.form.get('buying_price', 0))
            selling_price = float(request.form.get('selling_price', 0))
            stock_quantity = int(request.form.get('stock_quantity', 0))
            low_stock_threshold = int(request.form.get('low_stock_threshold', 5))
            image_file = request.files.get('image')
            image_url = save_product_image(image_file) if image_file and image_file.filename else None
        else:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            name = data.get('name', '').strip()
            sku = data.get('sku', '').strip() or None
            barcode = data.get('barcode', '').strip() or None
            category_id = data.get('category_id')
            buying_price = float(data.get('buying_price', 0))
            selling_price = float(data.get('selling_price', 0))
            stock_quantity = int(data.get('stock_quantity', 0))
            low_stock_threshold = int(data.get('low_stock_threshold', 5))
            image_url = None
        
        if not name:
            return jsonify({'error': 'Product name required'}), 400
        if selling_price <= 0:
            return jsonify({'error': 'Valid selling price required'}), 400
        
        cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
        
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        if sku:
            c.execute("SELECT id FROM products WHERE sku = ?", (sku,))
            if c.fetchone():
                conn.close()
                return jsonify({'error': 'SKU already exists'}), 400
        
        c.execute("""
            INSERT INTO products (name, sku, barcode, category_id, buying_price, selling_price, stock_quantity, low_stock_threshold, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, sku, barcode, cat_id, buying_price, selling_price, stock_quantity, low_stock_threshold, image_url))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'message': 'Product created', 'product_id': new_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 400

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip() or None
            barcode = request.form.get('barcode', '').strip() or None
            category_id = request.form.get('category_id')
            buying_price = float(request.form.get('buying_price', 0))
            selling_price = float(request.form.get('selling_price', 0))
            low_stock_threshold = int(request.form.get('low_stock_threshold', 5))
            image_file = request.files.get('image')
            image_url = save_product_image(image_file) if image_file and image_file.filename else None
            cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
            conn = sqlite3.connect('shop.db')
            c = conn.cursor()
            if image_url:
                c.execute("UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, selling_price=?, low_stock_threshold=?, image_url=? WHERE id=?",
                          (name, sku, barcode, cat_id, buying_price, selling_price, low_stock_threshold, image_url, product_id))
            else:
                c.execute("UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, selling_price=?, low_stock_threshold=? WHERE id=?",
                          (name, sku, barcode, cat_id, buying_price, selling_price, low_stock_threshold, product_id))
            conn.commit()
            conn.close()
        else:
            data = request.get_json()
            cat_id = int(data.get('category_id')) if data.get('category_id') else None
            conn = sqlite3.connect('shop.db')
            c = conn.cursor()
            c.execute("UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, selling_price=?, low_stock_threshold=? WHERE id=?",
                      (data['name'], data.get('sku'), data.get('barcode'), cat_id, data.get('buying_price', 0), data['selling_price'], data.get('low_stock_threshold', 5), product_id))
            conn.commit()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/<int:product_id>', methods=['GET'])
@admin_required
def get_product(product_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT id, name, sku, barcode, category_id, buying_price, selling_price, stock_quantity, low_stock_threshold, image_url FROM products WHERE id = ?", (product_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({
            'id': row[0], 'name': row[1], 'sku': row[2], 'barcode': row[3],
            'category_id': row[4], 'buying_price': row[5], 'selling_price': row[6],
            'stock_quantity': row[7], 'low_stock_threshold': row[8], 'image_url': row[9]
        })
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/categories', methods=['POST'])
@admin_required
def create_category():
    data = request.get_json()
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)", (data['name'], data.get('color', '#667eea'), data.get('icon', '📦')))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Category exists'}), 400
    finally:
        conn.close()

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("UPDATE products SET category_id = NULL WHERE category_id = ?", (category_id,))
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# Static file serving
@app.route('/static/uploads/products/<filename>')
def uploaded_file(filename):
    filepath = os.path.join('static/uploads/products', filename)
    if not os.path.exists(filepath):
        return '', 404
    return send_file(filepath)

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 POS SYSTEM STARTING...")
    print("="*50)
    print("\n📍 http://127.0.0.1:5000")
    print("👤 Admin: admin / admin123")
    print("👤 Cashier: cashier / cashier123")
    print("📸 Images: PNG, JPG, JPEG, GIF, WEBP")
    print("💰 M-Pesa: Real STK Push (Daraja API)")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)