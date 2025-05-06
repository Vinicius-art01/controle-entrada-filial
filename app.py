from flask import Flask, render_template, request, redirect, url_for
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import json

app = Flask(__name__)

# --- Inicialização do Firebase (igual você já configurou) ---
if not firebase_admin._apps:
    # Se estiver no Render, use a variável de ambiente; senão, o JSON local
    if os.getenv('RENDER'):
        firebase_json = os.getenv('FIREBASE_CREDENTIALS')
        cred_dict    = json.loads(firebase_json)
        cred         = credentials.Certificate(cred_dict)
    else:
        caminho_arquivo = os.path.join(
            os.path.dirname(__file__),
            'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json'
        )
        cred = credentials.Certificate(caminho_arquivo)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Definição de filiais e filas em memória ---
FILIAIS = ['RIO', 'SALVADOR', 'AVENIDA', 'DUTRA', 'SEDE', 'ITABUNA']
fila = {filial: [] for filial in FILIAIS}

# --- Rota principal: renderiza o template index.html ---
@app.route('/')
def index():
    filial = request.args.get('filial', FILIAIS[0])
    lista  = fila.get(filial, [])
    return render_template('index.html',
                           filiais=FILIAIS,
                           filial=filial,
                           fila=lista)

# --- Registrar novo veículo ---
@app.route('/registrar', methods=['POST'])
def registrar():
    placa      = request.form['placa']
    solicitacao= request.form['solicitacao']
    filial     = request.form['filial']
    ordem      = len(fila[filial]) + 1
    hora       = datetime.now().strftime('%H:%M:%S')

    registro = {
        'ordem': ordem,
        'placa': placa,
        'solicitacao': solicitacao,
        'hora': hora
    }
    fila[filial].append(registro)
    return redirect(url_for('index', filial=filial))

# --- Liberar veículo e gravar no Firestore ---
@app.route('/liberar/<filial>/<int:ordem>', methods=['POST'])
def liberar(filial, ordem):
    veiculo = next((v for v in fila[filial] if v['ordem']==ordem), None)
    if veiculo:
        fila[filial] = [v for v in fila[filial] if v['ordem']!=ordem]
        db.collection('historico').add({
            **veiculo,
            'filial': filial,
            'liberado_em': datetime.now()
        })
    return redirect(url_for('index', filial=filial))

# --- Entry point para local e Render ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
