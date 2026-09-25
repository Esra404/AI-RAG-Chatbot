# Luna RAG Chat

OpenAI `gpt-5.6-luna`, yerel Jina embeddings ve FAISS kullanan, sohbetleri ve belge durumlarını kalıcı saklayan RAG sohbet uygulaması.

## Kurulum

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` içindeki `OPENAI_API_KEY` değerini doldurun ve uygulamayı başlatın:

```powershell
python run.py
```

Tarayıcıda `http://127.0.0.1:8001` adresini açın.

İsterseniz farklı bir port kullanmak için:

```powershell
$env:PORT = "9000"
python run.py
```

## Veri düzeni

- `config/document_registry.json`: içerik hash'i, belge ID'si, FAISS/chunk yolları ve aktiflik durumu
- `config/chats.json`: sohbetler ve tüm mesaj geçmişi
- `data/uploads/`: yüklenen asıl dosyalar
- `data/indexes/`: belge ID'sine göre bağımsız FAISS indeksleri
- `data/indexes/{belge-id}.json`: inceleme amacıyla FAISS vektörlerinin okunabilir JSON kopyası
- `data/chunks/`: indeks satırlarını belge parçalarıyla eşleyen JSON dosyaları

Aynı içeriğe sahip bir dosya yeniden yüklenirse SHA-256 kimliği sayesinde tekrar embed edilmez.

Embedding işlemi `jinaai/jina-embeddings-v5-text-nano` ile tamamen yerelde yapılır. Model ilk belge yüklemesinde Hugging Face üzerinden indirilir ve sonraki çalıştırmalarda yerel önbellekten yüklenir. Güvenilir ve tekrarlanabilir kurulum için model revision'ı `.env.example` içinde sabitlenmiştir. OpenAI API yalnızca Luna sohbet yanıtları için kullanılır.

Model proje içindeki `models/jina-embeddings-v5-text-nano` klasöründe tutulur. `config/model_state.json` dosyasındaki `downloaded` alanı indirme durumunu gösterir. Model dosyaları mevcut ve değer `true` ise Hugging Face ağına bağlanılmaz; dosyalar yoksa değer `false` olur ve ilk embedding sorgusunda model indirilir.

Jina v5 text nano modeli CC BY-NC 4.0 lisanslıdır. Ticari kullanım için Jina'nın lisans koşullarını inceleyin.

> Windows'ta FAISS uyumluluğu için Python 3.12 önerilir. API çağrıları için OpenAI hesabınızda kullanılabilir kredi bulunmalıdır.
