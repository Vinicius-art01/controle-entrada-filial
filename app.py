from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
import json, os, re
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

# --- Configuração do Flask ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

# --- Carrega usuários do arquivo JSON ---
USERS = {}
with open(os.path.join(os.path.dirname(__file__), 'users.json'), encoding='utf-8') as f:
    lista = json.load(f)
    for u in lista:
        # Armazenamos senha sempre hasheada em memória
        hashed = generate_password_hash(u['senha'])
        USERS[u['matricula']] = {
            'senha': hashed,
            'nome': u['nome']
        }

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, matricula, nome):
        self.id = matricula
        self.nome = nome

@login_manager.user_loader
def load_user(user_id):
    if user_id in USERS:
        return User(user_id, USERS[user_id]['nome'])
    return None

# --- Validação da placa (mesma de sempre) ---
def validar_placa(placa):
    placa = placa.upper()
    padrao = r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'
    return re.match(padrao, placa)

# --- Inicialização do Firebase Firestore ---
if not firebase_admin._apps:
    if os.getenv('RENDER'):
        cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
    else:
        cred_path = os.path.join(os.path.dirname(__file__),
                                 'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json')
        cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- Filiais e filas em memória ---
FILIAIS = ['RIO', 'SALVADOR', 'AVENIDA', 'DUTRA', 'SEDE', 'ITABUNA']
fila = {filial: [] for filial in FILIAIS}

# --- Rotas de Autenticação (sem registro) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        matricula = request.form.get('matricula')
        senha = request.form.get('senha')
        user = USERS.get(matricula)
        if user and check_password_hash(user['senha'], senha):
            login_user(User(matricula, user['nome']))
            flash(f'Bem-vindo, {user["nome"]}!', 'success')
            return redirect(url_for('home'))
        flash('Matrícula ou senha incorretos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# --- Home com links de filial ---
@app.route('/')
@login_required
def home():
    return render_template('home.html', filiais=FILIAIS)

# --- Gerenciar fila por filial, registra também current_user.nome ---
@app.route('/filial/<filial>', methods=['GET', 'POST'])
@login_required
def filial_view(filial):
    if filial not in FILIAIS:
        flash('Filial não existente.', 'warning')
        return redirect(url_for('home'))

    if request.method == 'POST':
        placa = request.form['placa'].strip().upper()
        solicitacao = request.form['solicitacao'].strip()

        if not validar_placa(placa):
            flash('Placa inválida! Ex: ABC1D23 ou ABC1234.', 'danger')
            return redirect(url_for('filial_view', filial=filial))

        if placa in [v['placa'] for v in fila[filial]]:
            flash('Placa já em fila.', 'warning')
            return redirect(url_for('filial_view', filial=filial))

        if not solicitacao:
            flash('Solicitação não pode ficar vazia.', 'danger')
            return redirect(url_for('filial_view', filial=filial))

        ordem = len(fila[filial]) + 1
        hora = datetime.now().strftime('%H:%M:%S')
        registro = {
            'ordem': ordem,
            'placa': placa,
            'solicitacao': solicitacao,
            'hora': hora,
            'usuario': current_user.nome   # armazena o nome do funcionário
        }
        fila[filial].append(registro)
        flash(f'Veículo {placa} adicionado por {current_user.nome}.', 'success')
        return redirect(url_for('filial_view', filial=filial))

    return render_template('filial.html', filial=filial, fila=fila[filial])

@app.route('/filial/<filial>/liberar/<int:ordem>', methods=['POST'])
@login_required
def liberar(filial, ordem):
    registro = next((v for v in fila[filial] if v['ordem'] == ordem), None)
    if registro:
        fila[filial] = [v for v in fila[filial] if v['ordem'] != ordem]
        # reordena
        for idx, v in enumerate(fila[filial], start=1):
            v['ordem'] = idx
        # grava histórico com filial e usuário
        db.collection('historico').add({
            **registro,
            'filial': filial,
            'liberado_em': datetime.now()
        })
        flash(f'Veículo {registro["placa"]} liberado.', 'info')
    return redirect(url_for('filial_view', filial=filial))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
