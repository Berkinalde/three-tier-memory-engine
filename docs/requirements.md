# 3-Tier Memory Engine

> Proje rehberi ve OpenCode uygulama belgesi. Python ile çalışan, kalıcı, kullanıcılar arasında yalıtılmış ve Dynamic Context Assembler ile bütünleşen bir agent hafızası geliştir.

## 1. Amaç

Bir agent'ın mevcut görevini takip etmesini, önceki oturumların sonuçlarını hatırlamasını ve kalıcı bilgileri gerektiğinde geri getirmesini sağlamak. Her mesajı sonsuza kadar saklamak yerine kontrollü kayıt, güncelleme, arama ve silme mekanizmaları kurmak.

Bu proje AI Application / Agent Engineering portföyünün ikinci bileşeni olacak. Önceki Dynamic Context Assembler'ın gerçek arayüzünü inceleyerek bütünleşmeli; onun API'sini bu belgeden tahmin etmemeli.

**Sorumluluk ayrımı:** Memory engine aday bilgileri getirir ve neden getirildiğini açıklar. Context Assembler bu adaylardan hangilerinin model isteğinin token bütçesine gireceğini belirler. Memory engine tek başına modelin doğru hatırlayacağını veya doğru cevap vereceğini garanti etmez.

## 2. Üç hafıza katmanı

### Working memory — mevcut işin durumu

Oturuma ve göreve özgü kısa ömürlü bilgiler: görev hedefi, tamamlanan adımlar, bekleyen işler ve doğrulanmış ara sonuçlar.

Örnek: “Üç belgeden ikisi incelendi; üçüncü belge bekliyor.”

Serbest biçimli gizli düşünce zincirini kaydetme. Saklanan veriler açık görev durumu, kısa karar özeti ve araçların gözlenebilir sonuçları olsun. Kaydın süresi dolabilir; oturum sona erdiğinde açık politika ile temizlenebilir.

### Episodic memory — önceki olay ve sonuçlar

Bir oturumda ne yapıldığını, hangi kararın verildiğini ve sonucun ne olduğunu kaynaklarıyla saklar.

Örnek: “2026-10-19 oturumunda kullanıcı IAM alıştırmalarında policy evaluation konusunu tekrar etmek istedi.”

Olayın gerçekleştiği zaman ile kaydın sisteme yazıldığı zaman ayrı tutulur. Oturum özeti, ham konuşmanın tamamı değildir; kaynak mesaj veya olay kimliklerine bağlanır.

### Semantic memory — yeniden kullanılabilir bilgiler

Tercihler, doğrulanmış bilgiler ve kalıcı ilişkilerdir.

Örnek: “Kullanıcı teknik açıklamaları Türkçe ve örnekli tercih ediyor.”

Bilgi kaynağı, doğrulanma durumu ve güncelliği görünür olmalı. Bir metnin embedding'inin bulunması onu doğru veya güvenilir yapmaz. Semantic memory için ilk sürümde vector database gerekmez.

## 3. Örnek uçtan uca kullanım

1. Kullanıcı “Geçen çalışmada kaldığımız AWS konusundan devam edelim” der.
2. Engine yalnızca ilgili kullanıcının erişilebilir kayıtlarını arar.
3. Son oturumun IAM özeti episodic memory'den; dil tercihi semantic memory'den gelir.
4. Yeni görev durumu working memory'ye yazılır.
5. Aday kayıtlar kaynak kimlikleri ve ilgililik puanlarıyla Context Assembler'a aktarılır.
6. Assembler token bütçesine sığan kayıtları seçer.
7. Görev tamamlanınca olay özeti kaydedilir. Yeni kalıcı bilgi varsa ayrı bir doğrulama politikasıyla semantic memory'ye alınır.

## 4. Temel teknik kararlar

Bu taslağın varsayılanları Python 3.11+, SQLite ve önce ağsız geliştirmedir. Bunlar uygulamayı küçük tutmak için seçildi; mevcut repo farklı ama uyumlu araçlar kullanıyorsa ona uy.

