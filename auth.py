# auth.py
from functools import wraps
from flask import session, jsonify, request, redirect, url_for

def login_required(f):
    """Decorator to require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def cashier_required(f):
    """Decorator to require cashier or admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        if session.get('role') not in ['admin', 'cashier']:
            return jsonify({'error': 'Cashier access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def shop_required(f):
    """Decorator to require a shop to be selected"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        shop_id = session.get('shop_id')
        if not shop_id:
            return jsonify({'error': 'No shop selected. Please select a shop first.'}), 400
        return f(*args, **kwargs)
    return decorated_function

def require_shop_selected(f):
    """Decorator to require a shop to be selected (redirects to shop selection)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        if not session.get('shop_id'):
            return redirect(url_for('select_shop'))
        return f(*args, **kwargs)
    return decorated_function

def redirect_if_logged_in(f):
    """Decorator to redirect if user is already logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            if session.get('role') == 'admin':
                return redirect(url_for('admin_panel'))
            elif session.get('shop_id'):
                return redirect(url_for('pos'))
            else:
                return redirect(url_for('select_shop'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get the current user from session"""
    if 'user_id' not in session:
        return None
    return {
        'id': session.get('user_id'),
        'username': session.get('username'),
        'role': session.get('role'),
        'shop_id': session.get('shop_id'),
        'shop_name': session.get('shop_name')
    }

def get_shop_id():
    """Get the current shop ID from session"""
    return session.get('shop_id')

def get_shop_name():
    """Get the current shop name from session"""
    return session.get('shop_name', 'No Shop Selected')

def set_shop_context(shop_id, shop_name=None):
    """Helper to set shop context in session"""
    session['shop_id'] = shop_id
    if shop_name:
        session['shop_name'] = shop_name
    return True

def clear_shop_context():
    """Helper to clear shop context from session"""
    session.pop('shop_id', None)
    session.pop('shop_name', None)
    return True

def has_shop_access(shop_id):
    """Check if current user has access to a specific shop"""
    if 'user_id' not in session:
        return False
    role = session.get('role')
    if role == 'admin':
        return True  # Admin has access to all shops
    user_shop_id = session.get('shop_id')
    return user_shop_id == shop_id

def is_admin():
    """Check if current user is admin"""
    return session.get('role') == 'admin'

def is_cashier():
    """Check if current user is cashier"""
    return session.get('role') == 'cashier'

def require_shop_owner(f):
    """Decorator to require that the user owns or has access to the shop"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get shop_id from kwargs or request
        shop_id = kwargs.get('shop_id') 
        if not shop_id:
            shop_id = request.json.get('shop_id') if request.is_json else None
        
        if not shop_id:
            return jsonify({'error': 'Shop ID required'}), 400
        
        # Admin has access to all shops
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
        
        # Cashier must match their assigned shop
        user_shop_id = session.get('shop_id')
        if user_shop_id != shop_id:
            return jsonify({'error': 'You do not have access to this shop'}), 403
        
        return f(*args, **kwargs)
    return decorated_function