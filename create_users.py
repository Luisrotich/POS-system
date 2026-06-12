import sqlite3
from werkzeug.security import generate_password_hash

def create_users():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Create users table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Delete existing users to avoid conflicts
    c.execute("DELETE FROM users WHERE username IN ('admin', 'cashier')")
    
    # Create new users with proper password hashing
    admin_pass = generate_password_hash('admin123')
    cashier_pass = generate_password_hash('cashier123')
    
    c.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
              ('admin', admin_pass, 'admin', 'System Administrator'))
    
    c.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
              ('cashier', cashier_pass, 'cashier', 'Store Cashier'))
    
    conn.commit()
    
    # Verify users were inserted correctly
    c.execute("SELECT id, username, role FROM users")
    users = c.fetchall()
    print("\n=== Users Created Successfully ===")
    for user in users:
        print(f"ID: {user[0]}, Username: {user[1]}, Role: {user[2]}")
    
    # Test password verification
    c.execute("SELECT password FROM users WHERE username = 'admin'")
    stored_hash = c.fetchone()[0]
    print(f"\nAdmin password hash: {stored_hash[:30]}...")
    print(f"Password 'admin123' verification: {generate_password_hash('admin123') == stored_hash}")
    
    conn.close()
    print("\n✅ Database setup complete! You can now run app.py")

if __name__ == '__main__':
    create_users()