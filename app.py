from flask import Flask, render_template, request, redirect, make_response, url_for, jsonify, send_from_directory, session
from flask import Flask, Response, abort, redirect, render_template, url_for
import sqlite3
import os
import zipfile
import cv2
import shutil
import requests
from werkzeug.utils import secure_filename
import importador
import threading
import random
import telegram
from telegram import Bot
import asyncio
import yt_dlp
import re

app = Flask(__name__)
app.secret_key = 'pobreflix_chave_secreta_super_segura'
app.config['UPLOAD_FOLDER'] = 'static/videos' 
app.config['THUMBNAIL_FOLDER'] = 'static/capas'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

TELEGRAM_BOT_TOKEN = "7905838078:AAHLkRxtsTWA9gGdS2osdd8m7Md1e_JxWOQ"

TELEGRAM_CHANNEL_ID = "-1004411648715"

def usando_postgres():
    return bool(os.environ.get('DATABASE_URL') and os.environ.get('DATABASE_URL').startswith("postgres"))

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres"):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(db_url)
    else:
        conn = sqlite3.connect('zdatabase.db')
        conn.row_factory = sqlite3.Row
        return conn

def executar_query(cursor, query, params=()):
    """Converte automaticamente %s para ? se estiver usando SQLite"""
    if not usando_postgres():
        query = query.replace('%s', '?')
    cursor.execute(query, params)

