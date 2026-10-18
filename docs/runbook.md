# Yerel çalıştırma ve operasyon

## SQLite

Her işlem kendi bağlantısını açar; bağlantı başka threade taşınmaz. Okuma snapshot transaction, yazma `BEGIN IMMEDIATE` kullanır. WAL açık; writer'lar süreçler arasında serileşir. Busy timeout 5 saniyedir. HTTP depolama erişim hatalarını içerik vermeden 503'e çevirir. Yerel dosya sistemi kullanın; SQLite WAL dosyasını paylaşımlı ağ diskine taşımayın.

`PRAGMA user_version` migration sürümüdür. `001.sql` temel tabloları, `002.sql` çıkarım çıktısı bağıntılarını kurar ve mevcut JSON sonuçlarından bunları doldurur. Migration transaction içinde çalışır; desteklenenden yeni şema reddedilir. Downgrade otomatik değildir. Yükseltmeden önce SQLite backup API ile yedek alın; yalnızca `.db` dosyasını WAL yazılırken kopyalamayın.

```python
import sqlite3
with sqlite3.connect('data/memory.db') as source:
    with sqlite3.connect('backups/memory-before-upgrade.db') as destination:
        source.backup(destination)
```

Yedeği ayrı geçici dosyaya geri yükleyin, `PRAGMA integrity_check` ve schema sürümünü doğrulayın; kontrollü kesintide uygulamanın dosyasını değiştirin. Gerçek kullanıcı verisiyle test yapmayın. Dosya ve yedekleri yalnızca servis hesabı okuyabilsin; disk şifrelemesini işletim sistemi seviyesinde yönetin.

## Saklama ve silme

Expiry retrieval'da anında uygulanır. Fiziksel cleanup için güvenilir operatör kapsam bazlı `memory-engine ... expire` çalıştırır. Otomatik cron kurulmadı. TTL ve kota varsayılanları README'dedir.

Silme transaction içinde içerik, sürümler, embedding, türev kayıtlar ve işlem cache'lerini temizler. `secure_delete=ON` etkindir; bu, WAL, dosya sistemi snapshot'ları veya eski yedeklerden kriptografik silme garantisi değildir. Yedek tutma süresini işletmeci belirlemeli; silme talepleri yedek rotasyonuna dahil edilmeli ve eski yedeğin geri yüklenmesi sonrasında silme listesi tekrar uygulanmalıdır. Güncel DB üzerinde bakım penceresinde `PRAGMA wal_checkpoint(TRUNCATE)` ve gerekiyorsa `VACUUM` uygulanabilir; aktif bağlantılar varken sonuç kontrol edilmelidir.

Idempotency ve extraction operation kayıtları ilgili kaynak/çıktı yaşam döngüsüne bağlıdır. İşlem sırasında süreç çökerse `pending:<attempt-id>` kalabilir. İlgili worker'ın kesin durduğunu doğrulamadan claim silmeyin. Kesin durduktan sonra yalnızca belirtilen tenant/user/operation_id için pending kaydını transaction içinde temizleyip aynı işi yeniden deneyin; operasyon sorgularında içerik yazdırmayın. Aktif işlemden claim çalmaya yönelik otomatik zaman aşımı uygulanmaz.

## HTTP dağıtımı

`MEMORY_TOKEN_FILE` okunabilen JSON token-scope eşlemesi sağlar. Token dosyası image içine eklenmez, volume/secret mount ile salt okunur bağlanır. Servis `/data` üzerinde yazabilir olmalıdır. Prod mod kimlik sağlayıcısız açılmaz. TLS sonlandırma ve dış rate limit reverse proxy/gateway'in sorumluluğudur; yerel demo 127.0.0.1'e bağlanır.

Docker (burada motor yanıtsız olduğu için çalıştırılarak doğrulanamadı):

```bash
docker build -t memory-engine:local .
python scripts/container_smoke.py --image memory-engine:local
# Üretim benzeri yerel kullanım: development modu kapalı
docker run --rm -p 127.0.0.1:8000:8000 \
  -v memory-data:/data \
  -v /absolute/private/tokens.json:/run/secrets/tokens.json:ro \
  -e MEMORY_TOKEN_FILE=/run/secrets/tokens.json memory-engine:local
```

Smoke script yalnızca oluşturduğu geçici container ve volume'u siler; development modunda sentetik kayıt yazıp container'ı yeniden başlatır ve HEALTHCHECK sonucunu bekler. Normal image UID 10001 ile çalışır. `MEMORY_DEVELOPMENT=1` yalnızca bu izole smoke/geliştirme bağlamında kullanılmalıdır.

Varsayılan Docker build bağımlılıkları indirmek için ağ ister. Kapalı ortamda aynı kilit sürümleri için wheelhouse hazırlayıp `pip --no-index --find-links` ile build prosedürü uyarlanabilir. Test çalışma aşaması dış sağlayıcı çağırmaz. GitHub workflow dosyası hazırdır, ancak repo publish edilmediği için uzak CI çalışması yoktur.

## Resmî arayüz başvuruları

HTTP exception ve middleware tercihleri 19 Ekim 2026 tarihinde [FastAPI hata işleme](https://fastapi.tiangolo.com/tutorial/handling-errors/) ve [Starlette pure ASGI middleware](https://www.starlette.io/middleware/) belgeleriyle kontrol edildi. Uygulama bu ortamda kurulu FastAPI 0.144.0/Starlette 1.8.0 ile test edildi. Canlı model/SDK eklenmedi.
