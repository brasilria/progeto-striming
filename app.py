from flask import Flask, render_template, request, redirect, make_response, url_for, jsonify, send_from_directory, session
import sqlite3
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
from flask import Flask, render_template, request

app = Flask(__name__)
app.secret_key = 'pobreflix_chave_secreta_super_segura'
app.config['UPLOAD_FOLDER'] = 'static/videos' 
app.config['THUMBNAIL_FOLDER'] = 'static/capas'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 1. TABELA DE CONTAS PRINCIPAIS (E-mail e Senha)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    ''')
    
    # 2. TABELA DE PERFIS (Vinculada a uma conta_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            conta_id INTEGER,
            FOREIGN KEY (conta_id) REFERENCES contas(id),
            UNIQUE(nome, conta_id)
        )
    ''')
    
    # 3. TABELA DE SÉRIES (Vinculada a uma conta_id e usuario_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT,
            arquivo TEXT,
            capa TEXT,
            classificacao TEXT,  -- <--- ADICIONE ESTA LINHA
            conta_id INTEGER,
            usuario_id INTEGER,
            eh_video_unico INTEGER DEFAULT 0,
            primeiro_video TEXT,
            FOREIGN KEY (conta_id) REFERENCES contas(id)
        )
    ''')
    
    # 4. TABELA DO FEED PÚBLICO (ONLINE) - CORRIGIDA E COMPLETA
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
            data_postagem DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (autor_id) REFERENCES contas(id)
        )
    ''')
    
    # Garantias de colunas extras caso o banco local já existisse antigo
    try: cursor.execute("ALTER TABLE series ADD COLUMN conta_id INTEGER")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE series ADD COLUMN usuario_id INTEGER")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE usuarios ADD COLUMN conta_id INTEGER")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE series ADD COLUMN eh_video_unico INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE series ADD COLUMN primeiro_video TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE feed_publico ADD COLUMN nome_autor TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE feed_publico ADD COLUMN autor_id INTEGER")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE series ADD COLUMN classificacao TEXT")
    except sqlite3.OperationalError: pass

    conn.commit()
    conn.close()

@app.before_request
def verificar_banco():
    init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, email FROM contas WHERE email = ? AND senha = ?', (email, senha))
        conta = cursor.fetchone()
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
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute('INSERT INTO contas (email, senha) VALUES (?, ?)', (email, senha))
                conn.commit()
                conn.close()
                return "Conta criada com sucesso! <a href='/login'>Clique aqui para logar</a>"
            except sqlite3.IntegrityError:
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
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM usuarios WHERE conta_id = ?', (session['conta_id'],))
    perfis = cursor.fetchall()
    conn.close()
    
    return render_template('perfis.html', perfis=perfis)

@app.route('/criar_perfil', methods=['POST'])
def criar_perfil():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    nome = request.form.get('nome')
    if nome:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (nome, conta_id) VALUES (?, ?)', (nome, session['conta_id']))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()
            
    return redirect(url_for('gerenciar_perfis'))

@app.route('/selecionar_perfil/<int:id>')
def selecionar_perfil(id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nome FROM usuarios WHERE id = ? AND conta_id = ?', (id, session.get('conta_id')))
    user = cursor.fetchone()
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

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM usuarios WHERE nome = ? AND conta_id = ?', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        conn.close()
        return redirect(url_for('gerenciar_perfis'))
        
    usuario_id = perfil_atual[0]

    # --- AQUI COMEÇA O ALGORITMO DE RECOMENDAÇÃO AUTOMÁTICA ---
    # 1. Descobre qual a classificação/gênero que este usuário mais tem em seu catálogo
    cursor.execute('''
        SELECT classificacao FROM series 
        WHERE usuario_id = ? AND classificacao IS NOT NULL AND classificacao != ''
        GROUP BY classificacao 
        ORDER BY COUNT(classificacao) DESC 
        LIMIT 1
    ''', (usuario_id,))
    
    genero_favorito = cursor.fetchone()
    
    videos_recomendados = []
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if genero_favorito:
        # 2. Se ele tem um gênero favorito, busca vídeos online na comunidade do mesmo gênero
        # mas que NÃO foram postados por ele mesmo (autor_id != conta_id)
        cursor.execute('''
            SELECT * FROM feed_publico 
            WHERE descricao LIKE ? AND autor_id != ? 
            ORDER BY RANDOM() LIMIT 4
        ''', (f"%{genero_favorito[0]}%", session['conta_id']))
        videos_recomendados = cursor.fetchall()
    
    # Se ele for um usuário novo e não tiver nenhum vídeo ainda, recomenda 4 vídeos aleatórios da comunidade
    if not videos_recomendados:
        cursor.execute('SELECT * FROM feed_publico WHERE autor_id != ? ORDER BY RANDOM() LIMIT 4', (session['conta_id'],))
        videos_recomendados = cursor.fetchall()
    # ---------------------------------------------------------

    # Coleta os vídeos normais do usuário (Seu catálogo offline)
    cursor.execute('SELECT * FROM series WHERE usuario_id = ?', (usuario_id,))
    series_cruas = cursor.fetchall()
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
            else: item['eh_video_unico'] = False; item['primeiro_video'] = None
        else:
            item['eh_video_unico'] = True
            item['primeiro_video'] = item['arquivo']
        lista_processada.append(item)

    # Passa os seus vídeos normais AND os recomendados automaticamente para o HTML
    return render_template('index.html', series=lista_processada, recomendados=videos_recomendados)

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

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM usuarios WHERE nome = ? AND conta_id = ?', (session['usuario_logado'], session['conta_id']))
    perfil_atual = cursor.fetchone()
    
    if not perfil_atual:
        conn.close()
        return "Perfil inválido ou desconectado.", 400
    
    usuario_id = perfil_atual[0]
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

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO series (nome, descricao, arquivo, capa, conta_id, usuario_id) 
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (nome, descricao, nome_seguro, caminho_db_capa, session['conta_id'], usuario_id))
    conn.commit()
    conn.close()

    caminho_capa_completo = os.path.join(app.config['THUMBNAIL_FOLDER'], caminho_db_capa)
    if not os.path.exists(caminho_capa_completo):
        open(caminho_capa_completo, 'a').close()

    threading.Thread(
        target=importador.motor_de_importacao, 
        args=(caminho_original_disco, pasta_final, caminho_capa_completo, f".{extensao}")
    ).start()

    return redirect('/')