def criar_cursor(conn):
    if usando_postgres():
        from psycopg2.extras import RealDictCursor
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        return conn.cursor()

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            conta_id INTEGER,
            FOREIGN KEY (conta_id) REFERENCES contas(id),
            UNIQUE(nome, conta_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT,
            arquivo TEXT,
            capa TEXT,
            classificacao TEXT,
            conta_id INTEGER,
            usuario_id INTEGER,
            eh_video_unico INTEGER DEFAULT 0,
            primeiro_video TEXT,
            FOREIGN KEY (conta_id) REFERENCES contas(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feed_publico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            url_video TEXT NOT NULL,
            capa_url TEXT,
            autor_id INTEGER, 
            nome_autor TEXT,  
            denuncias INTEGER DEFAULT 0,
            visualizacoes INTEGER DEFAULT 0,
            data_postagem TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (autor_id) REFERENCES contas(id)
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

@app.before_request
def verificar_banco():
    init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        conn = get_db_connection()
        cursor = criar_cursor(conn)
        
        executar_query(cursor, 'SELECT id, email FROM contas WHERE email = %s AND senha = %s', (email, senha))
        conta = cursor.fetchone()
        
        conn.close()
        
        if conta:
            session['conta_id'] = conta['id'] if not usando_postgres() else conta['id']
            session['conta_email'] = email
            return redirect(url_for('gerenciar_perfis'))
        else:
            return render_template('login.html', erro="E-mail ou senha incorretos.")
            
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            executar_query(cursor, 'INSERT INTO contas (email, senha) VALUES (%s, %s)', (email, senha))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return render_template('cadastro.html', erro="Este e-mail já está cadastrado ou ocorreu um erro.")
            
    return render_template('cadastro.html')

@app.route('/logout_conta')
def logout_conta():
    session.clear() 
    return redirect(url_for('login'))

@app.route('/perfis')
def gerenciar_perfis():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT id, nome, conta_id FROM usuarios WHERE conta_id = %s', (session['conta_id'],))
    perfis = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('perfis.html', perfis=perfis)

@app.route('/criar_perfil', methods=['POST'])
def criar_perfil():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    nome = request.form.get('nome')
    if nome:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            executar_query(cursor, 'INSERT INTO usuarios (nome, conta_id) VALUES (%s, %s)', (nome, session['conta_id']))
            conn.commit()
        except Exception:
            pass
        finally:
            cursor.close()
            conn.close()
            
    return redirect(url_for('gerenciar_perfis'))

@app.route('/selecionar_perfil/<int:id>')
def selecionar_perfil(id):
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT nome FROM usuarios WHERE id = %s AND conta_id = %s', (id, session.get('conta_id')))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        session['usuario_logado'] = user['nome'] if not usando_postgres() else user[0] 
    return redirect('/')

@app.route('/sair_perfil')
def sair_perfil():
    session.pop('usuario_logado', None) 
    return redirect(url_for('gerenciar_perfis'))

@app.route('/')
def index():
    if 'conta_id' not in session or 'usuario_logado' not in session: 
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT id FROM usuarios WHERE nome = %s AND conta_id = %s', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        cursor.close(); conn.close()
        return redirect(url_for('gerenciar_perfis'))
        
    usuario_id = perfil_atual['id'] if not usando_postgres() else perfil_atual['id']
    executar_query(cursor, 'SELECT * FROM series WHERE usuario_id = %s', (usuario_id,))
    series_cruas = cursor.fetchall()
    cursor.close(); conn.close()

    lista_processada = []
    for s in series_cruas:
        item = dict(s)
        if not item.get('capa') or item['capa'] == 'None': 
            item['capa'] = 'default.jpg'
        
        caminho_pasta = os.path.join(app.config['UPLOAD_FOLDER'], item['arquivo'])
        if os.path.isdir(caminho_pasta):
            arquivos = sorted([f for f in os.listdir(caminho_pasta) if f.lower().endswith(('.mp4', '.mkv', '.webm'))])
            if arquivos:
                item['eh_video_unico'] = (item.get('eh_video_unico') == 1) or (len(arquivos) == 1)
                item['primeiro_video'] = arquivos[0]
            else:
                item['eh_video_unico'] = False
                item['primeiro_video'] = None
        else:
            item['eh_video_unico'] = True
            item['primeiro_video'] = item['arquivo']
        
        lista_processada.append(item)

    return render_template('index.html', series=lista_processada)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    if 'conta_id' not in session or 'usuario_logado' not in session:
        return redirect(url_for('login'))

    nome = request.form.get('nome')
    descricao = request.form.get('descricao')
    arquivo = request.files.get('arquivo')

    if not nome or not arquivo or arquivo.filename == '':
        return "Nome e arquivo de vídeo/zip válido são obrigatórios", 400

    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT id FROM usuarios WHERE nome = %s AND conta_id = %s', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        cursor.close()
        conn.close()
        return "Perfil inválido ou desconectado.", 400
    
    usuario_id = perfil_atual['id'] if not usando_postgres() else perfil_atual[0]
    cursor.close()
    conn.close()

    nome_seguro = secure_filename(nome.lower().replace(" ", "_"))
    caminho_db_capa = f"{nome_seguro}.jpg"
    pasta_final = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
    os.makedirs(pasta_final, exist_ok=True)
    
    extensao = arquivo.filename.rsplit('.', 1)[-1].lower()
    caminho_temporario = os.path.join(pasta_final, secure_filename(arquivo.filename))

    if extensao in ['zip', 'mp4', 'mkv', 'webm']:
        try:
            arquivo.save(caminho_temporario)
        except Exception as e:
            if os.path.exists(pasta_final): shutil.rmtree(pasta_final)
            return f"Erro no salvamento do arquivo temporário: {e}", 500

        # 🚀 ENVIA DIRETAMENTE PARA O TELEGRAM (Nuvem Gratuita e Ilimitada)
        print(f"📤 Enviando '{nome}' para o canal do Telegram...")
        file_id_telegram = enviar_arquivo_para_telegram(caminho_temporario, nome)
        
        # Limpa o arquivo local do Render após subir para o Telegram para não ocupar espaço
        if os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)

        if not file_id_telegram:
            return "Erro: Não foi possível armazenar o arquivo no Telegram. Verifique o Token e o ID do Canal.", 500
    else:
        return "Extensão inválida. Envie arquivos de vídeo diretos ou um pacote .zip.", 400

    # Salvamos o file_id do Telegram no campo 'arquivo' da tabela series
    conn = get_db_connection()
    cursor = conn.cursor()
    executar_query(cursor, '''
        INSERT INTO series (nome, descricao, arquivo, capa, conta_id, usuario_id, eh_video_unico) 
        VALUES (%s, %s, %s, %s, %s, %s, 1)
    ''', (nome, descricao, file_id_telegram, caminho_db_capa, session['conta_id'], usuario_id))
    conn.commit()
    cursor.close()
    conn.close()

    # Criação vazia da capa caso não exista
    caminho_capa_completo = os.path.join(app.config['THUMBNAIL_FOLDER'], caminho_db_capa)
    if not os.path.exists(caminho_capa_completo):
        open(caminho_capa_completo, 'a').close()

    return redirect('/')

def enviar_arquivo_para_telegram(caminho_arquivo, titulo_video):
    """Envia o arquivo de vídeo ou zip para o canal do Telegram e retorna o file_id correto"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', TELEGRAM_BOT_TOKEN)
    canal_id = os.environ.get('TELEGRAM_CHANNEL_ID', TELEGRAM_CHANNEL_ID)
    
    if not token or not canal_id:
        print("❌ Token ou Canal do Telegram não configurados nas variáveis de ambiente.")
        return None

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    
    try:
        with open(caminho_arquivo, 'rb') as arquivo:
            payload = {
                'chat_id': canal_id,
                'caption': f"Backup PobreFlix: {titulo_video}"
            }
            files = {'document': arquivo}
            resposta = requests.post(url, data=payload, files=files)
            
            print(f"Status Telegram: {resposta.status_code}")
            
            if resposta.status_code == 200:
                dados_json = resposta.json()
                resultado = dados_json.get('result', {})
                
                # Tenta pegar o file_id dependendo de como o Telegram processou a mídia
                if 'document' in resultado:
                    file_id = resultado['document']['file_id']
                elif 'video' in resultado:
                    file_id = resultado['video']['file_id']
                else:
                    print("❌ O Telegram respondeu 200, mas nenhuma chave de arquivo válida foi encontrada.")
                    return None
                    
                print(f"✅ File ID capturado com sucesso: {file_id}")
                return file_id
            else:
                print(f"❌ Erro ao enviar para o Telegram: {resposta.text}")
                return None
    except Exception as e:
        print(f"❌ Erro na requisição do Telegram: {e}")
        return None

def obter_url_direta_telegram(file_id):
    """Pega o file_id do banco e solicita ao Telegram um link de download direto válido"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Token do Telegram não configurado.")
        return None
        
    url_file_info = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    
    try:
        resposta = requests.get(url_file_info)
        if resposta.status_code == 200:
            caminho_no_servidor = resposta.json()['result']['file_path']
            return f"https://api.telegram.org/file/bot{token}/{caminho_no_servidor}"
    except Exception as e:
        print(f"❌ Erro ao buscar link do Telegram: {e}")
    return None

