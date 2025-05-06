from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

app = Flask(__name__)

# Inicializar Firebase com variável de ambiente no Render
if not firebase_admin._apps:
    if os.getenv('RENDER'):
        # Pegando o JSON da variável de ambiente e salvando temporariamente
        firebase_json = os.getenv('FIREBASE_CREDENTIALS')
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # Local: usando o arquivo .json
        caminho_arquivo = os.path.join(os.path.dirname(__file__), 'controle-de-veiculos-ba52c-firebase-adminsdk-fbsvc-05f4208746.json')
        cred = credentials.Certificate(caminho_arquivo)

    firebase_admin.initialize_app(cred)

# Instanciando o Firestore
db = firestore.client()

@app.route('/')
def home():
    return 'API de Controle de Entrada está online! 🚗✅'

@app.route('/adicionar', methods=['POST'])
def adicionar_entrada():
    dados = request.json
    db.collection('entradas').add(dados)
    return jsonify({"mensagem": "Entrada adicionada com sucesso!"})

@app.route('/listar', methods=['GET'])
def listar_entradas():
    docs = db.collection('entradas').stream()
    entradas = []
    for doc in docs:
        entradas.append(doc.to_dict())
    return jsonify(entradas)

# Para rodar local e no Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
