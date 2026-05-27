import sqlite3

def atualizar_meu_banco():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    print("Criando tabelas da comunidade...")

    # Tabela de Usuários (Estilo Zangi)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pobre_id TEXT UNIQUE,
            nome TEXT,
            conta_id INTEGER,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de Vídeos (Estilo YouTube) - O SEU ERRO ESTÁ AQUI
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feed_publico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            descricao TEXT,
            autor_id TEXT,
            telegram_file_id TEXT,
            capa_url TEXT,
            denuncias INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    print("Sucesso! Agora a tabela 'feed_publico' existe.")

if __name__ == "__main__":
    atualizar_meu_banco()
