import os
from dotenv import load_dotenv

# .env dosyasının yolunu projenin kök dizinine göre ayarla
# Bu betiğin bulunduğu dizinden bir üst dizine çıkarak .env'yi buluruz.
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')

# .env dosyasını yükle, eğer varsa
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


# Gemini API Anahtarı (Opsiyonel)
# Bu anahtar, belirli bir kullanıcıya bağlı olmadığı için burada kalabilir.
GEMINI_API_KEY = "AIzaSyBdr_QbAAEbMe4MQ2H-MRwKbahSs5MXCp8"