- V1: bağımsız kütüphane, SQLite, CLI, kurallı kayıt ve lexical arama.
- V2: Context Assembler adaptörü ve uçtan uca demo.
- V3: embedding adaptörü ve lexical/vector hybrid retrieval.
- V4: kontrollü LLM ile bilgi çıkarımı ve oturum özeti.
- V5: FastAPI, operasyon hazırlıkları ve bütünleşik değerlendirme.

Mevcut projeye uygun değilse yeni framework ekleme. İlk sürüm için LangGraph, Redis veya harici vector database zorunlu değildir. Sağlayıcı SDK'sı, model kimliği veya güncel servis özelliği gerektiğinde uygulama sırasında resmi belgeleri doğrula.

## 5. Veri sözleşmesi

Her kayıt en az şu alanları taşısın:

- `id`: değişmez benzersiz kimlik.
- `tenant_id`, `user_id`: zorunlu sahiplik kapsamı.
- `tier`: working, episodic veya semantic.
- `session_id`, `task_id`: working için zorunlu; diğerlerinde kaynak varsa tutulur.
- `content`: açıkça kaydedilen bilgi veya kısa özet.
- `source_refs`: kaynak olay/mesaj kimlikleri; kaynağı olmayan otomatik çıkarımı doğrulanmış bilgi gibi saklama.
- `created_at`, `updated_at`, `occurred_at`, `expires_at`: UTC ve zaman dilimi bilgili zamanlar; occurred_at bilinmiyorsa boş olabilir.
- `importance`: 0–1; retrieval sıralamasında kullanılır.
- `confidence`: 0–1; importance'tan ayrıdır ve olasılıksal doğruluk garantisi değildir.
- `status`: active, candidate veya superseded.
- `version`: eşzamanlı güncelleme kontrolü.
- `metadata`: sınırlı boyutta JSON; secret veya sınırsız serbest içerik deposu değildir.

Semantic kayıtlar ayrıca `fact_key`, `verification_status` ve gerekiyorsa `supersedes_id` taşır. Tercih gibi tek değerli alanlarda fact_key kullan; aynı konuya ait bağımsız gerçekleri yanlışlıkla tek kayda birleştirme.

Embedding alanları V3'te ayrı depolanır: embedding model kimliği, sürümü, boyutu, içerik hash'i ve vektör. Vektörün hangi kullanıcıya ait olduğu kaydın sahipliğiyle aynı kalır.

Geçersiz puanları, NaN/sonsuzu, süresi dolmuş yeni kayıtları, yanlış zaman sırasını, boş kapsamı ve boyut sınırını aşan içeriği açık hata kodlarıyla reddet. Saat sağlayıcısı testlerde enjekte edilebilsin.

## 6. Yazma, güncelleme ve çelişki politikası

### V1'de kayıt

Kayıtlar açık API/CLI işlemleriyle yazılır; her konuşma otomatik hafızaya alınmaz. Importance varsayılanı 0.5'tir ve kullanıcı/çağıran sistem tarafından verilir. Otomatik puanlama sonraki sürümdedir.

`idempotency_key` kullanarak aynı olayın tekrar kaydedilmesini önle. Anahtar tenant/user kapsamındadır; aynı anahtar farklı payload ile kullanılırsa conflict hatası ver. Hafif normalize edilmiş metin hash'ini yardımcı deduplication için kullanabilirsin; anlam benzerliğini eşitlik sayma. Ayrı zamanlarda gerçekleşmiş aynı metinli olayları otomatik tekilleştirme.

### Güncelleme

Version kontrollü güncelleme yap. Eski sürümle yazma girişimine conflict dön. Mevcut aktif kaydı değiştirme ve yeni sürümü oluşturma işlemleri tek transaction içinde olmalı.

### Çelişki

- Kullanıcının açık düzeltmesi gibi yetkili bir güncelleme, aynı fact_key'in eski değerini superseded yapabilir.
- Bir belgeden veya LLM'den çıkarılan çelişkili bilgi candidate olur; doğrulanmış kaydı sessizce değiştiremez.
- Candidate ve superseded kayıtlar normal retrieval'a girmez; inceleme işlemleriyle ayrı görülebilir.
- Güven düzeyi yüksek olmak tek başına yetkili kaynak olmak anlamına gelmez.

## 7. Retrieval politikası

`retrieve(scope, query, session_id, task_id, top_k, tier_filters)` yapılandırılmış sonuçlar dönsün.