@app.route('/deletar_serie_completa/<int:id_filme>', methods=['DELETE'])
def deletar_serie_completa(id_filme):
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, "SELECT arquivo FROM series WHERE id = %s", (id_filme,))
    resultado = cursor.fetchone()
    
    if resultado:
        arquivo_nome = resultado['arquivo'] if not usando_postgres() else resultado[0]
        caminho_pasta = os.path.join(app.config['UPLOAD_FOLDER'], arquivo_nome)
        if os.path.exists(caminho_pasta): shutil.rmtree(caminho_pasta)
        executar_query(cursor, "DELETE FROM series WHERE id = %s", (id_filme,))
        conn.commit()
        
    cursor.close(); conn.close()
    return jsonify({"status": "sucesso"}), 200

@app.route('/deletar_capa_filme/<int:id_filme>', methods=['DELETE'])
def deletar_capa_filme(id_filme):
    conn = get_db_connection()
    cursor = conn.cursor()
    executar_query(cursor, "SELECT capa FROM series WHERE id = %s", (id_filme,))
    resultado = cursor.fetchone()
    
    if resultado and resultado[0]: 
        nome_capa = resultado[0]
        caminho_capa = os.path.join(app.config['THUMBNAIL_FOLDER'], nome_capa)
        if os.path.exists(caminho_capa):
            os.remove(caminho_capa)
    
    executar_query(cursor, "UPDATE series SET capa = NULL WHERE id = %s", (id_filme,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "sucesso"}), 200

