# Tasarımı açıklamak

1. **Katmanlar neden ayrı?** Working mevcut görevde ne kaldığını tutar ve session/task ile yalıtılır. Episodic önceki olay ve sonuçları kaynak ve olay zamanıyla saklar. Semantic tekrar kullanılabilir tercih/bilgidir; doğrulama ve çelişki politikası gerekir.
2. **Neden her mesaj saklanmaz?** Kontrolsüz saklama maliyet, ilgisiz arama, yanlış bilgi ve silme yükü oluşturur. Açık kayıt ve kontrollü özet daha denetlenebilirdir; gizli düşünce zinciri saklanmaz.
3. **Üç puan neden ayrı?** Importance kalıcı önemi, relevance bu sorguyla eşleşmeyi, confidence kaynağa ilişkin değerlendirmeyi belirtir. Confidence doğruluk olasılığı değildir; yüksek önem ilgisiz sonucu geri getirmez.
4. **Çelişkide hangisi kazanır?** Açık yetkili düzeltme eski fact_key değerini superseded yapabilir. Belge/LLM aday bilgisi doğrulanmış bilgiyi sessizce değiştiremez. Modelin yüksek güven puanı yetki vermez.
5. **TTL, eviction, silme farkı?** TTL kullanım süresini bitirir; cleanup beklenmeden retrieval dışına çıkarır. Eviction kota baskısındaki isteğe bağlı politikadır. Kullanıcı silmesi açık yaşam döngüsü işlemidir; türevleri ve cache'i de kaldırır.
6. **Başka kullanıcının verisi nasıl dışlanır?** Scope kimlikten gelir; SQL aday üretiminden önce tenant/user filtresini uygular. Working için session/task da gerekir. Vector search filtreden geçmiş adayların vektörlerini okur. Testlerde sıfır ihlal genel güvenlik ispatı değildir.
7. **Assembler sınırı nerede?** Engine neden ilgili olduğunu göstererek aday sunar. Assembler son token bütçesini ve seçimi yönetir. Hafıza required sistem talimatına dönüşmez; iki aşamanın seçimleri ayrı raporlanır.
8. **Embedding neyi çözer?** Gerçek bir model lexical eşleşmeyen anlam yakınlığını yakalayabilir; yanlış yakınlık, model drift'i veya hatalı bilgi sorununu çözmez. Buradaki hash fake modeli kalite modeli değildir ve sentetik testte daha fazla yanlış pozitif üretti.
9. **Çıkarım ne zaman kalıcı olur?** Açık etkinleştirme, geçerli kaynak, sıkı şema, sınırlı çağrı ve transaction sonrası episodic özet kaydedilebilir. Semantic sonuç önce candidate olur; yetkili insan/uygulama doğrulaması olmadan doğrulanmış gerçeğe dönüşmez. Kaynak silinirse türev yaşamaya devam etmez.

Portföy için ölçülü ifade: “Üç katmanlı kalıcı agent hafızası geliştirdim; yalıtım, çelişki, TTL ve silme politikalarını test ettim. Gerçek Dynamic Context Assembler ile yerel entegrasyonu ve sentetik retrieval değerlendirmesini çalıştırdım. Docker çalışma doğrulaması ve canlı sağlayıcı kalite ölçümleri henüz yapılmadı.”
