from flask import Flask, render_template, request, redirect, url_for
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)

# 1) Inicializa o Firebase Firestore
caminho_arquivo = os.path.join(
    os.path.dirname(__file__),
    'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json'
)
cred = credentials.Certificate(caminho_arquivo)
firebase_admin.initialize_app(cred)
db = firestore.client()

# 2) Defina suas filiais
FILIAIS = ['RIO', 'SALVADOR', 'AVENIDA', 'DUTRA', 'SEDE', 'ITABUNA']
# 3) Fila em memória por filial
fila = {filial: [] for filial in FILIAIS}

@app.route('/')
def index():
    # 4) Captura a filial selecionada na query string (padrão: RIO)
    filial = request.args.get('filial', FILIAIS[0])
    # 5) Lista de veículos dessa filial
    lista = fila.get(filial, [])
    return render_template('index.html', filiais=FILIAIS, filial=filial, fila=lista)

@app.route('/registrar', methods=['POST'])
def registrar():
    placa = request.form.get('placa')
    solicitacao = request.form.get('solicitacao')
    filial = request.form.get('filial')
    # Ordem automática
    ordem = len(fila[filial]) + 1
    hora = datetime.now().strftime('%H:%M:%S')

    registro = {
        'ordem': ordem,
        'placa': placa,
        'solicitacao': solicitacao,
        'hora': hora
    }
    # 6) Adiciona à fila da filial correta
    fila[filial].append(registro)
    return redirect(url_for('index', filial=filial))

@app.route('/liberar/<filial>/<int:ordem>', methods=['GET', 'POST'])
def liberar(filial, ordem):
    # 7) Remove o veículo da fila em memória
    veiculo = next((v for v in fila[filial] if v['ordem'] == ordem), None)
    if veiculo:
        fila[filial] = [v for v in fila[filial] if v['ordem'] != ordem]
        # 8) Salva no Firestore com informação da filial
        db.collection('historico').add({
            **veiculo,
            'filial': filial,
            'liberado_em': datetime.now()
        })
    return redirect(url_for('index', filial=filial))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')