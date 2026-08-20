import requests

BASE = 'http://127.0.0.1:5000'
S = requests.Session()

# login as admin
r = S.post(BASE + '/login', json={'username':'admin','password':'admin123'})
print('Login status:', r.status_code, r.text)

# fetch transactions
r = S.get(BASE + '/api/mpesa/transactions')
print('\nTransactions endpoint status:', r.status_code)
try:
    print(r.json())
except Exception as e:
    print('Error parsing JSON:', e, r.text)
