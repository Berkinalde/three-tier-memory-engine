# Doğrulama kaydı — 19 Ekim 2026

## Çalıştırılan kontroller

- `../dynamic-context-assembler/.venv/bin/python -m pytest -q`: **76 passed in 2.63s**. Python 3.13. Varsayılan testlerde internet socket bağlantıları engelli.
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

## Bekleyen doğrulamalar

- **Docker container:** ilk sandbox erişimi reddedildi; sandbox dışında izinli iki Docker kontrolü de 15 saniyede timeout oldu. Container build, HEALTHCHECK ve container restart smoke **çalıştırılamadı**. Dockerfile ve `scripts/container_smoke.py` hazır; V5 bu nedenle kısmen tamamlandı.
- **Uzak CI:** workflow hazır fakat push/remote run yapılmadı; yeşil CI iddiası yok.
- **Canlı sağlayıcı:** gerçek embedding/LLM adaptörü, hesap/anahtar veya ücretli servis açılmadı. İnterface ve offline fake/mock akışlar doğrulandı.
- **Bulut yayını:** yapılmadı; bu kapsamda otomatik yayın yok.

Ayrı proje klasörü kullanıldı; mevcut assembler kaynakları, Desktop rehberi ve `sources/` dosyaları değiştirilmedi. Üst dizindeki ilgisiz Git deposuna commit/push yapılmadı.
