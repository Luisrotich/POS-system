# setup_files.py 
# setup_files.py
import os

# Create directories
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

# Create login.html
login_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - General Shop POS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }
        .login-card {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            width: 100%;
            max-width: 400px;
        }
        .login-card h2 {
            color: #333;
            margin-bottom: 30px;
            text-align: center;
        }
        .btn-login {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            width: 100%;
            padding: 12px;
            color: white;
            font-weight: bold;
        }
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h2><i class="fas fa-store"></i> General Shop POS</h2>
        <form id="loginForm">
            <div class="mb-3">
                <label class="form-label"><i class="fas fa-user"></i> Username</label>
                <input type="text" class="form-control" id="username" required autocomplete="off">
            </div>
            <div class="mb-3">
                <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                <input type="password" class="form-control" id="password" required>
            </div>
            <button type="submit" class="btn btn-login">
                <i class="fas fa-sign-in-alt"></i> Login
            </button>
        </form>
        <div class="mt-3 text-center text-muted">
            <small>Demo: admin/admin123 | cashier/cashier123</small>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script>
        $('#loginForm').on('submit', function(e) {
            e.preventDefault();
            $.ajax({
                url: '/login',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    username: $('#username').val(),
                    password: $('#password').val()
                }),
                success: function(response) {
                    if (response.success) {
                        if (response.role === 'admin') {
                            window.location.href = '/admin';
                        } else {
                            window.location.href = '/pos';
                        }
                    }
                },
                error: function() {
                    alert('Invalid credentials');
                }
            });
        });
    </script>