@app.route('/deletar_filme_local/<int:id_filme>', methods=['POST'])
def deletar_filme_local(id_filme):
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT arquivo, capa FROM series WHERE id = ?", (id_filme,))
        item = cursor.fetchone()

        if item:
            nome_pasta, nome_capa = item
            caminho_pasta = os.path.join(app.config['UPLOAD_FOLDER'], nome_pasta)
            caminho_capa = os.path.join(app.config['THUMBNAIL_FOLDER'], nome_capa)

            if os.path.exists(caminho_pasta): shutil.rmtree(caminho_pasta)
            if os.path.exists(caminho_capa): os.remove(caminho_capa)

            cursor.execute("DELETE FROM series WHERE id = ?", (id_filme,))
            conn.commit()
            conn.close()
            return jsonify({"status": "sucesso"}), 200
        return jsonify({"status": "erro"}), 404
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/serie/<nome_serie>')
def ver_serie(nome_serie):
    caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], nome_serie)
    if not os.path.isdir(caminho_completo): return redirect('/')

    episodios = sorted([f for f in os.listdir(caminho_completo) if f.lower().endswith(('mp4', 'mkv', 'webm'))])
    nome_exibicao = nome_serie.replace("_", " ")
    return render_template('serie.html', nome=nome_exibicao, episodios=episodios, nome_serie=nome_serie)

@app.route('/video/<nome_serie>/<video_atual>')
def ver_video(nome_serie, video_atual):
    # Criamos a variável com o nome correto: caminho_midia
    caminho_midia = f"videos/{nome_serie}/{video_atual}"
    
    # CORRIGIDO: Agora usamos 'caminho_midia' exatamente como foi criada acima
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
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 1. Descobre o género/classificação que este utilizador mais tem no seu catálogo offline
    cursor.execute('''
        SELECT classificacao FROM series 
        WHERE usuario_id = (SELECT id FROM usuarios WHERE nome = ? AND conta_id = ? LIMIT 1)
        AND classificacao IS NOT NULL AND classificacao != ''
        GROUP BY classificacao 
        ORDER BY COUNT(classificacao) DESC 
        LIMIT 1
    ''', (session.get('usuario_logado'), session['conta_id']))
    
    genero_favorito = cursor.fetchone()
    
    videos_recomendados = []
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2. Se ele tiver um género favorito, vai buscar 4 vídeos aleatórios desse género na comunidade
    if genero_favorito:
        cursor.execute('''
            SELECT * FROM feed_publico 
            WHERE (descricao LIKE ? OR titulo LIKE ?) AND autor_id != ? 
            ORDER BY RANDOM() LIMIT 4
        ''', (f"%{genero_favorito[0]}%", f"%{genero_favorito[0]}%", session['conta_id']))
        videos_recomendados = cursor.fetchall()

    # 3. Procura o feed geral da comunidade (todos os vídeos)
    cursor.execute('SELECT * FROM feed_publico ORDER BY id DESC')
    videos_brutos = cursor.fetchall()
    conn.close()
    
    # Processa os vídeos do feed geral
    videos_processados = []
    for video in videos_brutos:
        v = dict(video)
        if not v.get('nome_autor'):
            v['nome_autor'] = "Bot Soberano"
        videos_processados.append(v)

    # Converte os recomendados em dicionários para o Jinja
    recomendados_processados = [dict(r) for r in videos_recomendados]

    # Passa o feed normal E as recomendações para o comunidade.html
    return render_template('comunidade.html', videos=videos_processados, recomendados=recomendados_processados)

