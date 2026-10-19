# Three-Tier Memory Engine

Python 3.11+ ile çalışan, SQLite üzerinde kalıcı ve kullanıcı kapsamında yalıtılmış agent hafızası. Çekirdek kütüphane standart kütüphane dışında bağımlılık ve ağ gerektirmez. FastAPI isteğe bağlıdır.

Working memory görev durumunu; episodic memory geçmiş olay ve sonuçları; semantic memory yeniden kullanılabilir tercih ve bilgileri saklar. Her konuşma otomatik kaydedilmez. Otomatik çıkarım ayrıca etkinleştirilir ve semantic çıktılar doğrulanmamış aday olur.

## Sprint durumu — 19 Ekim 2026

| Sprint | Durum | Kanıt |
|---|---|---|
| V1 — çekirdek ve CLI | Tamamlandı | Kalıcılık, yalıtım, TTL, transaction rollback, kota, sürüm yarışı ve CLI testleri |
| V2 — Assembler | Tamamlandı | Mevcut Dynamic Context Assembler'ın gerçek `assemble` sözleşmesiyle testler; iki süreçli oturum demosu |
| V3 — hybrid retrieval | Tamamlandı, offline kapsam | Model/boyut/hash doğrulama, cosine + RRF, silme testleri; gerçek embedding modeli ölçülmedi |
| V4 — kontrollü çıkarım | Tamamlandı, mock kapsam | Açık etkinleştirme, kaynak doğrulama, timeout, idempotency, işlem yarışı, toplu kota ve secret testleri |
| V5 — HTTP ve operasyon | Kısmen tamamlandı | HTTP/operasyon kodu, CI, Dockerfile, runbook ve değerlendirme hazır; gerçek yerel HTTP smoke geçti. Docker motoru yanıt vermediği için container sağlık testi bekliyor |

Son doğrulama: **81 pytest testi geçti**, Ruff temiz. Bağımsız incelemenin dört önemli bulgusu regresyon testleriyle giderildi. 19 Ekim 2026 ikinci incelemesinde beş bulgu (B1–B5: sözcüksüz içerik/sorgu, sürüm geçmişi kotası, kimlik öncesi arama kotası, döngü hata kodu, aday sınırı) kanıt ve regresyon testleriyle giderildi. Ayrıntılar: [doğrulama](docs/verification.md), [inceleme raporu](docs/review-2026-10-19.html), [çalışma günlüğü](docs/progress.md).

Canlı LLM/embedding çağrısı, bağımsız insan kalite değerlendirmesi, uzak CI çalıştırması ve bulut yayını yapılmadı. Bunlar yapılmış gibi raporlanmaz.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                       # yalnızca çekirdek
pip install -r requirements-dev.lock   # API ve test bağımlılıkları
```

Bağımlılıkların ilk kurulumu ağ veya önceden hazırlanmış wheel deposu gerektirir. Testler ve demolar API anahtarsız çalışır; pytest varsayılanında dış ağ bağlantıları engellenir. Kilitli bağımlılıklar bu ortamda Python 3.13 ile doğrulandı; stdlib çekirdek Python 3.11 ile de smoke test edildi. CI, 3.11 ve 3.13 matrisi içerir fakat uzak CI burada çalıştırılmadı.

Mevcut komşu Assembler projesiyle:

```bash
export PYTHONPATH="src:../dynamic-context-assembler/src"
python -m pytest -q
python -m ruff check src tests examples evaluations scripts
python examples/two_sessions.py
python evaluations/run.py --output evaluations/results-v1.json
python scripts/http_smoke.py
```

Assembler ayrı kütüphanedir. Taşınan kurulumlarda `pip install -e /path/to/dynamic-context-assembler` kullanın. Memory çekirdeği Assembler'ı import etmez; adaptör çağrısı ve entegrasyon testleri bu bağımlılığı gerektirir.

## CLI

Girdi/çıktı JSON'dur. CLI yerel, güvenilir operatör arayüzüdür; `--tenant/--user` kimlik doğrulama değildir. Dış erişim için HTTP sınırı kullanın.

```bash
printf '%s' '{"tier":"episodic","content":"AWS IAM policy evaluation tamamlandı","source_refs":["event:session-A"]}' | \
  memory-engine --db data/memory.db --tenant demo --user learner create --idempotency-key event-A

