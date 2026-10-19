# Doğrulama kaydı — 19 Ekim 2026

## Çalıştırılan kontroller

- `../dynamic-context-assembler/.venv/bin/python -m pytest -q`: **81 passed in 3.55s**. Python 3.13. Varsayılan testlerde internet socket bağlantıları engelli.
- `python -m ruff check src tests examples evaluations scripts`: **All checks passed**.
- `python -m ruff format --check src tests examples evaluations scripts`: **24 files already formatted**.
- `PYTHONPATH=src python3 ...`: Python **3.11.8** ile kayıt/arama/tüm kullanıcı silme smoke geçti.
- `PYTHONPATH=src python scripts/http_smoke.py`: gerçek 127.0.0.1 Uvicorn sunucusunda health ve kimlik doğrulamalı HTTP CRUD geçti. Geçici DB ve süreç kapatıldı.
- `python examples/two_sessions.py`: ayrı writer süreçleri sonlandıktan sonra okuma, A working state'inin B'den dışlanması, gerçek Assembler ile **109/135 token**, bir seçilen/bir bütçeden elenen kayıt ve silme doğrulandı. Çıktı: `evaluations/demo.json`.
- `python evaluations/run.py`: 15 kayıt/8 sorgu, yöntem başına 400 ölçüm; çıktılar `evaluations/results-v1.json` ve `evaluations/evaluation-summary.txt`.
- `pip wheel --no-deps --no-build-isolation --no-index . -w dist`: **three_tier_memory_engine-0.5.0-py3-none-any.whl** başarıyla oluşturuldu. Çekirdek ve iki SQL migration wheel içindedir.

## Son sentetik değerlendirme

| Yöntem | Precision@3 | Pozitif Recall@3 | Alakasız false recall | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| Lexical | .2917 | 1.0000 | .0000 | 1.290 | 1.629 |
| Hybrid fake | .2917 | 1.0000 | .6667 | 1.562 | 2.490 |
| Newest-first | .1250 | .3333 | 1.0000 | 1.285 | 1.694 |

Her yöntemde ölçülen isolation ve lifecycle ihlal sayısı **0**. Sabit precision paydası k=3; pozitif sorguların çoğunda yalnızca bir beklenen kayıt vardır. Gerçek ortam bilgisi JSON içinde; sıcak yerel SQLite ve küçük sentetik veri sonuçları üretim performansını temsil etmez. Hash embedder kalite artışı sağlamış gibi sunulmaz.

V4 oracle: desteklenen 1 çıktı kabul edildi, uydurma 1 çıktı reddedildi; canlı model/bağımsız insan değerlendirmesi yapılmadı. Daha geniş doğrulama testleri çelişki, Türkçe, bozuk JSON, secret, injection ve timeout yollarını kapsar.

## Bağımsız kod incelemesi

Ayrı reviewer dört önemli hata belirledi. Sekiz yeni test önce kırmızı çalıştırıldı; sonra düzeltmelerle yeşile döndü:

1. Büyük integer skor ve unpaired surrogate: HTTP 500 yerine sabit 422; yazma yok.
2. Silinen veya expired çıkarım çıktısı: operation cache eski kimliği döndürmüyor.
3. Kaynak değişimindeki iki çıkarım yarışı: attempt token eski işlemin yeni claim'i silmesini engelliyor.
4. Toplu çıkarım kotası: aynı batch'in önceki çıktısı evict edilmiyor; tüm batch rollback oluyor.

Ek iki kırmızı→yeşil kontrol migration 001→002 sırasında eski cache çıktılarının bağlanmasını ve episodic özetin olay zamanının kaynak zamanından gelmesini doğruladı. İncelemede ertelenen minor bulgu yok.

## İkinci bağımsız inceleme — kritik düzeltmeler

Üç kritik bulgu bağımsız olarak yeniden üretildi, ardından düzeltildi ve regresyon testleriyle korundu:

1. **Sözcüksüz içerik/sorgu** — `!!!` içeren tek kayıt tüm kapsamın `index_scope`'unu `invalid_vector` ile kırıyordu; `???` sorgusu `retrieve`'i hata veriyordu. `HashEmbedder` artık sözcük yoksa ham metinden deterministik sıfır-olmayan vektör üretir (token içeren metinlerin vektörleri aynı kalır), böylece indeksleme ve arama hata vermek yerine çalışır. Test: `test_symbol_only_content_and_query_are_safe`.
2. **Sürüm geçmişi kotası** — byte kotası kümülatif sürüm geçmişini saydığı ve hiç geri kazanılmadığı için sık güncellenen tek bir kayıt kendi sürümleri yüzünden kalıcı olarak `quota_exceeded` veriyordu; eviction bile kurtaramıyordu. Eviction açıkken kota aşımında önce en eski sürüm payload'ları geri kazanılır (canlı kayıt `memories.payload`'da kalır), ardından kayıt tahliyesi uygulanır. Test: `test_version_history_does_not_brick_updates`.
3. **Kimlik öncesi arama kotası** — arama hız penceresi kimlik doğrulamadan önce ve global tüketildiği için kimliksiz bir çağıran geçerli token sahiplerini 429'a düşürebiliyordu. Pencere artık bearer token (yoksa istemci konağı) başına tutulur. Test: `test_search_rate_limit_is_per_principal`.
4. **Döngü hata kodu** — türevler `_link_sources`'tan önce silindiği için gerçek döngü denemesi `source_cycle` yerine `not_found` dönüyordu. Kaynak döngüsü artık türevler silinmeden önce reddedilir. Test: `test_update_cycle_reports_source_cycle`.
5. **Aday sınırı** — `candidates` tarama sınırını aşınca aramayı hata ile kesiyordu. Artık `max_candidates` kadar kayıtla sınırlanır (deterministik id sırası), dolu kapsam aranabilir kalır. Test: `test_candidate_limit_truncates_instead_of_failing`.

Düzeltme sonrası: **81 passed in 3.55s**, `ruff check` ve `ruff format --check` temiz. Üç doküman/entegrasyon notu (middleware istisna loglaması; `hybrid_fake` anlatısı; kardeş projeye sabit test bağlılığı) davranış değiştirilmeden belgelendi. Ayrıntılı kanıt: [inceleme raporu](review-2026-10-19.html).

## Bekleyen doğrulamalar

- **Docker container:** ilk sandbox erişimi reddedildi; sandbox dışında izinli iki Docker kontrolü de 15 saniyede timeout oldu. Container build, HEALTHCHECK ve container restart smoke **çalıştırılamadı**. Dockerfile ve `scripts/container_smoke.py` hazır; V5 bu nedenle kısmen tamamlandı.
- **Uzak CI:** workflow hazır fakat push/remote run yapılmadı; yeşil CI iddiası yok.
- **Canlı sağlayıcı:** gerçek embedding/LLM adaptörü, hesap/anahtar veya ücretli servis açılmadı. İnterface ve offline fake/mock akışlar doğrulandı.
- **Bulut yayını:** yapılmadı; bu kapsamda otomatik yayın yok.

Ayrı proje klasörü kullanıldı; mevcut assembler kaynakları, Desktop rehberi ve `sources/` dosyaları değiştirilmedi. Üst dizindeki ilgisiz Git deposuna commit/push yapılmadı.
