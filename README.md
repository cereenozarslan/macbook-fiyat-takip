# MacBook Fiyat Takip Botu

Belirli bir MacBook modelinin fiyatını dört farklı e-ticaret sitesinden düzenli olarak çeken,
geçmişi veritabanında tutan ve özeti Telegram'a bildiren fiyat takip sistemi.

## Ne yapar

- **4 kaynaktan fiyat toplama** — Apple Türkiye, Vatan Bilgisayar, MediaMarkt ve Trendyol
- **Fiyat geçmişi** — her ölçüm SQLite veritabanına yazılır, zaman içindeki değişim izlenebilir
- **Telegram bildirimi** — güncel fiyat özeti bot üzerinden mesaj olarak gelir
- **Telegram üzerinden sorgulama** (`bot_dinleyici.py`) — bota mesaj atarak anlık durum sorulabilir
- **MCP sunucusu** (`mcp_server.py`) — fiyat verisini bir yapay zeka asistanına araç olarak açar

## Teknolojiler

Python · requests · SQLite · Telegram Bot API · MCP (Model Context Protocol)

## Kurulum

```bash
git clone https://github.com/cereenozarslan/macbook-fiyat-takip.git
cd macbook-fiyat-takip
python3 -m venv .venv && source .venv/bin/activate
pip install requests
cp .env.example .env      # kendi değerlerini yaz
```

### Gerekli değerler

| Anahtar | Nereden alınır |
|---|---|
| `TELEGRAM_TOKEN` | Telegram'da [@BotFather](https://t.me/BotFather) ile bot oluşturunca verilir |
| `TELEGRAM_CHAT_ID` | Bota bir mesaj atıp `getUpdates` çıktısından okunur |

## Çalıştırma

```bash
python fiyat_toplayici.py    # fiyatları çeker, kaydeder, Telegram'a yollar
python bot_dinleyici.py      # gelen mesajları dinler ve yanıtlar
```

Düzenli çalıştırmak için macOS'ta `cron`, Windows'ta Görev Zamanlayıcı kullanılabilir.

## Teknik notlar

- Siteler `requests` ile normal bir Chrome gibi tanıtılarak çekilir; bu olmadan çoğu site 403 döner.
- **Teknosa listeye dahil edilmedi**: Cloudflare WAF hem `requests` hem de headless/headed
  Playwright isteklerini engelliyor.
- HTML yapısı değişen bir site için ayrıştırma deseni `fiyat_toplayici.py` içinde tek yerde
  tanımlıdır, güncellemesi kolaydır.

## Not

`.env` ve `fiyatlar.db` depoya dahil değildir — biri gizli anahtar, diğeri kişisel ölçüm geçmişi.
