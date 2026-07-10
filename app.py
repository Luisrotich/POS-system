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
import uuid
import requests
import base64
from requests.auth import HTTPBasicAuth

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=7)

# M-Pesa Daraja API credentials
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', 'your_consumer_key')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', 'your_consumer_secret')
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '174379')
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', 'your_passkey')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'https://your-domain.com/api/mpesa/callback')
MPESA_ENVIRONMENT = os.environ.get('MPESA_ENVIRONMENT', 'sandbox')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_product_image(file):
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join('static/uploads/products', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        return f'/static/uploads/products/{filename}'
    return None

def get_db():
    """Get database connection with row factory for dict results"""
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(table, column):
    """Check if a column exists in a table"""
    conn = get_db()
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    conn.close()
    return column in columns

def add_column_if_not_exists(table, column, column_type):
    """Add a column to a table if it doesn't exist"""
    if not column_exists(table, column):
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
            conn.commit()
            print(f"✅ Added column '{column}' to '{table}'")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Could not add column '{column}' to '{table}': {e}")
        finally:
            conn.close()

# ==================== DATABASE ====================

def init_db():
    """Initialize database with all tables"""
    conn = get_db()
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT,
        email TEXT,
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
        buying_price REAL DEFAULT 0,
        selling_price REAL NOT NULL,
        stock_quantity INTEGER DEFAULT 0,
        low_stock_threshold INTEGER DEFAULT 5,
        image_url TEXT,
        unit TEXT DEFAULT 'piece',
        tax_rate REAL DEFAULT 16,
        discount REAL DEFAULT 0,
        supplier TEXT,
        expiry_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id)
    )''')
    
    # Sales table - create with all columns
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
        status TEXT DEFAULT 'completed',
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
    
    # Inventory transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        type TEXT,
        quantity INTEGER,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    
    # Customers table
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT UNIQUE,
        email TEXT,
        address TEXT,
        loyalty_points INTEGER DEFAULT 0,
        total_spent REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE,
        customer_id INTEGER,
        customer_name TEXT,
        customer_phone TEXT,
        customer_email TEXT,
        delivery_address TEXT,
        status TEXT DEFAULT 'pending',
        total REAL,
        items TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )''')
    
    conn.commit()
    conn.close()
    
    # Now add any missing columns to existing tables
    add_column_if_not_exists('users', 'email', 'TEXT')
    add_column_if_not_exists('products', 'unit', 'TEXT DEFAULT "piece"')
    add_column_if_not_exists('products', 'tax_rate', 'REAL DEFAULT 16')
    add_column_if_not_exists('products', 'discount', 'REAL DEFAULT 0')
    add_column_if_not_exists('products', 'supplier', 'TEXT')
    add_column_if_not_exists('products', 'expiry_date', 'TEXT')
    add_column_if_not_exists('sales', 'status', 'TEXT DEFAULT "completed"')
    add_column_if_not_exists('sales', 'customer_phone', 'TEXT')
    add_column_if_not_exists('customers', 'total_spent', 'REAL DEFAULT 0')
    add_column_if_not_exists('customers', 'loyalty_points', 'INTEGER DEFAULT 0')
    
    # Insert default data
    conn = get_db()
    c = conn.cursor()
    
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
        c.execute("INSERT INTO users (username, password, role, full_name, email) VALUES (?, ?, ?, ?, ?)",
                  ('admin', admin_pass, 'admin', 'System Administrator', 'admin@generalshop.com'))
        c.execute("INSERT INTO users (username, password, role, full_name, email) VALUES (?, ?, ?, ?, ?)",
                  ('cashier', cashier_pass, 'cashier', 'Store Cashier', 'cashier@generalshop.com'))
    
    # Default settings
    default_settings = {
        'business_name': 'General Shop',
        'logo': '',
        'phone': '+254 700 000 000',
        'email': 'info@generalshop.com',
        'address': 'Nairobi, Kenya',
        'pin': 'A123456789',
        'currency': 'KES',
        'tax_rate': '16',
        'footer': 'Thank you for shopping with us!'
    }
    for key, value in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    
    # Sample products if empty
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.execute("SELECT id FROM categories WHERE name = 'Food' LIMIT 1")
        food_row = c.fetchone()
        if food_row:
            food_id = food_row[0]
            sample_products = [
                ('White Bread', 'BREAD001', '123456', food_id, 50, 70, 100, 5, 'piece', 16, 0, 'Baker\'s Delight', ''),
                ('Fresh Milk 1L', 'MILK001', '123457', food_id, 80, 120, 50, 5, 'litre', 16, 0, 'Dairy Farm', ''),
                ('Sugar 1kg', 'SUGAR001', '123459', food_id, 100, 180, 75, 5, 'kg', 16, 0, 'Sugar Corp', ''),
                ('Cooking Oil 2L', 'OIL001', '123460', food_id, 250, 350, 40, 5, 'litre', 16, 0, 'Oil Company', ''),
            ]
            for p in sample_products:
                c.execute("""INSERT INTO products (name, sku, barcode, category_id, buying_price, 
                             selling_price, stock_quantity, low_stock_threshold, unit, tax_rate, 
                             discount, supplier, expiry_date)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", p)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

# Run initialization
init_db()

# ==================== AUTH DECORATORS ====================

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

# ==================== FRONTEND ROUTES ====================

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    conn = get_db()
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

# ==================== M-PESA HELPERS ====================

def get_mpesa_access_token():
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    if MPESA_ENVIRONMENT == 'production':
        url = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    try:
        response = requests.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET), timeout=30)
        if response.status_code == 200:
            return response.json().get('access_token')
        return None
    except:
        return None

def generate_mpesa_password(shortcode, passkey, timestamp):
    data_to_encode = shortcode + passkey + timestamp
    return base64.b64encode(data_to_encode.encode()).decode('utf-8')

def stk_push_request(phone_number, amount, account_reference="POS Payment", transaction_desc="Payment for goods"):
    access_token = get_mpesa_access_token()
    if not access_token:
        return {'error': 'Failed to get M-Pesa token'}, None
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_mpesa_password(MPESA_SHORTCODE, MPESA_PASSKEY, timestamp)
    
    if phone_number.startswith('0'):
        phone_number = '254' + phone_number[1:]
    elif phone_number.startswith('+'):
        phone_number = phone_number[1:]
    
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

# ==================== API ENDPOINTS ====================

# ---------- CATEGORIES ----------
@app.route('/api/categories')
def get_categories():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, color, icon FROM categories ORDER BY name")
    categories = []
    for row in c.fetchall():
        c.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (row[0],))
        count = c.fetchone()[0]
        categories.append({'id': row[0], 'name': row[1], 'color': row[2], 'icon': row[3], 'product_count': count})
    conn.close()
    return jsonify(categories)

@app.route('/api/categories', methods=['POST'])
@admin_required
def create_category():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)", 
                  (data['name'], data.get('color', '#667eea'), data.get('icon', '📦')))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Category exists'}), 400
    finally:
        conn.close()

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE categories SET name=?, color=?, icon=? WHERE id=?", 
              (data['name'], data.get('color', '#667eea'), data.get('icon', '📦'), category_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE products SET category_id = NULL WHERE category_id = ?", (category_id,))
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- PRODUCTS ----------
@app.route('/api/products')
def get_products():
    category = request.args.get('category_id')
    search = request.args.get('search', '')
    conn = get_db()
    c = conn.cursor()
    
    query = """SELECT p.id, p.name, p.sku, p.barcode, p.selling_price, p.stock_quantity, 
                      p.image_url, c.name as category_name, p.category_id,
                      COALESCE(p.buying_price, 0) as buying_price,
                      COALESCE(p.low_stock_threshold, 5) as low_stock_threshold,
                      COALESCE(p.unit, 'piece') as unit,
                      COALESCE(p.tax_rate, 16) as tax_rate,
                      COALESCE(p.discount, 0) as discount,
                      COALESCE(p.supplier, '') as supplier,
                      COALESCE(p.expiry_date, '') as expiry_date
               FROM products p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE 1=1"""
    params = []
    
    if category and category.isdigit():
        query += " AND p.category_id = ?"
        params.append(int(category))
    if search:
        query += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY p.name"
    c.execute(query, params)
    
    products = []
    for row in c.fetchall():
        products.append({
            'id': row[0], 'name': row[1], 'sku': row[2], 'barcode': row[3],
            'selling_price': row[4], 'stock_quantity': row[5], 'image_url': row[6],
            'category': row[7] if row[7] else 'Uncategorized', 'category_id': row[8],
            'buying_price': row[9] or 0, 'low_stock_threshold': row[10] or 5,
            'unit': row[11] or 'piece', 'tax_rate': row[12] or 16,
            'discount': row[13] or 0, 'supplier': row[14] or '', 'expiry_date': row[15] or ''
        })
    conn.close()
    return jsonify(products)

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT id, name, sku, barcode, category_id, 
                      COALESCE(buying_price, 0) as buying_price, 
                      selling_price, stock_quantity, 
                      COALESCE(low_stock_threshold, 5) as low_stock_threshold,
                      image_url, COALESCE(unit, 'piece') as unit, 
                      COALESCE(tax_rate, 16) as tax_rate, 
                      COALESCE(discount, 0) as discount,
                      COALESCE(supplier, '') as supplier,
                      COALESCE(expiry_date, '') as expiry_date
               FROM products WHERE id = ?""", (product_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({
            'id': row[0], 'name': row[1], 'sku': row[2], 'barcode': row[3],
            'category_id': row[4], 'buying_price': row[5] or 0, 'selling_price': row[6],
            'stock_quantity': row[7], 'low_stock_threshold': row[8] or 5,
            'image_url': row[9], 'unit': row[10] or 'piece', 'tax_rate': row[11] or 16,
            'discount': row[12] or 0, 'supplier': row[13] or '', 'expiry_date': row[14] or ''
        })
    return jsonify({'error': 'Not found'}), 404

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
            unit = request.form.get('unit', 'piece')
            tax_rate = float(request.form.get('tax_rate', 16))
            discount = float(request.form.get('discount', 0))
            supplier = request.form.get('supplier', '')
            expiry_date = request.form.get('expiry_date', '')
            image_file = request.files.get('image')
            image_url = save_product_image(image_file) if image_file and image_file.filename else None
        else:
            data = request.get_json()
            name = data.get('name', '').strip()
            sku = data.get('sku', '').strip() or None
            barcode = data.get('barcode', '').strip() or None
            category_id = data.get('category_id')
            buying_price = float(data.get('buying_price', 0))
            selling_price = float(data.get('selling_price', 0))
            stock_quantity = int(data.get('stock_quantity', 0))
            low_stock_threshold = int(data.get('low_stock_threshold', 5))
            unit = data.get('unit', 'piece')
            tax_rate = float(data.get('tax_rate', 16))
            discount = float(data.get('discount', 0))
            supplier = data.get('supplier', '')
            expiry_date = data.get('expiry_date', '')
            image_url = None
        
        if not name:
            return jsonify({'error': 'Product name required'}), 400
        if selling_price <= 0:
            return jsonify({'error': 'Valid selling price required'}), 400
        
        cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
        
        conn = get_db()
        c = conn.cursor()
        if sku:
            c.execute("SELECT id FROM products WHERE sku = ?", (sku,))
            if c.fetchone():
                conn.close()
                return jsonify({'error': 'SKU already exists'}), 400
        
        c.execute("""INSERT INTO products (name, sku, barcode, category_id, buying_price, selling_price, 
                      stock_quantity, low_stock_threshold, image_url, unit, tax_rate, discount, supplier, expiry_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (name, sku, barcode, cat_id, buying_price, selling_price, stock_quantity, 
               low_stock_threshold, image_url, unit, tax_rate, discount, supplier, expiry_date))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return jsonify({'success': True, 'message': 'Product created', 'product_id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

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
            unit = request.form.get('unit', 'piece')
            tax_rate = float(request.form.get('tax_rate', 16))
            discount = float(request.form.get('discount', 0))
            supplier = request.form.get('supplier', '')
            expiry_date = request.form.get('expiry_date', '')
            image_file = request.files.get('image')
            image_url = save_product_image(image_file) if image_file and image_file.filename else None
            cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
            
            conn = get_db()
            c = conn.cursor()
            if image_url:
                c.execute("""UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, 
                             selling_price=?, low_stock_threshold=?, image_url=?, unit=?, tax_rate=?, 
                             discount=?, supplier=?, expiry_date=? WHERE id=?""",
                          (name, sku, barcode, cat_id, buying_price, selling_price, low_stock_threshold,
                           image_url, unit, tax_rate, discount, supplier, expiry_date, product_id))
            else:
                c.execute("""UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, 
                             selling_price=?, low_stock_threshold=?, unit=?, tax_rate=?, discount=?, 
                             supplier=?, expiry_date=? WHERE id=?""",
                          (name, sku, barcode, cat_id, buying_price, selling_price, low_stock_threshold,
                           unit, tax_rate, discount, supplier, expiry_date, product_id))
            conn.commit()
            conn.close()
        else:
            data = request.get_json()
            cat_id = int(data.get('category_id')) if data.get('category_id') else None
            conn = get_db()
            c = conn.cursor()
            c.execute("""UPDATE products SET name=?, sku=?, barcode=?, category_id=?, buying_price=?, 
                         selling_price=?, low_stock_threshold=?, unit=?, tax_rate=?, discount=?, 
                         supplier=?, expiry_date=? WHERE id=?""",
                      (data['name'], data.get('sku'), data.get('barcode'), cat_id, 
                       data.get('buying_price', 0), data['selling_price'], 
                       data.get('low_stock_threshold', 5), data.get('unit', 'piece'),
                       data.get('tax_rate', 16), data.get('discount', 0),
                       data.get('supplier', ''), data.get('expiry_date', ''), product_id))
            conn.commit()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- INVENTORY ----------
@app.route('/api/inventory/<int:product_id>', methods=['POST'])
@admin_required
def inventory_adjustment(product_id):
    data = request.get_json()
    type_ = data.get('type')
    quantity = int(data.get('quantity', 0))
    note = data.get('note', '')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT stock_quantity FROM products WHERE id = ?", (product_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    
    current_stock = row[0]
    
    if type_ == 'in':
        new_stock = current_stock + quantity
    elif type_ == 'out':
        if current_stock < quantity:
            conn.close()
            return jsonify({'error': 'Insufficient stock'}), 400
        new_stock = current_stock - quantity
    elif type_ == 'adjust':
        new_stock = quantity
    elif type_ == 'damaged':
        if current_stock < quantity:
            conn.close()
            return jsonify({'error': 'Insufficient stock'}), 400
        new_stock = current_stock - quantity
    elif type_ == 'returned':
        new_stock = current_stock + quantity
    else:
        conn.close()
        return jsonify({'error': 'Invalid type'}), 400
    
    c.execute("UPDATE products SET stock_quantity = ? WHERE id = ?", (new_stock, product_id))
    c.execute("""INSERT INTO inventory_transactions (product_id, type, quantity, note) 
                 VALUES (?, ?, ?, ?)""", (product_id, type_, quantity, note))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'new_stock': new_stock})

@app.route('/api/inventory/transactions')
@admin_required
def get_inventory_transactions():
    product_id = request.args.get('product_id')
    conn = get_db()
    c = conn.cursor()
    if product_id:
        c.execute("""SELECT i.*, p.name FROM inventory_transactions i 
                     JOIN products p ON i.product_id = p.id 
                     WHERE i.product_id = ? ORDER BY i.created_at DESC LIMIT 50""", (product_id,))
    else:
        c.execute("""SELECT i.*, p.name FROM inventory_transactions i 
                     JOIN products p ON i.product_id = p.id 
                     ORDER BY i.created_at DESC LIMIT 50""")
    transactions = []
    for row in c.fetchall():
        transactions.append({
            'id': row[0], 'product_id': row[1], 'type': row[2], 
            'quantity': row[3], 'note': row[4], 'created_at': row[5], 'product_name': row[6]
        })
    conn.close()
    return jsonify(transactions)

# ---------- SALES ----------
@app.route('/api/sale', methods=['POST'])
@cashier_required
def create_sale():
    data = request.get_json()
    items = data.get('items', [])
    customer_name = data.get('customer_name', 'Walk-in Customer')
    customer_phone = data.get('customer_phone', '')
    payment_method = data.get('payment_method', 'cash')
    mpesa_transaction_id = data.get('mpesa_transaction_id', None)
    
    if not items:
        return jsonify({'error': 'No items in sale'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    subtotal = sum(item['price'] * item['quantity'] for item in items)
    tax_rate = float(data.get('tax_rate', 16))
    tax = subtotal * (tax_rate / 100)
    total = subtotal + tax
    
    order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    receipt_number = f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    c.execute("""INSERT INTO sales (order_number, user_id, customer_name, customer_phone, 
                      subtotal, tax, total, payment_method, receipt_number, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (order_number, session['user_id'], customer_name, customer_phone, 
               subtotal, tax, total, payment_method, receipt_number, 'completed'))
    sale_id = c.lastrowid
    
    for item in items:
        c.execute("INSERT INTO sale_items (sale_id, product_id, quantity, price_at_time) VALUES (?, ?, ?, ?)",
                  (sale_id, item['id'], item['quantity'], item['price']))
        c.execute("UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?", 
                  (item['quantity'], item['id']))
    
    if payment_method == 'mpesa' and mpesa_transaction_id:
        c.execute("UPDATE mpesa_transactions SET status = 'completed', receipt_number = ? WHERE checkout_request_id = ?",
                  (receipt_number, mpesa_transaction_id))
    
    # Update customer
    if customer_name and customer_phone:
        c.execute("SELECT id FROM customers WHERE phone = ?", (customer_phone,))
        customer = c.fetchone()
        if customer:
            c.execute("UPDATE customers SET total_spent = total_spent + ?, loyalty_points = loyalty_points + ? WHERE id = ?",
                      (total, int(total / 100), customer[0]))
        else:
            c.execute("INSERT INTO customers (name, phone, total_spent, loyalty_points) VALUES (?, ?, ?, ?)",
                      (customer_name, customer_phone, total, int(total / 100)))
    
    conn.commit()
    
    c.execute("""SELECT p.name, si.quantity, si.price_at_time FROM sale_items si 
                 JOIN products p ON si.product_id = p.id WHERE si.sale_id = ?""", (sale_id,))
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
    return jsonify({'success': True, 'sale_id': sale_id, 'order_number': order_number, 
                    'receipt_number': receipt_number, 'receipt_data': receipt_data})

@app.route('/api/sales/report')
@admin_required
def sales_report():
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    method = request.args.get('method')
    
    conn = get_db()
    c = conn.cursor()
    
    query = """SELECT id, order_number, customer_name, 
                      COALESCE(subtotal, 0) as subtotal, 
                      COALESCE(tax, 0) as tax, 
                      COALESCE(total, 0) as total, 
                      payment_method, sale_date,
                      (SELECT COUNT(*) FROM sale_items WHERE sale_id = sales.id) as item_count
               FROM sales WHERE (status IS NULL OR status != 'refunded')"""
    params = []
    
    if from_date:
        query += " AND DATE(sale_date) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND DATE(sale_date) <= ?"
        params.append(to_date)
    if method and method != 'all':
        query += " AND payment_method = ?"
        params.append(method)
    
    query += " ORDER BY sale_date DESC LIMIT 200"
    c.execute(query, params)
    
    sales = []
    for row in c.fetchall():
        sales.append({
            'id': row[0], 'order_number': row[1], 'customer_name': row[2] or 'Walk-in',
            'subtotal': row[3] or 0, 'tax': row[4] or 0, 'total': row[5] or 0,
            'payment_method': row[6], 'date': row[7], 'item_count': row[8] or 0
        })
    conn.close()
    return jsonify({'sales': sales})

@app.route('/api/sales/<int:sale_id>/refund', methods=['POST'])
@admin_required
def refund_sale(sale_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get sale items
    c.execute("SELECT product_id, quantity FROM sale_items WHERE sale_id = ?", (sale_id,))
    items = c.fetchall()
    
    # Restore stock
    for product_id, quantity in items:
        c.execute("UPDATE products SET stock_quantity = stock_quantity + ? WHERE id = ?", (quantity, product_id))
    
    # Mark sale as refunded
    c.execute("UPDATE sales SET status = 'refunded' WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/receipt/<int:sale_id>')
def view_receipt(sale_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
    sale = c.fetchone()
    if not sale:
        return "Sale not found", 404
    
    c.execute("""SELECT p.name, si.quantity, si.price_at_time FROM sale_items si 
                 JOIN products p ON si.product_id = p.id WHERE si.sale_id = ?""", (sale_id,))
    items = c.fetchall()
    conn.close()
    
    # Get values with fallbacks and convert to proper types
    try:
        order_num = sale[1] if len(sale) > 1 and sale[1] is not None else 'N/A'
        customer = sale[3] if len(sale) > 3 and sale[3] is not None else 'Walk-in'
        subtotal = float(sale[4]) if len(sale) > 4 and sale[4] is not None else 0
        tax = float(sale[5]) if len(sale) > 5 and sale[5] is not None else 0
        total = float(sale[6]) if len(sale) > 6 and sale[6] is not None else 0
        payment = sale[7] if len(sale) > 7 and sale[7] is not None else 'Cash'
        receipt = sale[8] if len(sale) > 8 and sale[8] is not None else 'N/A'
        date = sale[10] if len(sale) > 10 and sale[10] is not None else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        subtotal = 0
        tax = 0
        total = 0
        order_num = 'N/A'
        customer = 'Walk-in'
        payment = 'Cash'
        receipt = 'N/A'
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Get business settings
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings WHERE key IN ('business_name', 'phone', 'address', 'footer')")
    settings = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    business_name = settings.get('business_name', 'GENERAL SHOP')
    phone = settings.get('phone', '+254 700 000 000')
    address = settings.get('address', 'Nairobi, Kenya')
    footer = settings.get('footer', 'Thank you for shopping with us!')
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Receipt</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Courier New', monospace; 
            width: 300px; 
            margin: 20px auto; 
            padding: 20px;
            background: white;
        }}
        .header {{ text-align: center; margin-bottom: 15px; }}
        .header h2 {{ font-size: 18px; font-weight: bold; }}
        .header p {{ font-size: 11px; color: #666; margin: 3px 0; }}
        .divider {{ border-top: 1px dashed #000; margin: 10px 0; }}
        .item {{ display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; }}
        .total {{ font-weight: bold; font-size: 16px; }}
        .footer {{ text-align: center; font-size: 11px; color: #666; margin-top: 15px; }}
        .text-center {{ text-align: center; }}
        .order-info {{ font-size: 12px; }}
        @media print {{
            body {{ margin: 0; padding: 10px; }}
            .no-print {{ display: none; }}
        }}
    </style>
    </head>
    <body>
        <div class="header">
            <h2>{business_name}</h2>
            <p>{address}</p>
            <p>Tel: {phone}</p>
            <div class="divider"></div>
            <p class="order-info">
                Order: {order_num}<br>
                Receipt: {receipt}<br>
                Date: {date}<br>
                Customer: {customer}
            </p>
            <div class="divider"></div>
        </div>
        
        <div class="items">
    """
    
    for item in items:
        try:
            name = item[0] if item[0] else 'Unknown'
            quantity = int(item[1]) if item[1] else 0
            price = float(item[2]) if item[2] else 0
            html += f"""
                <div class="item">
                    <span>{name} x{quantity}</span>
                    <span>Ksh {price * quantity:.2f}</span>
                </div>
            """
        except (ValueError, TypeError):
            continue
    
    html += f"""
        </div>
        
        <div class="divider"></div>
        
        <div class="item">
            <span>Subtotal:</span>
            <span>Ksh {subtotal:.2f}</span>
        </div>
        <div class="item">
            <span>VAT:</span>
            <span>Ksh {tax:.2f}</span>
        </div>
        <div class="item total">
            <span>TOTAL:</span>
            <span>Ksh {total:.2f}</span>
        </div>
        
        <div class="divider"></div>
        
        <div class="text-center">
            Payment: {payment}
        </div>
        
        <div class="footer">
            <div class="divider"></div>
            {footer}
            <br>
            <span style="font-size: 10px;">Thank you for shopping with us!</span>
        </div>
        
        <div class="text-center no-print" style="margin-top: 20px;">
            <button onclick="window.print()" style="padding: 10px 30px; background: #1e3c72; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px;">
                🖨️ Print Receipt
            </button>
            <br><br>
            <button onclick="window.close()" style="padding: 8px 20px; background: #666; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 12px;">
                Close
            </button>
        </div>
        
        <script>
            window.onload = function() {{
                setTimeout(function() {{
                    window.print();
                }}, 500);
            }};
            
            window.onafterprint = function() {{
                setTimeout(function() {{
                    window.close();
                }}, 1000);
            }};
            
            setTimeout(function() {{
                window.close();
            }}, 10000);
        </script>
    </body>
    </html>
    """
    return html

@app.route('/api/print/receipt', methods=['POST'])
def print_receipt():
    """Print receipt - opens a printable receipt page"""
    data = request.get_json()
    receipt_data = data.get('receipt_data')
    if not receipt_data:
        return jsonify({'error': 'No receipt data'}), 400
    
    # Get business settings for receipt
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings WHERE key IN ('business_name', 'phone', 'address', 'footer')")
    settings = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    business_name = settings.get('business_name', 'GENERAL SHOP')
    phone = settings.get('phone', '+254 700 000 000')
    address = settings.get('address', 'Nairobi, Kenya')
    footer = settings.get('footer', 'Thank you for shopping with us!')
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Receipt</title>
        <meta charset="UTF-8">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Courier New', monospace; 
                width: 300px; 
                margin: 20px auto; 
                padding: 20px;
                background: white;
            }}
            .header {{ text-align: center; margin-bottom: 15px; }}
            .header h2 {{ font-size: 18px; font-weight: bold; }}
            .header p {{ font-size: 11px; color: #666; margin: 3px 0; }}
            .divider {{ border-top: 1px dashed #000; margin: 10px 0; }}
            .item {{ display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; }}
            .total {{ font-weight: bold; font-size: 16px; }}
            .footer {{ text-align: center; font-size: 11px; color: #666; margin-top: 15px; }}
            .payment {{ font-size: 13px; }}
            .text-center {{ text-align: center; }}
            .order-info {{ font-size: 12px; }}
            @media print {{
                body {{ margin: 0; padding: 10px; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>{business_name}</h2>
            <p>{address}</p>
            <p>Tel: {phone}</p>
            <div class="divider"></div>
            <p class="order-info">
                Order: {receipt_data.get('order_number', 'N/A')}<br>
                Receipt: {receipt_data.get('receipt_number', 'N/A')}<br>
                Date: {receipt_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}<br>
                Customer: {receipt_data.get('customer_name', 'Walk-in')}
            </p>
            <div class="divider"></div>
        </div>
        
        <div class="items">
    """
    
    for item in receipt_data.get('items', []):
        html += f"""
            <div class="item">
                <span>{item.get('name', 'Unknown')} x{item.get('quantity', 0)}</span>
                <span>Ksh {item.get('price', 0) * item.get('quantity', 0):.2f}</span>
            </div>
        """
    
    html += f"""
        </div>
        
        <div class="divider"></div>
        
        <div class="item">
            <span>Subtotal:</span>
            <span>Ksh {receipt_data.get('subtotal', 0):.2f}</span>
        </div>
        <div class="item">
            <span>VAT 16%:</span>
            <span>Ksh {receipt_data.get('tax', 0):.2f}</span>
        </div>
        <div class="item total">
            <span>TOTAL:</span>
            <span>Ksh {receipt_data.get('total', 0):.2f}</span>
        </div>
        
        <div class="divider"></div>
        
        <div class="payment text-center">
            Payment: {receipt_data.get('payment_method', 'Cash')}
        </div>
        
        <div class="footer">
            <div class="divider"></div>
            {footer}
            <br>
            <span style="font-size: 10px;">Thank you for shopping with us!</span>
        </div>
        
        <div class="text-center no-print" style="margin-top: 20px;">
            <button onclick="window.print()" style="padding: 10px 30px; background: #1e3c72; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px;">
                🖨️ Print Receipt
            </button>
            <br><br>
            <button onclick="window.close()" style="padding: 8px 20px; background: #666; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 12px;">
                Close
            </button>
        </div>
        
        <script>
            // Auto print when page loads
            window.onload = function() {{
                setTimeout(function() {{
                    window.print();
                }}, 500);
            }};
            
            // Close after print or after 10 seconds
            window.onafterprint = function() {{
                setTimeout(function() {{
                    window.close();
                }}, 1000);
            }};
            
            // Fallback: close after 10 seconds even if print dialog is cancelled
            setTimeout(function() {{
                window.close();
            }}, 10000);
        </script>
    </body>
    </html>
    """
    return html

# ---------- M-PESA ----------
@app.route('/api/mpesa/pay', methods=['POST'])
@cashier_required
def mpesa_payment():
    data = request.get_json()
    phone_number = data.get('phone_number')
    amount = data.get('amount')
    
    if not phone_number or not amount:
        return jsonify({'error': 'Phone number and amount required'}), 400
    
    error, response = stk_push_request(phone_number, amount)
    if error:
        return jsonify({'error': error.get('error', 'STK push failed')}), 400
    
    checkout_request_id = response.get('CheckoutRequestID')
    if not checkout_request_id:
        return jsonify({'error': 'No CheckoutRequestID returned'}), 500
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO mpesa_transactions (checkout_request_id, phone_number, amount, status) VALUES (?, ?, ?, 'pending')",
              (checkout_request_id, phone_number, amount))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'checkout_request_id': checkout_request_id,
        'message': 'STK Push sent. Check your phone to complete the payment.'
    })

@app.route('/api/mpesa/callback', methods=['POST'])
def mpesa_callback():
    data = request.get_json()
    body = data.get('Body', {})
    stk_callback = body.get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    result_code = stk_callback.get('ResultCode')
    
    conn = get_db()
    c = conn.cursor()
    
    if result_code == 0:
        callback_metadata = stk_callback.get('CallbackMetadata', {})
        items = callback_metadata.get('Item', [])
        receipt_number = None
        for item in items:
            if item.get('Name') == 'MpesaReceiptNumber':
                receipt_number = item.get('Value')
        c.execute("UPDATE mpesa_transactions SET status = 'completed', receipt_number = ? WHERE checkout_request_id = ?",
                  (receipt_number, checkout_request_id))
    else:
        c.execute("UPDATE mpesa_transactions SET status = 'failed' WHERE checkout_request_id = ?", (checkout_request_id,))
    
    conn.commit()
    conn.close()
    return jsonify({'ResultCode': 0, 'ResultDesc': 'Success'})

@app.route('/api/mpesa/status/<checkout_request_id>')
def mpesa_status(checkout_request_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status, receipt_number FROM mpesa_transactions WHERE checkout_request_id = ?", (checkout_request_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return jsonify({'status': result[0], 'receipt_number': result[1]})
    return jsonify({'status': 'not_found'}), 404

@app.route('/api/mpesa/transactions')
@admin_required
def mpesa_transactions():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT receipt_number, phone_number, amount, status, transaction_date FROM mpesa_transactions ORDER BY transaction_date DESC LIMIT 50")
    transactions = [{'receipt_number': row[0] or '-', 'phone_number': row[1], 'amount': row[2] or 0, 'status': row[3], 'date': row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(transactions)

# ---------- DASHBOARD ----------
@app.route('/api/dashboard/stats')
@admin_required
def dashboard_stats():
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) = ? AND (status IS NULL OR status != 'refunded')", (today,))
    today_sales, today_count = c.fetchone()
    
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) >= ? AND (status IS NULL OR status != 'refunded')", (week_ago,))
    weekly_sales, weekly_count = c.fetchone()
    
    c.execute("SELECT COALESCE(SUM(total), 0), COUNT(*) FROM sales WHERE DATE(sale_date) >= ? AND (status IS NULL OR status != 'refunded')", (month_ago,))
    monthly_sales, monthly_count = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM products")
    total_products = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM customers")
    total_customers = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM mpesa_transactions WHERE status = 'completed'")
    mpesa_count, mpesa_total = c.fetchone()
    
    c.execute("SELECT COALESCE(SUM(total), 0) FROM sales WHERE status IS NULL OR status != 'refunded'")
    total_revenue = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM products WHERE stock_quantity <= low_stock_threshold")
    low_stock_products = c.fetchone()[0]
    
    conn.close()
    return jsonify({
        'today_sales': {'amount': float(today_sales or 0), 'count': today_count or 0},
        'weekly_sales': {'amount': float(weekly_sales or 0), 'count': weekly_count or 0},
        'monthly_sales': {'amount': float(monthly_sales or 0), 'count': monthly_count or 0},
        'total_products': total_products or 0,
        'total_customers': total_customers or 0,
        'mpesa_transactions': {'count': mpesa_count or 0, 'total': float(mpesa_total or 0)},
        'total_revenue': float(total_revenue or 0),
        'low_stock_products': low_stock_products or 0
    })

@app.route('/api/sales-chart')
@admin_required
def sales_chart():
    period = request.args.get('period', 'week')
    conn = get_db()
    c = conn.cursor()
    
    labels = []
    values = []
    
    if period == 'week':
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            labels.append((datetime.now() - timedelta(days=i)).strftime('%a'))
            c.execute("SELECT COALESCE(SUM(total), 0) FROM sales WHERE DATE(sale_date) = ? AND (status IS NULL OR status != 'refunded')", (date,))
            val = c.fetchone()[0]
            values.append(float(val or 0))
    else:  # month
        for i in range(29, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            labels.append((datetime.now() - timedelta(days=i)).strftime('%d %b'))
            c.execute("SELECT COALESCE(SUM(total), 0) FROM sales WHERE DATE(sale_date) = ? AND (status IS NULL OR status != 'refunded')", (date,))
            val = c.fetchone()[0]
            values.append(float(val or 0))
    
    conn.close()
    return jsonify({'labels': labels, 'values': values})

@app.route('/api/best-sellers')
@admin_required
def best_sellers():
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""SELECT p.name, COALESCE(SUM(si.quantity), 0) as total_sold, COALESCE(SUM(si.quantity * si.price_at_time), 0) as revenue
                 FROM sale_items si
                 JOIN products p ON si.product_id = p.id
                 JOIN sales s ON si.sale_id = s.id
                 WHERE (s.status IS NULL OR s.status != 'refunded')
                 GROUP BY p.id
                 ORDER BY total_sold DESC
                 LIMIT 10""")
    products = [{'name': row[0], 'total_sold': row[1] or 0, 'revenue': row[2] or 0} for row in c.fetchall()]
    conn.close()
    return jsonify(products)

@app.route('/api/recent/sales')
@admin_required
def recent_sales():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT order_number, total, payment_method, sale_date FROM sales WHERE status IS NULL OR status != 'refunded' ORDER BY sale_date DESC LIMIT 10")
    sales = [{'er_number': row[0], 'total': float(row[1] or 0), 'payment_method': row[2], 'date': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(sales)

@app.route('/api/low-stock/products')
@admin_required
def low_stock_products():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, sku, stock_quantity, low_stock_threshold FROM products WHERE stock_quantity <= low_stock_threshold ORDER BY stock_quantity ASC LIMIT 10")
    products = [{'name': row[0], 'sku': row[1], 'stock': row[2] or 0, 'threshold': row[3] or 5} for row in c.fetchall()]
    conn.close()
    return jsonify(products)

# ---------- USERS ----------
@app.route('/api/users')
@admin_required
def get_users():
    conn = get_db()
    c = conn.cursor()
    has_email = column_exists('users', 'email')
    if has_email:
        c.execute("SELECT id, username, full_name, email, role, created_at FROM users ORDER BY created_at DESC")
    else:
        c.execute("SELECT id, username, full_name, '' as email, role, created_at FROM users ORDER BY created_at DESC")
    users = [{'id': row[0], 'username': row[1], 'full_name': row[2], 'email': row[3] or '', 'role': row[4], 'created_at': row[5]} for row in c.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    has_email = column_exists('users', 'email')
    if has_email:
        c.execute("SELECT id, username, full_name, email, role FROM users WHERE id = ?", (user_id,))
    else:
        c.execute("SELECT id, username, full_name, '' as email, role FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify({'id': row[0], 'username': row[1], 'full_name': row[2], 'email': row[3] or '', 'role': row[4]})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = generate_password_hash(data.get('password'))
    full_name = data.get('full_name', '')
    email = data.get('email', '')
    role = data.get('role', 'cashier')
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, full_name, email, role) VALUES (?, ?, ?, ?, ?)",
                  (username, password, full_name, email, role))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username exists'}), 400
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    data = request.get_json()
    username = data.get('username')
    full_name = data.get('full_name', '')
    email = data.get('email', '')
    role = data.get('role', 'cashier')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0] == 'admin' and username != 'admin':
        conn.close()
        return jsonify({'error': 'Cannot rename admin user'}), 400
    
    if data.get('password'):
        password = generate_password_hash(data['password'])
        c.execute("UPDATE users SET username=?, full_name=?, email=?, role=?, password=? WHERE id=?",
                  (username, full_name, email, role, password, user_id))
    else:
        c.execute("UPDATE users SET username=?, full_name=?, email=?, role=? WHERE id=?",
                  (username, full_name, email, role, user_id))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0] == 'admin':
        conn.close()
        return jsonify({'error': 'Cannot delete admin user'}), 400
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- SETTINGS ----------
@app.route('/api/settings')
def get_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    settings = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
@admin_required
def update_settings():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    for key, value in data.items():
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- CUSTOMERS ----------
@app.route('/api/customers')
@admin_required
def get_customers():
    search = request.args.get('search', '')
    conn = get_db()
    c = conn.cursor()
    query = """SELECT id, name, phone, email, 
                      COALESCE(total_spent, 0) as total_spent, 
                      COALESCE(loyalty_points, 0) as loyalty_points 
               FROM customers WHERE 1=1"""
    params = []
    if search:
        query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    query += " ORDER BY total_spent DESC"
    c.execute(query, params)
    customers = [{'id': row[0], 'name': row[1] or 'Unknown', 'phone': row[2] or '-', 'email': row[3] or '-', 
                  'total_spent': row[4] or 0, 'loyalty_points': row[5] or 0} for row in c.fetchall()]
    conn.close()
    return jsonify(customers)

@app.route('/api/customers', methods=['POST'])
@admin_required
def create_customer():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO customers (name, phone, email, address) VALUES (?, ?, ?, ?)",
                  (data.get('name'), data.get('phone'), data.get('email'), data.get('address')))
        conn.commit()
        return jsonify({'success': True, 'id': c.lastrowid})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Phone number exists'}), 400
    finally:
        conn.close()

# ---------- ORDERS ----------
@app.route('/api/orders')
@admin_required
def get_orders():
    status = request.args.get('status', 'all')
    conn = get_db()
    c = conn.cursor()
    query = "SELECT id, order_number, customer_name, total, status, created_at FROM orders WHERE 1=1"
    params = []
    if status != 'all':
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    orders = [{'id': row[0], 'order_number': row[1], 'customer_name': row[2] or 'Walk-in', 
               'total': row[3] or 0, 'status': row[4] or 'pending', 'date': row[5]} for row in c.fetchall()]
    conn.close()
    return jsonify(orders)

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@admin_required
def update_order_status(order_id):
    data = request.get_json()
    status = data.get('status')
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ---------- REPORTS ----------
@app.route('/api/reports/<report_type>')
@admin_required
def generate_report(report_type):
    conn = get_db()
    c = conn.cursor()
    data = []
    title = ''
    
    if report_type == 'sales':
        title = 'Sales Report'
        c.execute("""SELECT DATE(sale_date) as date, COUNT(*) as orders, 
                          COALESCE(SUM(total), 0) as total_sales
                     FROM sales WHERE status IS NULL OR status != 'refunded'
                     GROUP BY DATE(sale_date)
                     ORDER BY date DESC LIMIT 30""")
        for row in c.fetchall():
            data.append({'Date': row[0], 'Orders': row[1], 'Total Sales': f"Ksh {row[2]:,.2f}"})
    
    elif report_type == 'inventory':
        title = 'Inventory Report'
        c.execute("""SELECT name, sku, stock_quantity, low_stock_threshold,
                          CASE WHEN stock_quantity = 0 THEN 'Out of Stock'
                               WHEN stock_quantity <= low_stock_threshold THEN 'Low Stock'
                               ELSE 'In Stock' END as status
                     FROM products ORDER BY stock_quantity ASC""")
        for row in c.fetchall():
            data.append({'Product': row[0], 'SKU': row[1] or '-', 'Stock': row[2] or 0, 
                        'Threshold': row[3] or 5, 'Status': row[4]})
    
    elif report_type == 'profit':
        title = 'Profit Report'
        c.execute("""SELECT DATE(sale_date) as date,
                          COALESCE(SUM(total - subtotal), 0) as gross_profit,
                          COALESCE(SUM(total), 0) as revenue
                     FROM sales WHERE status IS NULL OR status != 'refunded'
                     GROUP BY DATE(sale_date)
                     ORDER BY date DESC LIMIT 30""")
        for row in c.fetchall():
            data.append({'Date': row[0], 'Gross Profit': f"Ksh {row[1]:,.2f}", 
                        'Revenue': f"Ksh {row[2]:,.2f}"})
    
    elif report_type == 'tax':
        title = 'Tax Report'
        c.execute("""SELECT DATE(sale_date) as date,
                          COALESCE(SUM(tax), 0) as vat_collected,
                          COUNT(*) as transactions
                     FROM sales WHERE status IS NULL OR status != 'refunded'
                     GROUP BY DATE(sale_date)
                     ORDER BY date DESC LIMIT 30""")
        for row in c.fetchall():
            data.append({'Date': row[0], 'VAT Collected': f"Ksh {row[1]:,.2f}", 'Transactions': row[2]})
    
    elif report_type == 'products':
        title = 'Product Performance'
        c.execute("""SELECT p.name, COALESCE(SUM(si.quantity), 0) as sold,
                          COALESCE(SUM(si.quantity * si.price_at_time), 0) as revenue
                     FROM products p
                     LEFT JOIN sale_items si ON p.id = si.product_id
                     LEFT JOIN sales s ON si.sale_id = s.id AND (s.status IS NULL OR s.status != 'refunded')
                     GROUP BY p.id
                     ORDER BY sold DESC LIMIT 20""")
        for row in c.fetchall():
            data.append({'Product': row[0], 'Units Sold': row[1] or 0, 'Revenue': f"Ksh {row[2]:,.2f}"})
    
    elif report_type == 'customers':
        title = 'Customer Report'
        c.execute("""SELECT name, phone, 
                          COALESCE(total_spent, 0) as total_spent, 
                          COALESCE(loyalty_points, 0) as loyalty_points
                     FROM customers ORDER BY total_spent DESC LIMIT 20""")
        for row in c.fetchall():
            data.append({'Customer': row[0] or 'Unknown', 'Phone': row[1] or '-', 
                        'Total Spent': f"Ksh {row[2]:,.2f}", 'Loyalty Points': row[3] or 0})
    
    conn.close()
    return jsonify({'title': title, 'data': data})

# ---------- EXPORTS ----------
@app.route('/api/export/products')
@admin_required
def export_products():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT name, sku, barcode, selling_price, stock_quantity, 
                      COALESCE(c.name, '') as category, supplier, unit
               FROM products p LEFT JOIN categories c ON p.category_id = c.id""")
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'SKU', 'Barcode', 'Selling Price', 'Stock', 'Category', 'Supplier', 'Unit'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', 
                     as_attachment=True, download_name=f'products_{datetime.now().strftime("%Y%m%d")}.csv')

@app.route('/api/export/inventory')
@admin_required
def export_inventory():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT name, sku, stock_quantity, low_stock_threshold, buying_price, selling_price
               FROM products ORDER BY name""")
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Product', 'SKU', 'Stock', 'Threshold', 'Buying Price', 'Selling Price'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f'inventory_{datetime.now().strftime("%Y%m%d")}.csv')

@app.route('/api/export/sales')
@admin_required
def export_sales():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT order_number, customer_name, subtotal, tax, total, payment_method, sale_date
               FROM sales WHERE status IS NULL OR status != 'refunded' ORDER BY sale_date DESC""")
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Order', 'Customer', 'Subtotal', 'Tax', 'Total', 'Payment', 'Date'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f'sales_{datetime.now().strftime("%Y%m%d")}.csv')

@app.route('/api/export/mpesa/csv')
@admin_required
def export_mpesa_csv():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT receipt_number, phone_number, amount, status, transaction_date FROM mpesa_transactions ORDER BY transaction_date DESC")
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Receipt Number', 'Phone Number', 'Amount', 'Status', 'Date'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f'mpesa_{datetime.now().strftime("%Y%m%d")}.csv')

@app.route('/api/export/orders')
@admin_required
def export_orders():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT order_number, customer_name, total, status, created_at FROM orders ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Order', 'Customer', 'Total', 'Status', 'Date'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f'orders_{datetime.now().strftime("%Y%m%d")}.csv')

# ---------- STATIC FILES ----------
@app.route('/static/uploads/products/<filename>')
def uploaded_file(filename):
    filepath = os.path.join('static/uploads/products', filename)
    if not os.path.exists(filepath):
        return '', 404
    return send_file(filepath)

# ==================== RUN SERVER ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 GENERAL SHOP POS SYSTEM STARTING...")
    print("="*60)
    print("\n📍 http://127.0.0.1:5000")
    print("👤 Admin: admin / admin123")
    print("👤 Cashier: cashier / cashier123")
    print("📸 Images: PNG, JPG, JPEG, GIF, WEBP")
    print("💰 M-Pesa: Real STK Push (Daraja API)")
    print("📊 Full Admin Dashboard with all modules")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)