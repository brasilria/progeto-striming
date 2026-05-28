from flask import Flask, render_template, request, redirect, make_response, url_for, jsonify, send_from_directory, session
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import zipfile
import cv2
import shutil
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

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise Exception("A variável de ambiente DATABASE_URL não foi configurada no Render!")
    
    # Corrige variações automáticas de protocolo comuns no Render
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return psycopg2.connect(db_url)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Criação das tabelas no padrão PostgreSQL
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            conta_id INTEGER,
            FOREIGN KEY (conta_id) REFERENCES contas(id),
            UNIQUE(nome, conta_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
        cursor = conn.cursor()
        # Modificado de ? para %s por conta do PostgreSQL
        cursor.execute('SELECT id, email FROM contas WHERE email = %s AND senha = %s', (email, senha))
        conta = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if conta:
            session['conta_id'] = conta[0]
            session['conta_email'] = conta[1]
            return redirect(url_for('gerenciar_perfis'))
        else:
            return "E-mail ou senha incorretos!", 401
            
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if email and senha:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('INSERT INTO contas (email, senha) VALUES (%s, %s)', (email, senha))
                conn.commit()
                cursor.close()
                conn.close()
                return "Conta criada com sucesso! <a href='/login'>Clique aqui para logar</a>"
            except psycopg2.errors.UniqueViolation:
                return "Este e-mail já está cadastrado!", 400
                
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
    cursor = conn.cursor()
    cursor.execute('SELECT id, nome, conta_id FROM usuarios WHERE conta_id = %s', (session['conta_id'],))
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
            cursor.execute('INSERT INTO usuarios (nome, conta_id) VALUES (%s, %s)', (nome, session['conta_id']))
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            pass
        finally:
            cursor.close()
            conn.close()
            
    return redirect(url_for('gerenciar_perfis'))

@app.route('/selecionar_perfil/<int:id>')
def selecionar_perfil(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT nome FROM usuarios WHERE id = %s AND conta_id = %s', (id, session.get('conta_id')))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        session['usuario_logado'] = user[0] 
    return redirect('/')

@app.route('/sair_perfil')
def sair_perfil():
    session.pop('usuario_logado', None) 
    return redirect(url_for('gerenciar_perfis'))

@app.route('/')
def index():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
    if 'usuario_logado' not in session:
        return redirect(url_for('gerenciar_perfis'))

    conn = get_db_connection()
    # Usando RealDictCursor para simular o comportamento de dicionário do sqlite3.Row
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT id FROM usuarios WHERE nome = %s AND conta_id = %s', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        cursor.close()
        conn.close()
        return redirect(url_for('gerenciar_perfis'))
        
    usuario_id = perfil_atual['id']

    # Algoritmo de recomendação
    cursor.execute('''
        SELECT classificacao FROM series 
        WHERE usuario_id = %s AND classificacao IS NOT NULL AND classificacao != ''
        GROUP BY classificacao 
        ORDER BY COUNT(classificacao) DESC 
        LIMIT 1
    ''', (usuario_id,))
    
    genero_favorito = cursor.fetchone()
    videos_recomendados = []

    if genero_favorito:
        cursor.execute('''
            SELECT * FROM feed_publico 
            WHERE descricao LIKE %s AND autor_id != %s 
            ORDER BY RANDOM() LIMIT 4
        ''', (f"%{genero_favorito['classificacao']}%", session['conta_id']))
        videos_recomendados = cursor.fetchall()
    
    if not videos_recomendados:
        cursor.execute('SELECT * FROM feed_publico WHERE autor_id != %s ORDER BY RANDOM() LIMIT 4', (session['conta_id'],))
        videos_recomendados = cursor.fetchall()

    # Catálogo offline do usuário
    cursor.execute('SELECT * FROM series WHERE usuario_id = %s', (usuario_id,))
    series_cruas = cursor.fetchall()
    cursor.close()
    conn.close()

    lista_processada = []
    for s in series_cruas:
        item = dict(s)
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

    # Convertendo objetos de recomendação para dicionários normais para o template
    recomendados_processados = [dict(v) for v in videos_recomendados]

    return render_template('index.html', series=lista_processada, recomendados=recomendados_processados)

def gerar_thumbnail(caminho_video, caminho_saida):
    cap = cv2.VideoCapture(caminho_video)
    if not cap.isOpened():
        print(f"Erro: Não foi possível abrir o vídeo {caminho_video}")
        return

    cap.set(cv2.CAP_PROP_POS_MSEC, 5000)
    sucesso, frame = cap.read()
    
    if not sucesso:
        cap.set(cv2.CAP_PROP_POS_MSEC, 0)
        sucesso, frame = cap.read()

    if not sucesso:
        cap.release()
        return

    h, w, _ = frame.shape
    largura_alvo, altura_alvo = 1920, 1080
    aspecto_alvo = largura_alvo / altura_alvo
    aspecto_original = w / h

    if aspecto_original > aspecto_alvo:
        nova_largura = int(aspecto_alvo * h)
        inicio_w = (w - nova_largura) // 2
        frame_cortado = frame[:, inicio_w : inicio_w + nova_largura]
    else:
        nova_altura = int(w / aspecto_alvo)
        inicio_h = (h - nova_altura) // 2
        frame_cortado = frame[inicio_h : inicio_h + nova_altura, :]

    frame_final = cv2.resize(frame_cortado, (largura_alvo, altura_alvo), interpolation=cv2.INTER_AREA)
    cv2.imwrite(caminho_saida, frame_final, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    cap.release()

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
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM usuarios WHERE nome = %s AND conta_id = %s', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        cursor.close()
        conn.close()
        return "Perfil inválido ou desconectado.", 400
    
    usuario_id = perfil_atual[0]
    cursor.close()
    conn.close()

    nome_seguro = secure_filename(nome.lower().replace(" ", "_"))
    caminho_db_capa = f"{nome_seguro}.jpg"
    pasta_final = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
    os.makedirs(pasta_final, exist_ok=True)
    
    extensao = arquivo.filename.rsplit('.', 1)[-1].lower()
    caminho_original_disco = ""

    if extensao == 'zip':
        caminho_zip_temporario = os.path.join(pasta_final, secure_filename(arquivo.filename))
        arquivo.save(caminho_zip_temporario)

        try:
            with zipfile.ZipFile(caminho_zip_temporario, 'r') as zip_ref:
                zip_ref.extractall(pasta_final)
            os.remove(caminho_zip_temporario) 
        except Exception as e:
            return f"Erro ao descompactar a série: {e}", 500

        arquivos_internos = sorted([f for f in os.listdir(pasta_final) if f.lower().endswith(('.mp4', '.mkv', '.webm'))])
        if not arquivos_internos:
            return "Nenhum arquivo de vídeo suportado localizado dentro do pacote .zip", 400
        
        caminho_original_disco = os.path.join(pasta_final, arquivos_internos[0])

    elif extensao in ['mp4', 'mkv', 'webm']:
        nome_video_limpo = secure_filename(arquivo.filename)
        caminho_original_disco = os.path.join(pasta_final, nome_video_limpo)
        
        try:
            with open(caminho_original_disco, 'wb') as f:
                while True:
                    chunk = arquivo.stream.read(1024 * 1024)
                    if not chunk: break
                    f.write(chunk)
        except Exception as e:
            if os.path.exists(pasta_final): shutil.rmtree(pasta_final)
            return f"Erro no salvamento do filme: {e}", 500
    else:
        return "Extensão inválida. Envie arquivos de vídeo diretos ou um pacote .zip para séries.", 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO series (nome, descricao, arquivo, capa, conta_id, usuario_id) 
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (nome, descricao, nome_seguro, caminho_db_capa, session['conta_id'], usuario_id))
    conn.commit()
    cursor.close()
    conn.close()

    caminho_capa_completo = os.path.join(app.config['THUMBNAIL_FOLDER'], caminho_db_capa)
    if not os.path.exists(caminho_capa_completo):
        open(caminho_capa_completo, 'a').close()

    threading.Thread(
        target=importador.motor_de_importacao, 
        args=(caminho_original_disco, pasta_final, caminho_capa_completo, f".{extensao}")
    ).start()

    return redirect('/')

# Rota para deletar apenas a capa (para o erro 404 de /deletar_capa_filme/2)
@app.route('/deletar_capa_filme/<int:id_filme>', methods=['DELETE'])
def deletar_capa_filme(id_filme):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT capa FROM series WHERE id = %s", (id_filme,))
    resultado = cursor.fetchone()
    
    if resultado:
        nome_capa = resultado[0]
        caminho_capa = os.path.join(app.config['THUMBNAIL_FOLDER'], nome_capa)
        if os.path.exists(caminho_capa):
            os.remove(caminho_capa)
        cursor.execute("UPDATE series SET capa = NULL WHERE id = %s", (id_filme,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "sucesso"}), 200
    
    cursor.close()
    conn.close()
    return jsonify({"status": "erro", "mensagem": "Capa não encontrada"}), 404

# Rota para deletar episódios (a que você precisava)
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
        # Garante que o nome da pasta e do arquivo sejam seguros
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
    caminho_midia = f"videos/{nome_serie}/{video_atual}"
    url_video_real = url_for('static', filename=caminho_midia)
    url_capa = url_for('static', filename=f'capas/{nome_serie}.jpg')

    return render_template(
        'player.html', 
        url_video=url_video_real, 
        titulo=video_atual.replace('_', ' ').replace('.mp4', '').replace('.mkv', '').replace('.webm', ''), 
        proximo=None, 
        nome_serie=nome_serie,
        capa=url_capa
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Busca gênero favorito
    cursor.execute('''
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
        cursor.execute('''
            SELECT * FROM feed_publico 
            WHERE (descricao LIKE %s OR titulo LIKE %s) AND autor_id != %s 
            ORDER BY RANDOM() LIMIT 4
        ''', (f"%{genero_favorito['classificacao']}%", f"%{genero_favorito['classificacao']}%", session['conta_id']))
        videos_recomendados = cursor.fetchall()

    # Feed geral
    cursor.execute('SELECT * FROM feed_publico ORDER BY id DESC')
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM feed_publico WHERE autor_id = %s', (session['conta_id'],))
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
        
        cursor.execute('''
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT * FROM series WHERE id = %s', (video_id,))
    video = cursor.fetchone()
    
    if not video:
        cursor.execute('SELECT * FROM feed_publico WHERE id = %s', (video_id,))
        video = cursor.fetchone()
            
    cursor.close()
    conn.close()

    if video:
        item = dict(video)
        url_banco = None
        
        if 'url_video' in item and item['url_video']:
            url_banco = item['url_video']
        elif 'arquivo' in item and item['arquivo']:
            url_banco = item['arquivo']

        if not url_banco:
            return "Erro: Link vazio.", 400

        titulo_video = item['nome'] if 'nome' in item else item['titulo']
        return render_template('player2.html', url_video=url_banco, titulo=titulo_video)
    
    return "Erro 404", 404

@app.route('/deletar_feed/<int:video_id>', methods=['DELETE'])
def deletar_feed(video_id):
    if 'conta_id' not in session:
        return jsonify({"erro": "Não autorizado."}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT autor_id FROM feed_publico WHERE id = %s', (video_id,))
    video = cursor.fetchone()

    if not video:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Não encontrado."}), 404

    if video[0] and int(video[0]) != int(session['conta_id']):
        cursor.close()
        conn.close()
        return jsonify({"erro": "Você só pode deletar os seus próprios vídeos."}), 403

    cursor.execute('DELETE FROM feed_publico WHERE id = %s', (video_id,))
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

    # Se for um link do YouTube, não usamos o yt-dlp (evita bloqueio de robô)
    if 'youtube.com' in url_original or 'youtu.be' in url_original:
        try:
            # Extrai o ID do vídeo usando expressão regular (pega formatos comuns e shorts)
            video_id_match = re.search(r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})', url_original)
            if video_id_match:
                video_id = video_id_match.group(1)
                link_embed = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
                # Retornamos uma flag 'is_youtube': True para o HTML saber que deve abrir um iframe
                return jsonify({'success': True, 'url': link_embed, 'is_youtube': True})
            else:
                return jsonify({'success': False, 'error': 'ID do YouTube não identificado'}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': f'Erro ao processar link do YouTube: {str(e)}'}), 500

    # Se for link de outro servidor (como Telegram), mantém o comportamento normal com o yt-dlp
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
    cursor = conn.cursor()
    
    cursor.execute('SELECT nome FROM usuarios WHERE id = %s AND conta_id = %s', (id, session['conta_id']))
    perfil = cursor.fetchone()
    
    if perfil:
        nome_perfil_deletado = perfil[0]
        
        cursor.execute('DELETE FROM usuarios WHERE id = %s AND conta_id = %s', (id, session['conta_id']))
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
    cursor.execute('DELETE FROM feed_publico WHERE id = %s AND autor_id = %s', (video_id, session['conta_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/comunidade')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