@app.route('/deletar_episodio/<nome_serie>/<nome_episodio>', methods=['DELETE'])
def deletar_episodio(nome_serie, nome_episodio):
    if 'conta_id' not in session: return jsonify({"status": "erro"}), 401
    
    pasta_serie = os.path.join(app.config['UPLOAD_FOLDER'], nome_serie)
    caminho_arquivo = os.path.join(pasta_serie, nome_episodio)
    
    if os.path.exists(caminho_arquivo):
        os.remove(caminho_arquivo)
        return jsonify({"status": "sucesso"}), 200
    return jsonify({"status": "erro", "mensagem": "Arquivo não encontrado"}), 404

@app.route('/adicionar_episodio/<nome_serie>', methods=['POST'])
def adicionar_episodio(nome_serie):
    if 'conta_id' not in session: return redirect(url_for('login'))
    
    arquivo = request.files.get('novo_episodio')
    if arquivo and arquivo.filename != '':
        pasta_serie = os.path.join(app.config['UPLOAD_FOLDER'], nome_serie)
        caminho_salvo = os.path.join(pasta_serie, secure_filename(arquivo.filename))
        arquivo.save(caminho_salvo)
        
    return redirect(url_for('ver_serie', nome_serie=nome_serie))

@app.route('/serie/<nome_serie>')
def ver_serie(nome_serie):
    caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], nome_serie)
    if not os.path.isdir(caminho_completo): return redirect('/')

    episodios = sorted([f for f in os.listdir(caminho_completo) if f.lower().endswith(('mp4', 'mkv', 'webm'))])
    nome_exibicao = nome_serie.replace("_", " ")
    return render_template('serie.html', nome=nome_exibicao, episodios=episodios, nome_serie=nome_serie)

@app.route('/video/<nome_serie>/<video_atual>')
def ver_video(nome_serie, video_atual):
  # Se for o File ID do Telegram
  if video_atual.startswith('BAACAg') or len(video_atual) > 30:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', TELEGRAM_BOT_TOKEN)

    # Pede o link direto do arquivo para a API do Telegram
    get_file_url = (
        f'https://api.telegram.org/bot{token}/getFile?file_id={video_atual}'
    )
    resposta_tg = requests.get(get_file_url).json()

    if not resposta_tg.get('ok'):
      return 'Vídeo não encontrado no Telegram', 404

    file_path = resposta_tg['result']['file_path']
    telegram_download_url = (
        f'https://api.telegram.org/file/bot{token}/{file_path}'
    )

    # Redireciona o player do usuário direto para a CDN do Telegram
    return redirect(telegram_download_url)

  else:
    # Modo antigo para arquivos locais (se houver)
    caminho_midia = f'videos/{nome_serie}/{video_atual}'
    url_video_real = url_for('static', filename=caminho_midia)
    url_capa = url_for('static', filename=f'capas/{nome_serie}.jpg')

    return render_template(
        'player.html',
        url_video=url_video_real,
        titulo=video_atual.replace('_', ' ')
        .replace('.mp4', '')
        .replace('.mkv', ''),
        proximo=None,
        nome_serie=nome_serie,
        capa=url_capa,
    )

@app.route('/trocar_capa/<nome_base>', methods=['POST'])
def trocar_capa(nome_base):
    if 'nova_capa' in request.files:
        arquivo_img = request.files['nova_capa']
        if arquivo_img.filename != '':
            caminho_capa = os.path.join(app.config['THUMBNAIL_FOLDER'], f"{nome_base}.jpg")
            arquivo_img.save(caminho_capa)
    return redirect('/')