İlk önce tenant/user, status ve expiry filtrelerini uygula. Working kayıtlarında session/task kapsamını da zorunlu tut. Kapsam filtresini aramadan sonra uygulama: başka kullanıcının kaydı aday listesine bile girmemeli.

V1 için küçük veri kümelerinde deterministik lexical eşleşme yeterli. Türkçe ve Unicode normalizasyonunu belgeleyerek uygula; gerçek dilsel anlama iddiasında bulunma. Boş sorguda yalnızca açıkça seçilmiş güncel working kayıtları getir; bütün geçmişi döndürme.

Varsayılan sıralama:

```text
score = 0.60 * relevance + 0.25 * recency + 0.15 * importance
recency = 2 ** (-age_days / half_life_days)
```

Başlangıç half-life değerleri working 1 gün, episodic 30 gün, semantic 180 gündür; yapılandırılabilir sezgisel tercihlerdir. Relevance 0–1 normalize lexical skordur. Working için güncellikte updated_at; episodic için occurred_at varsa o, yoksa created_at; semantic için son doğrulama zamanı varsa o, yoksa created_at kullan. Salt okunma işlemi güncellik skorunu yükseltmesin.

İlgisiz ama yeni bir kayıt sırf toplam skoru yüzünden seçilmesin: query aramasında önce yapılandırılabilir minimum relevance filtresi uygula. Eşit skorda id sırası kullan. Top_k, sorgu boyutu ve taranan aday sayısı üst sınırları olsun.

Her sonuç: kayıt kimliği, tier, içerik, kaynaklar, relevance, recency, importance, final_score ve neden seçildiği bilgisini taşısın. Relevance ile final_score'u ayır; Assembler'a aktarılacak alanın anlamını açıkça belgeleyin.

## 8. Süre dolumu, kapasite ve unutma

- Working için varsayılan TTL 24 saat, episodic için 90 gün; semantic için varsayılan otomatik expiry yoktur. Hepsi yapılandırılabilir başlangıç politikalarıdır.
- Süresi dolan kayıtlar temizlik işi henüz çalışmasa bile retrieval'dan çıkarılır.
- Kullanıcı/tier başına kayıt ve byte kotası belirle; varsayılanları README'de açıkça kaydet.
- Kota dolduğunda önce expired kayıtları temizle. Sonra isteğe bağlı, doğrulanmamış ve düşük importance'lı kayıtları oldest-first eşitlik çözümüyle çıkar.
- Doğrulanmış semantic kayıtları sessizce evict etme; alan yetmezse açık quota hatası ver.
- Ekleme ve eviction atomik olsun; başarısız ekleme mevcut veriyi gereksiz silmesin.
- `delete_memory` ve `delete_user_data` içerik, ilişkili sürümler, embedding ve özet cache'lerini birlikte silsin. İçeriksiz denetim kaydı tutulacaksa politikası açık olsun.
- SQLite ve yedeklerde fiziksel veri kalıntıları olabilir. Mantıksal silmeyi tüm yedeklerden anında kriptografik silme gibi sunma; bakım/yedek politikası belgelenmeli.

## 9. Dynamic Context Assembler entegrasyonu

Önce önceki projenin gerçek modellerini ve CLI/API sözleşmesini incele. Ayrı adapter modülü oluştur; memory çekirdeğini Assembler'a bağımlı yapma.

- Memory kimliğini ve source_refs'i son çıktıya kadar koru.
- Sonuçları isteğe bağlı bağlam birimleri olarak aktar; hatırlanan bilgi otomatik required sistem talimatına dönüşmesin.
- Önceki assembler yalnızca working_memory alanı sunuyorsa üç tier'ı burada metadata ile temsil et veya uyumlu bir adapter kullan; bu alan adının storage tier anlamına gelmediğini açıkla.
- Bellek adayları için item ve byte limiti uygula; nihai token kararını Assembler versin.
- Engine'in getirdiği, Assembler'ın seçtiği ve bütçe nedeniyle çıkardığı kayıtları ayrı raporla.
- Repo mevcut değilse gerçek sözleşmeye dayandığını iddia etme. Küçük bir mock interface ile adapter contract testini hazırla ve gerçek entegrasyonu bekliyor işaretle.