printf '%s' '{"tier":"semantic","content":"Türkçe ve örnekli açıklamalar tercih ediliyor","fact_key":"explanation_style","verification_status":"verified","source_refs":["event:user-preference"]}' | \
  memory-engine --db data/memory.db --tenant demo --user learner create --authoritative

memory-engine --db data/memory.db --tenant demo --user learner search 'AWS IAM'
memory-engine --db data/memory.db --tenant demo --user learner search '' --tier working --session-id B --task-id aws
memory-engine --db data/memory.db --tenant demo --user learner get RECORD_ID
printf '%s' '{"content":"Yeni içerik"}' | memory-engine --db data/memory.db --tenant demo --user learner update RECORD_ID --version 1
memory-engine --db data/memory.db --tenant demo --user learner delete RECORD_ID
memory-engine --db data/memory.db --tenant demo --user learner expire
memory-engine --db data/memory.db --tenant demo --user learner delete-user
```

`--authoritative`, açık kullanıcı düzeltmesini temsil eder. Aynı `fact_key` için eski aktif kayıt superseded olur. Yetkisiz/belgeden gelen çelişki candidate olur. Candidate/superseded kayıtlar retrieval'a girmez; kimlikleriyle `get` incelemesi yapılabilir. Adayı kabul etmek için yetkili yeni bir semantic kayıt oluşturulur; doğrudan durum alanı değiştirilmez.

## Python

```python
from memory_engine import MemoryInput, MemoryService, Repository, Scope