@app.route('/comunidade')
def comunidade():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    
    executar_query(cursor, '''
        SELECT classificacao FROM series 
        WHERE usuario_id = (SELECT id FROM usuarios WHERE nome = %s AND conta_id = %s LIMIT 1)
        AND classificacao IS NOT NULL AND classificacao != ''
        GROUP BY classificacao 
        ORDER BY COUNT(classificacao) DESC 
        LIMIT 1
    ''', (session.get('usuario_logado'), session['conta_id']))
    
    genero_favorito = cursor.fetchone()
    videos_recomendados = []

    if genero_favorito:
        gen = genero_favorito['classificacao'] if not usando_postgres() else genero_favorito[0]
        executar_query(cursor, '''
            SELECT * FROM feed_publico 
            WHERE (descricao LIKE %s OR titulo LIKE %s) AND autor_id != %s 
            ORDER BY RANDOM() LIMIT 4
        ''', (f"%{gen}%", f"%{gen}%", session['conta_id']))
        videos_recomendados = cursor.fetchall()

    executar_query(cursor, 'SELECT * FROM feed_publico ORDER BY id DESC')
    videos_brutos = cursor.fetchall()
    cursor.close()
    conn.close()
    
    videos_processados = []
    for video in videos_brutos:
        v = dict(video)
        if not v.get('nome_autor'):
            v['nome_autor'] = "Bot Soberano"
        videos_processados.append(v)

    recomendados_processados = [dict(r) for r in videos_recomendados]

    return render_template('comunidade.html', videos=videos_processados, recomendados=recomendados_processados)

@app.route('/meu_canal')
def meu_canal():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT * FROM feed_publico WHERE autor_id = %s', (session['conta_id'],))
    meus_videos = cursor.fetchall()
    cursor.close()
    conn.close()
    
    meus_videos_processados = [dict(row) for row in meus_videos]
    return render_template('canal.html', videos=meus_videos_processados)

