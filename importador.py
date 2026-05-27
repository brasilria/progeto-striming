import os
import zipfile
import cv2
import shutil
import threading

def gerar_capa_avulsa(video_path, thumb_path):
    """Uma única 'fornalha' processando um vídeo."""
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(thumb_path, frame)
    cap.release()

def motor_de_importacao(caminho_zip, pasta_final, caminho_capa_db, extensao):
    """
    Gerencia a extração e a divisão do trabalho.
    """
    try:
        # PASSO 1: Extração (Se for ZIP)
        if extensao == '.zip':
            with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    fname = file_info.filename.lower()
                    # Filtra apenas o que importa (vídeos) e ignora lixo de sistema
                    if fname.endswith(('.mp4', '.mkv', '.webm')) and not fname.startswith('__macosx'):
                        filename = os.path.basename(file_info.filename)
                        if not filename: continue
                        
                        with zip_ref.open(file_info) as source, \
                             open(os.path.join(pasta_final, filename), "wb") as target:
                            shutil.copyfileobj(source, target)
            
            # Limpa o ZIP original para economizar espaço (o 'balde' vazio)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)

        videos_extraidos = sorted([f for f in os.listdir(pasta_final) if f.lower().endswith(('.mp4', '.mkv', '.webm'))])
        
        threads = []
        for vid in videos_extraidos:
            caminho_vid = os.path.join(pasta_final, vid)
            # Para não sobrecarregar, vamos gerar apenas a capa principal da série 
            # Mas a lógica permite gerar de todos se você quiser no futuro
            if vid == videos_extraidos[0]: 
                t = threading.Thread(target=gerar_capa_avulsa, args=(caminho_vid, caminho_capa_db))
                threads.append(t)
                t.start()

        # Espera as capas essenciais terminarem
        for t in threads:
            t.join()

        print(f"✅ Série '{os.path.basename(pasta_final)}' processada com sucesso!")

    except Exception as e:
        print(f"❌ Erro no motor: {e}")