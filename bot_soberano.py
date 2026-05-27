import telebot # pip install pyTelegramBotAPI
import requests

TOKEN = '7905838078:AAHLkRxtsTWA9gGdS2osdd8m7Md1e_JxWOQ'
API_POBREFIX = 'http://127.0.0.1:5000/publicar_via_bot'
bot = telebot.TeleBot(TOKEN)

@bot.channel_post_handler(content_types=['video'])
def handle_channel_video(message):
    # 1. Pegamos o ID do arquivo de vídeo real no servidor do Telegram
    file_id = message.video.file_id
    
    # 2. Pedimos ao Telegram o caminho para baixar esse arquivo
    file_info = bot.get_file(file_id)
    file_path = file_info.file_path
    
    # 3. GERAMOS O LINK .MP4 REAL (Soberania de Dados)
    # Esse link aponta direto para o arquivo bruto nos servidores do Telegram
    link_direto_mp4 = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    
    titulo = message.caption if message.caption else "Vídeo R.S.C.B."
    
    # 4. Envia o link .mp4 PRONTO para o seu banco de dados
    dados = {
        "titulo": titulo,
        "url": link_direto_mp4
    }
    
    try:
        requests.post(API_POBREFIX, json=dados)
        print(f"✅ SUCESSO: Link .mp4 gerado e enviado: {titulo}")
    except:
        print("❌ Erro: Seu site (app.py) está desligado.")

print("📡 Bot Gerador de .mp4 Ativado...")
bot.polling()