@app.route('/publicar_bot', methods=['POST'])
def publicar_bot():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"status": "erro", "mensagem": "Dados ausentes"}), 400

        titulo = dados.get('titulo', 'Vídeo Compartilhado')
        url_video = dados.get('url')
        descricao = dados.get('descricao', 'Enviado via Comunidade')

        if not url_video:
            return jsonify({"status": "erro", "mensagem": "A URL do vídeo é obrigatória"}), 400

        capa = 'https://img.icons8.com/color/512/telegram-app.png'
        if "youtube.com" in url_video or "youtu.be" in url_video:
            try:
                video_id = url_video.split("v=")[1].split("&")[0] if "v=" in url_video else url_video.split("/")[-1].split("?")[0]
                capa = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            except:
                pass

        id_autor = session.get('conta_id', 1)
        nome_autor = session.get('conta_email', 'Bot Soberano').split('@')[0]

        conn = get_db_connection()
        cursor = conn.cursor()
        executar_query(cursor, '''
            INSERT INTO feed_publico (titulo, descricao, url_video, capa_url, autor_id, nome_autor) 
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (titulo, descricao, url_video, capa, id_autor, nome_autor))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "sucesso"}), 200

    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/assistir/<int:video_id>')
def assistir(video_id):
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    
    executar_query(cursor, 'SELECT * FROM series WHERE id = %s', (video_id,))
    video = cursor.fetchone()
    
    if not video:
        executar_query(cursor, 'SELECT * FROM feed_publico WHERE id = %s', (video_id,))
        video = cursor.fetchone()
            
    cursor.close()
    conn.close()

    if video:
        item = dict(video)
        url_banco = None
        
        if 'url_video' in item and item['url_video']:
            url_banco = item['url_video']
        elif 'arquivo' in item and item['arquivo']:
            val_arquivo = item['arquivo']
            # Se parecer um file_id do Telegram (geralmente grande e alfanumérico sem extensão de arquivo)
            if not val_arquivo.endswith(('.mp4', '.mkv', '.webm', '.zip')) and len(val_arquivo) > 20:
                url_banco = obter_url_direta_telegram(val_arquivo)
            else:
                # É um arquivo local antigo na pasta static/videos
                url_banco = url_for('static', filename=f"videos/{val_arquivo}")

        if not url_banco:
            return "Erro: Link ou arquivo vazio.", 400

        titulo_video = item['nome'] if 'nome' in item else item['titulo']
        return render_template('player2.html', url_video=url_banco, titulo=titulo_video)
    
    return "Erro 404", 404

@app.route('/deletar_feed/<int:video_id>', methods=['DELETE'])
def deletar_feed(video_id):
    if 'conta_id' not in session:
        return jsonify({"erro": "Não autorizado."}), 401

    conn = get_db_connection()
    cursor = criar_cursor(conn)
    executar_query(cursor, 'SELECT autor_id FROM feed_publico WHERE id = %s', (video_id,))
    video = cursor.fetchone()

    if not video:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Não encontrado."}), 404

    autor_id_val = video['autor_id'] if not usando_postgres() else video[0]
    if autor_id_val and int(autor_id_val) != int(session['conta_id']):
        cursor.close()
        conn.close()
        return jsonify({"erro": "Você só pode deletar os seus próprios vídeos."}), 403

    executar_query(cursor, 'DELETE FROM feed_publico WHERE id = %s', (video_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"sucesso": True}), 200

@app.route('/gerar_link_direto', methods=['POST'])
def gerar_link_direto():
    data = request.json
    url_original = data.get('url')
    if not url_original: 
        return jsonify({'success': False, 'error': 'URL ausente'}), 400

    # Se não for uma URL real (ex: é apenas o slug 'teste1' ou um nome de arquivo local)
    if not url_original.startswith('http://') and not url_original.startswith('https://'):
        # Trata como um arquivo local na pasta static/videos
        caminho_local = url_for('static', filename=f'videos/{url_original}')
        return jsonify({'success': True, 'url': caminho_local, 'is_youtube': False})

    if 'youtube.com' in url_original or 'youtu.be' in url_original:
        try:
            video_id_match = re.search(r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})', url_original)
            if video_id_match:
                video_id = video_id_match.group(1)
                link_embed = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
                return jsonify({'success': True, 'url': link_embed, 'is_youtube': True})
            else:
                return jsonify({'success': False, 'error': 'ID do YouTube não identificado'}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': f'Erro ao processar link do YouTube: {str(e)}'}), 500

    # Para outros sites da web que usam o yt-dlp
    ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True, 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_original, download=False)
            return jsonify({'success': True, 'url': info.get('url'), 'is_youtube': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/deletar_perfil/<int:id>', methods=['POST'])
def deletar_perfil(id):
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = criar_cursor(conn)
    
    executar_query(cursor, 'SELECT nome FROM usuarios WHERE id = %s AND conta_id = %s', (id, session['conta_id']))
    perfil = cursor.fetchone()
    
    if perfil:
        nome_perfil_deletado = perfil['nome'] if not usando_postgres() else perfil[0]
        
        executar_query(cursor, 'DELETE FROM usuarios WHERE id = %s AND conta_id = %s', (id, session['conta_id']))
        conn.commit()
        
        if session.get('usuario_logado') == nome_perfil_deletado:
            session.pop('usuario_logado', None)
            
    cursor.close()
    conn.close()
    return redirect(url_for('gerenciar_perfis'))

@app.route('/deletar_video_comunidade/<int:video_id>', methods=['POST'])
def deletar_video_comunidade(video_id):
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    executar_query(cursor, 'DELETE FROM feed_publico WHERE id = %s AND autor_id = %s', (video_id, session['conta_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/comunidade')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
