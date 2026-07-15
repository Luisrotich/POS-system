import sqlite3
from werkzeug.security import generate_password_hash

def reset_admin():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Check if admin exists
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    admin = c.fetchone()
    
    if admin:
        # Reset password
        new_password = generate_password_hash('admin123')
        c.execute("UPDATE users SET password = ? WHERE username = 'admin'", (new_password,))
        print("✅ Admin password reset to: admin123")
    else:
        # Create admin
        admin_pass = generate_password_hash('admin123')
        cashier_pass = generate_password_hash('cashier123')
        
        # Get default shop
        c.execute("SELECT id FROM shops LIMIT 1")
        shop = c.fetchone()
        shop_id = shop[0] if shop else None
        
        c.execute("""
            INSERT INTO users (username, password, role, full_name, email, shop_id) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('admin', admin_pass, 'admin', 'System Administrator', 'admin@generalshop.com', shop_id))
        
        c.execute("""
            INSERT INTO users (username, password, role, full_name, email, shop_id) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('cashier', cashier_pass, 'cashier', 'Store Cashier', 'cashier@generalshop.com', shop_id))
        
        print("✅ Admin and Cashier users created!")
        print("👤 Admin: admin / admin123")
        print("👤 Cashier: cashier / cashier123")
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*40)
    print("🔐 Login Credentials:")
    print("👤 Admin: admin")
    print("🔑 Password: admin123")
    print("="*40)

if __name__ == '__main__':
    reset_admin()