</body>
</html>'''

# Create index.html (simplified version)
index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POS - General Shop</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #f5f6fa; font-family: 'Segoe UI', sans-serif; }
        .top-bar { background: white; border-bottom: 1px solid #ddd; position: sticky; top: 0; z-index: 1000; }
        .category-card { background: white; border-radius: 30px; padding: 10px 20px; cursor: pointer; transition: 0.3s; box-shadow: 0 2px 5px rgba(0,0,0,0.1); display: inline-block; margin: 5px; }
        .category-card.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
        .products-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
        .product-card { background: white; border-radius: 15px; cursor: pointer; transition: 0.3s; box-shadow: 0 5px 15px rgba(0,0,0,0.1); overflow: hidden; }
        .product-card:hover { transform: translateY(-5px); }
        .product-image { width: 100%; height: 150px; object-fit: cover; background: #f0f0f0; }
        .product-info { padding: 15px; }
        .cart-sidebar { background: #f8f9fa; height: calc(100vh - 70px); position: sticky; top: 70px; overflow-y: auto; }
        .cart-item { background: white; border-radius: 10px; padding: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        .cart-item-controls button { width: 30px; height: 30px; border-radius: 50%; border: none; background: #667eea; color: white; }
        @media (max-width: 768px) { .cart-sidebar { height: auto; position: relative; } }
    </style>
</head>
<body>
    <div class="container-fluid p-0">
        <div class="top-bar p-3">
            <div class="row align-items-center">
                <div class="col-md-3">
                    <button class="btn btn-primary" id="openRegisterBtn" style="display:none"><i class="fas fa-cash-register"></i> Open Register</button>
                    <span id="registerStatus" class="badge bg-danger">Register: Closed</span>
                </div>
                <div class="col-md-4">
                    <input type="text" class="form-control" id="searchInput" placeholder="Search products...">
                </div>
                <div class="col-md-5 text-end">
                    <span id="datetime" class="me-3"></span>
                    <button class="btn btn-sm btn-danger" onclick="logout()">Logout</button>
                </div>
            </div>
        </div>
        <div class="row g-0">
            <div class="col-md-7 p-3">
                <div id="categoriesList" class="mb-3"></div>
                <div id="productsGrid" class="products-grid"></div>
            </div>
            <div class="col-md-5 cart-sidebar p-3">
                <h4>Shopping Cart</h4>
                <div id="cartItems"></div>
                <hr>
                <div class="d-flex justify-content-between"><span>Subtotal:</span><span id="subtotal">Ksh 0</span></div>
                <div class="d-flex justify-content-between"><span>VAT (16%):</span><span id="tax">Ksh 0</span></div>
                <div class="d-flex justify-content-between fw-bold"><span>Total:</span><span id="total">Ksh 0</span></div>
                <button class="btn btn-success w-100 mt-3" id="payCashBtn">Pay Cash</button>
                <button class="btn btn-primary w-100 mt-2" id="payMpesaBtn">Pay M-Pesa</button>
                <button class="btn btn-danger w-100 mt-2" id="cancelSaleBtn">Cancel</button>
            </div>
        </div>
    </div>

    <!-- M-Pesa Modal -->
    <div class="modal fade" id="mpesaModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5>M-Pesa Payment</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
                <div class="modal-body">
                    <input type="tel" class="form-control mb-2" id="mpesaPhone" placeholder="2547XXXXXXXX">
                    <input type="number" class="form-control" id="mpesaAmount" readonly>
                    <div id="mpesaStatus" class="alert alert-info mt-2">Enter phone number</div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" id="confirmMpesaBtn">Send STK Push</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Register Modal -->
    <div class="modal fade" id="registerModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5>Open Register</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
                <div class="modal-body">
                    <input type="number" class="form-control" id="openingBalance" value="0" placeholder="Opening balance">
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" id="confirmOpenRegisterBtn">Open</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let cart = [], currentCategory = null, registerOpen = false;
        
        function updateDateTime() { $('#datetime').text(new Date().toLocaleString()); }
        setInterval(updateDateTime, 1000); updateDateTime();
        
        function checkRegisterStatus() {
            $.get('/api/register/status', function(data) {
                registerOpen = data.is_open;
                if (registerOpen) {
                    $('#registerStatus').text('Register: Open').removeClass('bg-danger').addClass('bg-success');
                    $('#openRegisterBtn').hide();
                } else {
                    $('#registerStatus').text('Register: Closed').removeClass('bg-success').addClass('bg-danger');
                    $('#openRegisterBtn').show();
                }
            });
        }
        
        $('#openRegisterBtn').click(() => $('#registerModal').modal('show'));
        $('#confirmOpenRegisterBtn').click(() => {
            $.post('/api/register/open', JSON.stringify({opening_balance: parseFloat($('#openingBalance').val())}), 
                () => { $('#registerModal').modal('hide'); checkRegisterStatus(); alert('Register opened!'); })
                .fail(() => alert('Failed'));
        });
        
        function loadCategories() {
            $.get('/api/categories', function(cats) {
                let html = '<div class="category-card" data-category="">All</div>';
                cats.forEach(c => html += `<div class="category-card" data-category="${c.name}" style="background:${c.color}20">${c.icon} ${c.name}</div>`);
                $('#categoriesList').html(html);
            });
        }
        
        function loadProducts() {
            let url = '/api/products';
            if (currentCategory) url += `?category=${currentCategory}`;
            let search = $('#searchInput').val();
            if (search) url += `${currentCategory?'&':'?'}search=${search}`;
            $.get(url, function(prods) {
                let html = '';
                prods.forEach(p => {
                    html += `<div class="product-card" data-id="${p.id}" data-name="${p.name}" data-price="${p.selling_price}" data-stock="${p.stock_quantity}">
                        <div class="product-info"><strong>${p.name}</strong><br>Ksh ${p.selling_price}<br><small>Stock: ${p.stock_quantity}</small></div>
                    </div>`;
                });
                $('#productsGrid').html(html);
            });
        }
        
        $(document).on('click', '.product-card', function() {
            if (!registerOpen) { alert('Open register first!'); return; }
            let id = $(this).data('id'), name = $(this).data('name'), price = $(this).data('price'), stock = $(this).data('stock');
            let item = cart.find(i => i.id === id);
            if (item) { if (item.qty < stock) item.qty++; else alert('Out of stock'); }
            else cart.push({id, name, price, qty: 1, stock});
            updateCart();
        });
        
        function updateCart() {
            let subtotal = 0, html = '';
            cart.forEach((item, i) => {
                let total = item.price * item.qty;
                subtotal += total;
                html += `<div class="cart-item"><div><strong>${item.name}</strong><br>Ksh ${item.price}</div>
                    <div><button class="dec" data-i="${i}">-</button> ${item.qty} <button class="inc" data-i="${i}">+</button><br>Ksh ${total}</div></div>`;
            });
            $('#cartItems').html(html || '<p class="text-muted">Cart empty</p>');
            let tax = subtotal * 0.16, total = subtotal + tax;
            $('#subtotal').text(`Ksh ${subtotal}`);
            $('#tax').text(`Ksh ${tax}`);
            $('#total').text(`Ksh ${total}`);
        }
        
        $(document).on('click', '.inc', function() { let i = $(this).data('i'); if (cart[i].qty < cart[i].stock) cart[i].qty++; updateCart(); });
        $(document).on('click', '.dec', function() { let i = $(this).data('i'); if (cart[i].qty > 1) cart[i].qty--; else cart.splice(i,1); updateCart(); });
        
        $('#cancelSaleBtn').click(() => { if(confirm('Cancel?')) { cart = []; updateCart(); } });
        
        function processPayment(method, mpesaId) {
            if(cart.length === 0) { alert('Cart empty'); return; }
            $.post('/api/sale', JSON.stringify({items: cart.map(i => ({id:i.id, name:i.name, price:i.price, quantity:i.qty})), payment_method: method, mpesa_transaction_id: mpesaId}))
                .done(function(res) {
                    alert(`Sale complete!\nOrder: ${res.order_number}`);
                    cart = []; updateCart(); loadProducts();
                    $.post('/api/print/receipt', JSON.stringify({receipt_data: res.receipt_data})).done(html => { let w = window.open('', '_blank'); w.document.write(html); w.document.close(); });
                }).fail(err => alert(err.responseJSON?.error || 'Sale failed'));
        }
        
        $('#payCashBtn').click(() => processPayment('cash'));
        $('#payMpesaBtn').click(() => {
            if(cart.length === 0) { alert('Cart empty'); return; }
            $('#mpesaAmount').val(parseFloat($('#total').text().replace('Ksh','')));
            $('#mpesaModal').modal('show');
        });
        
        $('#confirmMpesaBtn').click(() => {
            let phone = $('#mpesaPhone').val();
            if(!phone.match(/^254[17][0-9]{8}$/)) { alert('Valid M-Pesa number required (2547XXXXXXXX)'); return; }
            $('#mpesaStatus').html('<i class="fas fa-spinner fa-spin"></i> Processing...');
            $.post('/api/mpesa/pay', JSON.stringify({phone_number: phone, amount: parseFloat($('#mpesaAmount').val())}))
                .done(res => {
                    let interval = setInterval(() => {
                        $.get(`/api/mpesa/status/${res.checkout_request_id}`, status => {
                            if(status.status === 'completed') { clearInterval(interval); $('#mpesaModal').modal('hide'); processPayment('mpesa', res.checkout_request_id); }
                            else if(status.status === 'failed') { clearInterval(interval); $('#mpesaStatus').html('Payment failed'); }
                        });
                    }, 3000);
                    $('#mpesaStatus').html('Check your phone and enter PIN...');
                    setTimeout(() => { clearInterval(interval); $('#mpesaStatus').html('Timeout'); }, 60000);
                }).fail(() => $('#mpesaStatus').html('Failed'));
        });
        
        $(document).on('click', '.category-card', function() { $('.category-card').removeClass('active'); $(this).addClass('active'); currentCategory = $(this).data('category'); loadProducts(); });
        $('#searchInput').on('keypress', e => { if(e.key === 'Enter') loadProducts(); });
        
        function logout() { window.location.href = '/logout'; }
        
        checkRegisterStatus(); loadCategories(); loadProducts(); setInterval(checkRegisterStatus, 30000);
    </script>
</body>
</html>'''