engine = MemoryService(Repository("data/memory.db"))
scope = Scope("demo", "learner")
record = engine.create(scope, MemoryInput(
    tier="working", content="İki belge incelendi, üçüncü bekliyor",
    session_id="B", task_id="review", source_refs=["event:tool-result"]
))
results = engine.retrieve(scope, "belge", session_id="B", task_id="review")
```

Her kayıtta UTC aware zaman, sahiplik, kaynaklar, sürüm, importance ve confidence bulunur. NaN, infinity, booleana dönüştürülmüş sayılar, geçersiz Unicode, boş kapsam ve aşırı içerik açık hata üretir. `clock` ve `Policy` testlerde enjekte edilir.

## Arama ve Assembler sınırı

Önce SQL ile tenant/user/status/expiry ve working session/task filtresi uygulanır. Vector adayları da aynı listeden üretilir. Kaynakları geçersiz türevler ayrıca elenir. Okuma güncelliği değiştirmez.

Lexical normalizasyon NFC + Türkçe `İ → i`, `I → ı` + casefold ve Unicode kelime parçalamadır. Sonek, eşanlam ve doğal dil anlama iddiası yoktur. Query tokenlarının eşleşen oranı relevance'tır.

`final_score = .60 × relevance + .25 × recency + .15 × importance`; `recency = 2 ** (-age_days / half_life_days)`. Working updated_at, episodic occurred_at veya created_at, semantic verified_at veya created_at kullanır. Eşit skorda id sırası seçilir. Boş sorgu yalnızca açıkça `tier_filters=["working"]` ve session/task ile güncel görev durumunu getirir.

Assembler'ın `working_memory` alanı bir **bağlam kategorisidir**; storage tier değildir. Üç katman burada `tier` ve `source_refs` ile taşınır. `required=False`; Assembler `importance` alanına engine `final_score` aktarılır. Adaptör `retrieved`, `selected`, `dropped`, kaynak eşlemesi ve eleme nedenlerini ayrı döndürür. Son token kararı Assembler'a aittir; approximate counter sağlayıcı tokenizer garantisi vermez.

Hybrid arama ayrı lexical ve cosine sıralamalarını RRF `k=60` ile birleştirir. Fused relevance, teorik maksimum `2/61` değerine bölünür. Cosine eşik varsayılanı .25. Model/sürüm/boyut/içerik hash'i değişince `reindex_required` döner; `index_scope` yeniden çalıştırılır. `HashEmbedder` yalnızca çevrimdışı entegrasyon içindir; ölçümde yanlış pozitif üretmiştir. Varsayılan arama lexical kalır.

## Kapasite ve yaşam döngüsü

| Politika | Varsayılan |
|---|---|
| Working TTL / half-life | 24 saat / 1 gün |
| Episodic TTL / half-life | 90 gün / 30 gün |
| Semantic TTL / half-life | Otomatik expiry yok / 180 gün |
| Kullanıcı + tier kotası | 1.000 kayıt, 4 MiB kayıt/sürüm payload'u |
| İçerik / metadata / kaynak | 16 KiB / 4 KiB / 64 kaynak |
| Sorgu / top_k / aday | 4 KiB / 100 / 3.000 |
| Minimum lexical relevance | .05 |
| Eviction | Varsayılan kapalı; açılırsa importance < .3, sonra oldest-first, sonra id |
| Adaptör | 100 item, 64 KiB payload |

Kotalar SQLite dosyasının fiziksel boyutu değildir; indeksler, WAL ve embedding overhead'i ayrı olabilir. Eviction doğrulanmış semantic kayıtları, doğrulanmış türevlerin kaynaklarını ve aynı transaction'ın yeni çıktılarının kaynaklarını korur. Alan yoksa `quota_exceeded`; transaction geri alınır. Geçmiş sürümler byte kotasına dahildir. Eviction açıkken kota aşıldığında önce en eski sürüm payload'ları geri kazanılır (canlı kayıt `memories.payload`'da kaldığı için veri kaybı yoktur), ardından kayıt tahliyesi uygulanır; böylece sık güncellenen tek bir kayıt sürüm geçmişi yüzünden kalıcı olarak güncellenemez hale gelmez.

`memory:ID` kaynakları yönetilen bağımlılıktır; kaynak silindiğinde bütün türevler, embedding'ler ve ilgili işlem cache'leri silinir. Kaynak süresi dolduğunda temizlik öncesinde bile türev retrieval'da görünmez. Kaynak içerik değişimi eski türevleri geçersizleştirir. `event:...` gibi dış kaynakların yaşam döngüsü çağıran uygulamanın sorumluluğundadır.

Idempotency anahtarı tenant/user kapsamındadır; payload/authority değişirse 409. Anahtar ilgili kayıt silinene kadar tutulur. Aynı metinli ayrı olaylar otomatik birleştirilmez. `delete_user_data` yalnızca doğrulanmış kullanıcı kapsamını temizler. İçeriksiz kalıcı denetim günlüğü tutulmaz.

## Otomatik çıkarım

`ExtractionService(engine, provider, enabled=True)` açıkça etkinleştirilir. Provider `async extract(request, max_output_tokens=...)` uygular; varsayılan iş başına tek çağrı, 10 saniye timeout, 32 kaynak, 8 fact, 8192 input / 4096 output token tavanı bulunur. UTF-8 byte sayısı konservatif token tavanı olarak kullanılır; büyük girdi sessizce kesilmez.

Şema yalnızca `summary` ve `facts` kabul eder. Çıktı kaynakta birebir bulunan alıntı olmak zorundadır; serbest paraphrase desteklenmez. Bu yöntem desteklenmeyen iddiaları sınırlar, anlam doğruluğu veya kusursuz prompt injection/DLP koruması sağlamaz. Özet olay zamanı kaynaktan taşınır; bilinmiyorsa boş kalır. Secret kalıpları ve bazı açık injection metinleri provider çağrısından önce reddedilir. Açık API/CLI kayıtları için kapsamlı DLP garantisi yoktur; secret'ları içerik veya metadata'ya koymayın.

Semantic sonuçlar her zaman `candidate` ve `unverified`; LLM doğrulanmış bilgiyi değiştiremez/silemez. Importance `.5 + .2 × açık hatırlama ifadesi`, en çok .7; confidence .5, kalibre edilmiş olasılık değildir. Model kimliği, prompt sürümü, işlem kimliği ve kaynaklar tutulur. Aynı işlem cache'den dönse de silinen/expired çıktı başarılıymış gibi dönmez. Provider adapter'ı async iptal sözleşmesine uymalı; çalışan süreçte bloklayıcı SDK çağrısı yapmamalıdır.

## HTTP

Üretimde body'deki tenant/user alanları reddedilir. `BearerAuthenticator` geçerli tokenı sunucu tarafındaki `Scope` ile eşler. Daha büyük kurulumda doğrulanmış OIDC/JWT kimliği veren bir authenticator enjekte edin.

```bash
# chmod 600 ile korunan tokens.json dosyasını uygulama dışında hazırlayın:
# {"rastgele-uzun-token":{"tenant_id":"demo","user_id":"learner"}}
MEMORY_TOKEN_FILE=/private/path/tokens.json MEMORY_DB=data/memory.db \
  uvicorn memory_engine.api:app_from_env --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Yerel geliştirme için açıkça `MEMORY_DEVELOPMENT=1` ayarlanabilir; bu mod `X-Dev-Tenant` ve `X-Dev-User` başlıklarını kabul eder. Paylaşılan/üretim ortamında kullanılmaz. Örnek istek:

```bash
curl -H "Authorization: Bearer $MEMORY_CLIENT_TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"AWS IAM","top_k":3}' http://127.0.0.1:8000/v1/memories/search
```

Endpoint'ler: `POST /v1/memories`, `POST /v1/memories/search`, `PATCH /v1/memories/{id}`, `DELETE /v1/memories/{id}`, `DELETE /v1/users/me/memories`, `GET /health`. PATCH gövdesi `{"expected_version":1,"changes":{"content":"yeni"}}`.

Hatalar sabit `error.code` ve sunucunun ürettiği `request_id` taşır: 401 kimlik, 404 kapsam dışı/yok, 409 sürüm/idempotency, 413 gövde, 422 doğrulama, 429 kota/hız/concurrency, 503 depolama erişimi. Gövde 64 KiB, concurrency 16, arama 120/dakika. Concurrency sınırı süreç başına globaldir; arama hız penceresi ise bearer token (yoksa istemci konağı) başına ayrı tutulur, böylece kimliksiz veya tek bir çağıran diğerlerinin arama kotasını tüketemez. Çok worker için gateway seviyesinde ortak limit gerekir.

Log yalnızca request_id, durum ve süre içerir. URL, içerik, token, kimlik ve exception metni loglanmaz. `app.state.metrics` istek/hata sayısı, toplam süre ve sabit histogram bucket'larını sunar; kimlik etiketi yoktur. Uvicorn access log kapalı çalıştırılmalıdır.

## Değerlendirme

Sürümlü sentetik Türkçe fixture: 15 kayıt, 8 sorgu, yöntem başına 400 ölçüm. Pozitif, alakasız, başka kullanıcı/tenant, çalışma oturumu, expired, deleted ve superseded senaryoları içerir. Sonuçlar: [results-v1.json](evaluations/results-v1.json).

| Yöntem | Precision@3 | Pozitif recall@3 | Alakasız sorguda yanlış hatırlama |
|---|---:|---:|---:|
| Lexical | .2917 | 1.0000 | .0000 |
| Hybrid + fake embedder | .2917 | 1.0000 | .6667 |
| En yeni önce baseline | .1250 | .3333 | 1.0000 |

Precision paydası her sorguda sabit 3'tür; tek ilgili kayıt olan sorguların tavanı 1/3'tür. Tüm yöntemlerde ölçülen scope ve lifecycle ihlali sıfırdır; bu genel güvenlik kanıtı değildir. Baseline aynı filtreleri kullanır. Gecikme ortamı, yöntem ve p50/p95 JSON'dadır; üretim yük testi sayılmaz.

İki sentetik çıkarım örneğinde desteklenen çıktı kabul edildi, uydurma çıktı reddedildi. Bu oranlar canlı LLM veya insan değerlendirmesi değildir. Canlı kalite çalışmasında iki bağımsız gözlemci kaynak/çıktı eşlerini desteklenmiş, uydurma, atlanmış olarak işaretlemeli; uyuşmazlıkları kaydetmeli, Türkçe/çelişki/injection örneklerini ayrı raporlamalıdır.

Bakım, yedek, silme sınırları, migration ve Docker adımları: [runbook](docs/runbook.md). Tasarımı açıklayan sorular: [öğrenme rehberi](docs/learning-guide.md).