Demo: oturum A'da tercih ve sonuç kaydet; süreci yeniden başlat; oturum B'de episodic/semantic bilgiyi getir; A'nın working state'ini B'ye taşıma; küçük context bütçesinde seçimi göster; bilgiyi silip retrieval'da artık bulunmadığını doğrula.

## 10. Sürümler ve tamamlanma koşulları

### V1 — SQLite çekirdeği ve CLI

Teslim: türlenmiş modeller, migration'lar, repository/service ayrımı, write/update/retrieve/expire/delete işlemleri ve JSON CLI. SQL parametreli olmalı. SQLite bağlantı ve transaction yönetimi thread/concurrency davranışıyla belgelenmeli.

Tamamlanma: veri yeniden başlatmada korunur; scope, expiry, version, idempotency, conflict ve quota testleri geçer. API anahtarı veya ağ gerektirmez.

### V2 — Assembler adaptörü

Teslim: yukarıdaki adapter, source mapping, uçtan uca demo ve engine/assembler raporları.

Tamamlanma: gerçek Assembler mevcutsa onunla test edilmiş; değilse mock sözleşme ile sınırları açıkça belirtilmiş olmalı. Başarılı birleşik çıktı Assembler'ın sayacına göre token bütçesine sığmalı.

### V3 — Embedding ve hybrid retrieval

Teslim: sağlayıcıdan bağımsız embedder arayüzü, offline fake embedder, isteğe bağlı gerçek adaptör ve küçük veri kümesi için brute-force cosine search. Harici vector DB ancak ölçülen ihtiyaç varsa eklenir.

Lexical/vector sonuçlarını ayrı sıralayıp Reciprocal Rank Fusion gibi açık ve deterministik bir yöntemle birleştir. V1 skoruna geçişte fused relevance'ın normalizasyonunu belgeleyerek uygula; iki farklı skor ölçeğini doğrudan toplama. Embedding boyutu/modeli farklı vektörleri karşılaştırma. İçerik/model değişince yeniden indeksleme gereksinimini kaydet. Silme cache ve vektörü de kapsasın.

Tamamlanma: filtreler vector aday üretiminden önce uygulanır; sıfır vektör ve uyumsuz boyut güvenli hata verir; model değişimi ve silme testleri geçer. Gerçek model yoksa kalite artışı iddia edilmez.

### V4 — Otomatik özet ve bilgi çıkarımı

Teslim: açıkça etkinleştirilen oturum özeti ve semantic candidate çıkarımı. Kaynak metin güvenilmeyen veri kabul edilir. Kaynak kimlikleri, model/prompt sürümü ve işlem kimliği tutulur.

LLM çıktısı şema doğrulamasından geçer; kaynakta olmayan iddia otomatik doğrulanmış kayıt olmaz. Kaynakta geçen API anahtarı veya parola gibi secret'ları kalıcı hafızaya alma. Bu kontrolün eksiksiz DLP garantisi olmadığını belirt. Model kendi çıktısıyla doğrulanmış kayıtları silemez veya değiştiremez.

Importance için kurallı bir başlangıç yöntemi kullan: açık saklama isteği ve doğrulanmış tercih gibi sinyaller; formülü belgeleyip sınırla. LLM'nin verdiği importance/confidence değerlerini kalibre edilmiş olasılık sayma.

İş başına en fazla 1 sağlayıcı çağrısı varsayılanı, input/output token sınırı ve timeout uygula; hata durumunda mevcut kayıtları koru. Büyük oturumu sessizce kesmek yerine açıkça atla veya sonlu parça politikasıyla işle. Tekrar işleme idempotent olmalı. Özet, kaynaklar silindiğinde geçersizleşmeli; aktif retrieval'a kaynakları silinmiş türevler dönmemeli.

Tamamlanma: tüm akışlar mock ile çalışır. Gerçek çağrı ancak ortamda anahtar ve açık etkinleştirme varsa yapılır. Bilgi atlama, uydurma, çelişki ve Türkçe örnekleri için canlı kalite ölçümleri ayrıca raporlanır.

### V5 — FastAPI ve operasyon

Teslim edilecek örnek HTTP işlemleri:

- `POST /v1/memories`: kayıt oluştur.
- `POST /v1/memories/search`: scope içinde ara.
- `PATCH /v1/memories/{id}`: version kontrollü güncelle.
- `DELETE /v1/memories/{id}`: kayıt ve türevlerini sil.
- `DELETE /v1/users/me/memories`: doğrulanmış kullanıcının bütün hafızasını sil.
- `GET /health`: içeriksiz sağlık bilgisi.

Tenant/user kapsamını body'ye güvenerek belirleme; doğrulanmış kimlikten türet. Yerel test kimliği yalnızca geliştirme modunda açıkça etkinleşsin. Başka kullanıcıya ait kimlikle işlemde veri varlığını sızdırmayan tutarlı 404 dön. Input hataları 422, version/idempotency çelişkisi 409, büyük gövde 413, kota/hız sınırı 429; hata gövdesinde sabit kod ve request_id olsun.

İstek gövdesi, arama sayısı ve concurrency sınırları; içeriksiz yapılandırılmış loglar; süre ve hata metrikleri; Docker ve offline CI ekle. Kimlikleri yüksek cardinality metrik etiketlerine koyma. Secret ve hafıza içeriği varsayılan loglara girmesin. Bulut yayını bu belge kapsamında otomatik yapılmaz; yerel çalışma ve deployment runbook'u hazırlanır.

Tamamlanma: kimlik yalıtımı HTTP seviyesinde test edilir; container sağlık kontrolü geçer; testler varsayılan olarak ağsız çalışır.

## 11. Gerekli testler

1. Üç tier için kayıt, okuma ve süreç yeniden başlatma sonrası kalıcılık.
2. Aynı kimlik/metin/sorgu olsa bile tenant ve user yalıtımı; working için session/task yalıtımı.
3. Tam expiry sınırı, fake clock ve temizlik öncesinde bile expired kaydın görünmemesi.
4. Aynı idempotency anahtarında aynı payload'ın tekrarsız sonucu; farklı payload'ın conflict üretmesi.
5. Version yarışında tek güncellemenin kazanması; transaction rollback.
6. Yetkili düzeltme ile supersede; LLM/belge adayının doğrulanmış bilgiyi değiştirememesi.
7. Deterministik lexical sıralama, Türkçe/Unicode, boş sorgu ve eşit skorlar.
8. İlgisiz yüksek importance kaydının relevance eşiğiyle dışarıda kalması.
9. Kota, eviction sırası ve doğrulanmış bilgiyi koruyan hata yolu.
10. Tek kayıt/tüm kullanıcı silmesinde sürüm, özet, cache ve embedding temizliği; kullanıcılar arası etkisizlik.
11. Assembler kaynak kimlikleri, token bütçesi ve çıkarma nedenleri.
12. Embedding model/boyut uyumsuzluğu ve sağlayıcı hata yolları.
13. Otomatik çıkarımda invalid JSON, uydurma iddia, prompt injection metni ve timeout.
14. HTTP kimlik doğrulama, kapsam kontrolü, hata kodları ve içerik sızdırmayan loglar.

Sabit seed ile rastgele küçük veri kümelerinde temel invariant'ları da doğrula: dönen her kayıt izinli scope içindedir, active ve süresi geçmemiştir; silinen kayıt/türev dönmez; top_k aşılmaz. Testler gerçek kullanıcı verisi kullanmasın.

## 12. Değerlendirme ve portföy kanıtı

Sürümlenmiş sentetik oturumlar ve beklenen hafıza kimlikleriyle bir evaluation set hazırla. Pozitif sorular yanında alakasız, çelişkili, eski ve başka kullanıcıya ait kayıt senaryoları bulunsun.

- Retrieval: precision@k ve recall@k; ilgisiz sorgularda yanlış hatırlama oranı.
- Isolation: erişim ihlali sayısı; test kümesinde sıfır beklenir, genel güvenlik kanıtı sayılmaz.
- Lifecycle: expired/superseded/deleted kayıt dönme sayısı.
- Entegrasyon: Assembler'ın seçtiği ilgili kayıtlar ve token kullanımı.
- Performans: veri kümesi boyutu, ortam, tekrar sayısı ve yöntemle birlikte p50/p95 retrieval süresi.
- V3 sonrası: aynı veri kümesinde lexical ve hybrid karşılaştırması.
- V4 sonrası: desteklenen/uydurulmuş/atlanmış bilgi oranları; insan incelemesi yöntemiyle birlikte.

