from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os, json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- Configuração do Flask ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')  # usado para sessions e flashes

# --- Banco de usuários (SQLite) ---
DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
init_db()

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id_, username, password):
        self.id = str(id_)
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, password FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return User(*row)
    return None

# --- Rotas de registro e login ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed = generate_password_hash(password)
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))
            conn.commit()
            conn.close()
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Usuário já existe.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, password FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        conn.close()
        if row and check_password_hash(row[1], password):
            user = User(row[0], username, row[1])
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('home'))
        flash('Usuário ou senha incorretos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# --- Inicialização do Firebase Firestore ---
if not firebase_admin._apps:
    if os.getenv('RENDER'):
        firebase_json = os.getenv('FIREBASE_CREDENTIALS')
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
    else:
        caminho = os.path.join(
            os.path.dirname(__file__),
            'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json'
        )
        cred = credentials.Certificate(caminho)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Definição de filiais e filas em memória ---
FILIAIS = ['RIO', 'SALVADOR', 'AVENIDA', 'DUTRA', 'SEDE', 'ITABUNA']
fila = {filial: [] for filial in FILIAIS}

# --- Página Inicial com links para cada filial ---
@app.route('/')
@login_required
def home():
    return render_template('home.html', filiais=FILIAIS)

# --- Exibir e gerenciar fila por filial ---
@app.route('/filial/<filial>', methods=['GET', 'POST'])
@login_required
def filial_view(filial):
    if filial not in FILIAIS:
        flash('Filial não encontrada.', 'warning')
        return redirect(url_for('home'))
    if request.method == 'POST':
        placa = request.form['placa']
        solicitacao = request.form['solicitacao']
        ordem = len(fila[filial]) + 1
        hora = datetime.now().strftime('%H:%M:%S')
        registro = {'ordem': ordem, 'placa': placa, 'solicitacao': solicitacao, 'hora': hora}
        fila[filial].append(registro)
        flash(f'Veículo {placa} adicionado à fila.', 'success')
        return redirect(url_for('filial_view', filial=filial))
    return render_template('filial.html', filial=filial, fila=fila[filial])

@app.route('/filial/<filial>/liberar/<int:ordem>', methods=['POST'])
@login_required
def liberar(filial, ordem):
    registro = next((v for v in fila[filial] if v['ordem'] == ordem), None)
    if registro:
        fila[filial] = [v for v in fila[filial] if v['ordem'] != ordem]
        db.collection('historico').add({**registro, 'filial': filial, 'liberado_em': datetime.now()})
        flash(f'Veículo {registro["placa"]} liberado.', 'info')
    return redirect(url_for('filial_view', filial=filial))

# --- Execução ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
