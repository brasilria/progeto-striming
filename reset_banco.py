import sqlite3

def corrigir_tabela_series():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    print("🔧 Ajustando a tabela 'series' para o formato esperado pelo app.py...")
    
    # Removemos a versão anterior que estava com nomes diferentes
    cursor.execute('DROP TABLE IF EXISTS series')

    # Criamos a tabela com os nomes EXATOS que o seu erro mostrou:
    # id, nome, descricao, arquivo, capa
    cursor.execute('''
        CREATE TABLE series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,         -- O app.py busca 'nome'
            descricao TEXT,             -- O app.py busca 'descricao'
            arquivo TEXT,               -- O app.py busca 'arquivo'
            capa TEXT,                  -- O app.py busca 'capa'
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ Tabela 'series' corrigida! O erro 'no such column: nome' deve sumir agora.")

if __name__ == '__main__':
    corrigir_tabela_series()