Ölçülmeyen kalite artışı yazma. Sentetik fixture başarısını üretim performansı gibi sunma. Baseline olarak aynı scope/expiry kurallarını kullanan en-yeni-önce yaklaşımı kullan; güvenlik kurallarını baseline'dan çıkararak avantaj yaratma.

## 13. Önerilen dosya yapısı

```text
src/memory_engine/
  models.py
  repository.py
  service.py
  retrieval.py
  policies.py
  migrations/
  adapters/
    context_assembler.py
    embeddings.py
    extraction.py
  cli.py
  api.py
tests/
examples/
evaluations/
README.md
pyproject.toml
```

Bu yapı öneridir; mevcut projenin düzeni önceliklidir. V1'de kullanılmayan sonraki sürüm modüllerini boş dosyalarla doldurma.

## 14. OpenCode'a uygulama talimatı

Bu belgedeki sürümleri sırasıyla uygula. Önce mevcut çalışma alanını ve AGENTS.md dosyalarını incele; kaynak/referans dosyalarını değiştirme. Mevcut kullanıcının değişikliklerini koru. Önceki Assembler projesi varsa sözleşmesini okuyup reuse et.

Her aşamada kısa uygulama planı çıkar, anlamlı testlerle davranışı doğrula ve ardından sonraki aşamaya geç. Her sürümün sonunda kullanıcıya neyi öğrendiğini ve hangi tasarım kararını neden verdiğini kısa Türkçe açıklamayla bildir. Kod adları İngilizce, README ve açıklamalar Türkçe olsun.

Önce ağsız çalışan V1'i bitir; daha sonra V2–V5'e geç. Gerçek hesap/anahtar gerektiren bir iş engelliyse mock ile yapılabilen bağımsız işleri tamamla ve canlı doğrulamayı açıkça beklemede tut. Ücretli servis açma veya yayınlama yapma. Gerektiğinde SDK/model davranışını güncel resmi kaynaklardan doğrula.

README'de kurulum, örnek CLI/API kullanımı, test komutları, SQLite migration/backup politikası, veri saklama/silme, güvenlik sınırları ve tasarım kararları bulunsun. Her sürümün durumunu tamamlandı/kısmen tamamlandı/bekliyor olarak kanıtıyla göster.

Son teslimde gerçekten çalıştırılan testleri ve evaluation sonuçlarını belirt. Canlı sağlayıcı testi yapılmadıysa belirt; test sonucu uydurma. Projenin tamamlanması, yerel bütünleşik akışın çalışması ve V1–V5 teslimatlarının doğrulanmasıdır; eksik canlı doğrulamayı veya bulut yayınını tamamlanmış sayma.

## 15. Bu projeyi bitirdiğinde açıklayabilmelisin

- Working, episodic ve semantic memory hangi farklı ihtiyaçları karşılar?
- Neden bütün konuşmaları otomatik kaydetmiyoruz?
- Importance, relevance ve confidence neden ayrı alanlar?
- Yeni bir bilgi eskisiyle çelişirse hangisine güveniyoruz?
- TTL, eviction ve kullanıcının silme isteği nasıl ayrışıyor?
- Başka kullanıcının verisi retrieval'a nasıl giremiyor?
- Memory engine ile Context Assembler'ın sorumluluk sınırı nerede?
- Embedding araması hangi hataları çözüyor, hangilerini çözmüyor?
- Bir özet veya çıkarılmış bilgi ne zaman kalıcı hafızaya alınabilir?

Portföy hikâyesi: “Üç katmanlı kalıcı agent hafızası geliştirdim; kapsam yalıtımı, çelişki yönetimi, süre dolumu ve silme politikalarını test ettim. Hafıza retrieval'ını token bütçeli context assembly ile bütünleştirdim ve sonuçları sürümlenmiş bir veri kümesinde ölçtüm.” Bu cümleyi ancak ilgili aşamalar gerçekten tamamlandığında kullan.
