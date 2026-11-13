from flask import Flask, request, render_template_string
import sqlite3
import os

app = Flask(__name__)
PRODUCTS_DB_PATH = os.environ.get('PRODUCTS_DB_PATH', '/tmp/products.db')

def init_db():
    conn = sqlite3.connect(PRODUCTS_DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, price REAL, hidden INTEGER DEFAULT 0)''')
    
    c.execute("SELECT COUNT(*) FROM products")
    count = c.fetchone()[0]
    
    if count == 0:
        products = [
            ('Laptop', 4999.99, 0),
            ('Smartfon', 2999.99, 0),
            ('Sluchawki', 199.99, 0),
            ('Klawiatura', 149.99, 0),
            ('Mysz', 89.99, 0),
            ('Monitor', 1299.99, 0),
            ('CTF{sql_injection_master}', 9999.99, 1)
        ]
        c.executemany('INSERT INTO products (name, price, hidden) VALUES (?, ?, ?)', products)
        conn.commit()
        print("Dodano produkty do bazy")
    else:
        print(f"Baza juz zawiera {count} produktow")
    
    conn.close()

init_db()


@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>CyberShop</title>
        <style>
            body { font-family: Arial; background: #0a0e27; color: white; padding: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            input { padding: 10px; width: 300px; background: #222; color: white; border: 1px solid #444; border-radius: 8px; }
            button { padding: 10px 20px; background: #4091bf; color: white; border: none; border-radius: 8px; cursor: pointer; }
            .product { background: rgba(255,255,255,0.05); padding: 10px; margin: 10px 0; border-radius: 8px; }
            .flag { color: #00ff88; font-weight: bold; }
            .search-form { margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>CyberShop</h1>
            <p>Znajdz swoj wymarzony produkt!</p>
            
            <form method="GET" action="/search" class="search-form">
                <input type="text" name="q" placeholder="Szukaj produktu...">
                <button type="submit">Szukaj</button>
            </form>
            
            <p style="color: #666; font-size: 0.8em;">Wskazowka: Pole wyszukiwania jest podatne na SQL Injection.</p>
            
            <div id="results">
            </div>
        </div>
    </body>
    </html>
    ''')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    conn = sqlite3.connect(PRODUCTS_DB_PATH)
    c = conn.cursor()
    
    sql = f"SELECT name, price FROM products WHERE name LIKE '%{query}%' AND hidden = 0"
    
    try:
        results = c.execute(sql).fetchall()
        conn.close()
        
        if results:
            html = '<h3>Wyniki wyszukiwania:</h3>'
            for name, price in results:
                html += f'<div class="product"> {name} - {price} PLN</div>'
            return html
        else:
            return '<p style="color: #aaa;">Brak produktow spelniajacych kryteria.</p>'
    except Exception as e:
        return f'<p style="color: #ff6666;">Blad zapytania: {e}</p>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7000, debug=False)