# Create admin.html (simplified)
admin_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">Admin Dashboard</a>
            <button class="btn btn-danger" onclick="logout()">Logout</button>
        </div>
    </nav>
    <div class="container mt-3">
        <div class="row" id="stats"></div>
        <div class="card mt-3">
            <div class="card-header">M-Pesa Transactions</div>
            <div class="card-body">
                <button class="btn btn-sm btn-primary" id="exportCSV">Export CSV</button>
                <table class="table table-bordered mt-2">
                    <thead><tr><th>Receipt</th><th>Phone</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead>
                    <tbody id="transactions"></tbody>
                </table>
            </div>
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script>
        function loadStats() {
            $.get('/api/dashboard/stats', d => {
                $('#stats').html(`
                    <div class="col-md-3"><div class="card bg-primary text-white p-3">Today: Ksh ${d.today_sales.amount}</div></div>
                    <div class="col-md-3"><div class="card bg-success text-white p-3">Weekly: Ksh ${d.weekly_sales.amount}</div></div>
                    <div class="col-md-3"><div class="card bg-info text-white p-3">Monthly: Ksh ${d.monthly_sales.amount}</div></div>
                    <div class="col-md-3"><div class="card bg-warning p-3">Products: ${d.total_products}</div></div>
                `);
            });
        }
        function loadTransactions() {
            $.get('/api/mpesa/transactions', t => {
                $('#transactions').html(t.map(tx => `<tr><td>${tx.receipt_number}</td><td>${tx.phone_number}</td><td>${tx.amount}</td><td>${tx.status}</td><td>${new Date(tx.date).toLocaleString()}</td></tr>`).join(''));
            });
        }
        $('#exportCSV').click(() => window.location.href = '/api/export/mpesa/csv');
        function logout() { window.location.href = '/logout'; }
        loadStats(); loadTransactions(); setInterval(loadStats, 30000);
    </script>
</body>
</html>'''

# Write files
with open('templates/login.html', 'w', encoding='utf-8') as f:
    f.write(login_html)
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(index_html)
with open('templates/admin.html', 'w', encoding='utf-8') as f:
    f.write(admin_html)

print("All template files created successfully!")
print("Now run: python app.py")