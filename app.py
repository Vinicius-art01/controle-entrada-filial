import os
import json
import re
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

import firebase_admin
from firebase_admin import credentials, firestore

# ——— Configuração do Flask ——————————————————————————————————————————————————
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

# ——— Carrega usuários de JSON ——————————————————————————————————————————————
def carregar_usuarios():
    # Primeira tenta a variável de ambiente, depois o arquivo padrão
    caminho = os.getenv("USERS_FILE_PATH", os.path.join(os.path.dirname(__file__), "users.json"))
    print(f"Carregando usuários de: {caminho}")  # <-- AQUI
    try:
        with open(caminho, encoding='utf-8') as f:
            dados = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Arquivo de usuários não encontrado em: {caminho}")
    # Monta dicionário {matricula: {senha_hash, nome}}
    usuarios = {}
    for u in dados:
        usuarios[u['matricula']] = {
            'senha_hash': generate_password_hash(u['senha']),
            'nome':        u['nome']
        }
    return usuarios

USERS = carregar_usuarios()

# ——— Configuração do Flask‑Login ————————————————————————————————————————
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, matricula, nome):
        self.id   = matricula
        self.nome = nome

@login_manager.user_loader
def load_user(user_id):
    u = USERS.get(user_id)
    return User(user_id, u['nome']) if u else None

# ——— Validação de placa ——————————————————————————————————————————————————
def validar_placa(placa: str) -> bool:
    placa = placa.upper()
    padrao = r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'
    return bool(re.match(padrao, placa))

# ——— Inicializa Firebase Firestore —————————————————————————————————————
if not firebase_admin._apps:
    if os.getenv('RENDER'):
        cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
    else:
        key_file = os.path.join(
            os.path.dirname(__file__),
            'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json'
        )
        cred = credentials.Certificate(key_file)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ——— Filiais e filas em memória ————————————————————————————————————————
FILIAIS = ['RIO', 'SALVADOR', 'AVENIDA', 'DUTRA', 'SEDE', 'ITABUNA']
fila = {filial: [] for filial in FILIAIS}

# ——— Rotas de Autenticação ——————————————————————————————————————————————
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        mat = request.form.get('matricula', '').strip()
        pwd = request.form.get('senha', '')
        u   = USERS.get(mat)
        if u and check_password_hash(u['senha_hash'], pwd):
            login_user(User(mat, u['nome']))
            flash(f'Bem‑vindo, {u["nome"]}!', 'success')
            return redirect(url_for('home'))
        flash('Matrícula ou senha incorretos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# ——— Home e seleção de filial ————————————————————————————————————————————
@app.route('/')
@login_required
def home():
    return render_template('home.html', filiais=FILIAIS)

# ——— Visualização e registro na fila por filial ———————————————————————————
@app.route('/filial/<filial>', methods=['GET','POST'])
@login_required
def filial_view(filial):
    if filial not in FILIAIS:
        flash('Filial inválida.', 'warning')
        return redirect(url_for('home'))

    if request.method == 'POST':
        placa      = request.form['placa'].strip().upper()
        solicitacao = request.form['solicitacao'].strip()

        # Validações
        if not validar_placa(placa):
            flash('Placa inválida! Use ABC1234 ou ABC1D23.', 'danger')
        elif placa in [v['placa'] for v in fila[filial]]:
            flash('Esta placa já está na fila.', 'warning')
        elif not solicitacao:
            flash('Solicitação não pode ficar vazia.', 'danger')
        else:
            ordem = len(fila[filial]) + 1
            hora  = datetime.now().strftime('%H:%M:%S')
            registro = {
                'ordem':      ordem,
                'placa':      placa,
                'solicitacao': solicitacao,
                'hora':       hora,
                'usuario':    current_user.nome
            }
            fila[filial].append(registro)
            flash(f'Veículo {placa} adicionado por {current_user.nome}.', 'success')
        return redirect(url_for('filial_view', filial=filial))

    return render_template('filial.html', filial=filial, fila=fila[filial])

# ——— Liberar veículo e gravar histórico ————————————————————————————————————
@app.route('/filial/<filial>/liberar/<int:ordem>', methods=['POST'])
@login_required
def liberar(filial, ordem):
    reg = next((v for v in fila[filial] if v['ordem']==ordem), None)
    if reg:
        fila[filial] = [v for v in fila[filial] if v['ordem']!=ordem]
        # reordena
        for idx, v in enumerate(fila[filial], start=1):
            v['ordem'] = idx
        db.collection('historico').add({
            **reg,
            'filial':      filial,
            'liberado_em': datetime.now()
        })
        flash(f'Veículo {reg["placa"]} liberado.', 'info')
    return redirect(url_for('filial_view', filial=filial))

# ——— Execução —————————————————————————————————————————————————————————
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
