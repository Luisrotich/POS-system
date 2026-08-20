from app import app

with app.test_client() as c:
    resp = c.post('/login', json={'username':'admin', 'password':'admin123'})
    print('Login:', resp.status_code, resp.get_json())
    resp2 = c.get('/api/mpesa/transactions')
    print('Transactions:', resp2.status_code)
    try:
        print(resp2.get_json())
    except Exception as e:
        print('No JSON:', e)