@app.route('/meu_canal')
def meu_canal():
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM feed_publico WHERE autor_id = ?', (session['conta_id'],))
    meus_videos = cursor.fetchall()
    conn.close()
    
    return render_template('canal.html', videos=meus_videos)

# ─── ROTA UNIFICADA E ADAPTADA AO FORMULÁRIO DO SEU HTML ───
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

        # Lógica para gerar automaticamente as capas de vídeos do YouTube
        capa = 'https://img.icons8.com/color/512/telegram-app.png'
        if "youtube.com" in url_video or "youtu.be" in url_video:
            try:
                video_id = url_video.split("v=")[1].split("&")[0] if "v=" in url_video else url_video.split("/")[-1].split("?")[0]
                capa = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            except:
                pass

        id_autor = session.get('conta_id', 1)
        nome_autor = session.get('conta_email', 'Bot Soberano').split('@')[0]

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # Inserção explícita na coluna nome_autor
        cursor.execute('''
            INSERT INTO feed_publico (titulo, descricao, url_video, capa_url, autor_id, nome_autor) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (titulo, descricao, url_video, capa, id_autor, nome_autor))
        
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso"}), 200

    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/assistir/<int:video_id>')
def assistir(video_id):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM series WHERE id = ?', (video_id,))
    video = cursor.fetchone()
    
    if not video:
        try:
            cursor.execute('SELECT * FROM feed_publico WHERE id = ?', (video_id,))
            video = cursor.fetchone()
        except sqlite3.OperationalError:
            pass
            
    conn.close()

    if video:
        colunas = video.keys()
        url_banco = None
        
        if 'url_video' in colunas and video['url_video']:
            url_banco = video['url_video']
        elif 'arquivo' in colunas and video['arquivo']:
            url_banco = video['arquivo']

        if not url_banco:
            return "Erro: Link vazio.", 400

        titulo_video = video['nome'] if 'nome' in colunas else video['titulo']
        return render_template('player2.html', url_video=url_banco, titulo=titulo_video)
    
    return "Erro 404", 404

@app.route('/deletar_feed/<int:video_id>', methods=['DELETE'])
def deletar_feed(video_id):
    if 'conta_id' not in session:
        return jsonify({"erro": "Não autorizado."}), 401

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT autor_id FROM feed_publico WHERE id = ?', (video_id,))
    video = cursor.fetchone()

    if not video:
        conn.close()
        return jsonify({"erro": "Não encontrado."}), 404

    if video[0] and int(video[0]) != int(session['conta_id']):
        conn.close()
        return jsonify({"erro": "Você só pode deletar os seus próprios vídeos."}), 403

    cursor.execute('DELETE FROM feed_publico WHERE id = ?', (video_id,))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True}), 200

@app.route('/gerar_link_direto', methods=['POST'])
def gerar_link_direto():
    data = request.json
    url_original = data.get('url')
    if not url_original: return jsonify({'success': False, 'error': 'URL ausente'}), 400

    ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True, 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_original, download=False)
            return jsonify({'success': True, 'url': info.get('url')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/deletar_perfil/<int:id>', methods=['POST'])
def deletar_perfil(id):
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 1. Garante que o perfil a ser deletado realmente pertence à conta logada na sessão
    cursor.execute('SELECT nome FROM usuarios WHERE id = ? AND conta_id = ?', (id, session['conta_id']))
    perfil = cursor.fetchone()
    
    if perfil:
        nome_perfil_deletado = perfil[0]
        
        # 2. Executa a remoção cirúrgica do perfil selecionado
        cursor.execute('DELETE FROM usuarios WHERE id = ? AND conta_id = ?', (id, session['conta_id']))
        conn.commit()
        
        # 3. Se o perfil removido for o que estava ativo na sessão no momento, limpa-o da memória
        if session.get('usuario_logado') == nome_perfil_deletado:
            session.pop('usuario_logado', None)
            
    conn.close()
    return redirect(url_for('gerenciar_perfis'))

@app.route('/deletar_video_comunidade/<int:video_id>', methods=['POST'])
def deletar_video_comunidade(video_id):
    if 'conta_id' not in session:
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Só deleta se o vídeo realmente foi postado por essa conta
    cursor.execute('DELETE FROM feed_publico WHERE id = ? AND autor_id = ?', (video_id, session['conta_id']))
    
    conn.commit()
    conn.close()
    return redirect('/comunidade')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
