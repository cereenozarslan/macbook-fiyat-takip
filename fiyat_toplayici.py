# fiyat_toplayici.py
# MacBook Air M5 (MDHH4TU/A, 16GB/512GB) fiyatlarini 4 kaynaktan ceker,
# fiyatlar.db'ye kaydeder ve ozeti Telegram'a yollar.
#
# Kurulum:    pip install requests        (sqlite3 Python'da hazir gelir)
# Calistirma: python fiyat_toplayici.py
#
# Desenler 06.07.2026 tarihli DevTools kesif notlarindan (urller.txt).

import os
from pathlib import Path
import re
import time
import sqlite3
import datetime
import requests

# Task Scheduler gibi baska bir dizinden calistirildiginda da fiyatlar.db ve
# hata_*.html dosyalarinin hep script'in yaninda olusmasi icin mutlak yol.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_YOLU = os.path.join(BASE_DIR, "fiyatlar.db")

# -- 0. GIZLI BILGILER (kendi degerlerinle doldur) -----------------------
# NOT: Bunlari kimseyle paylasma. Ilerde .env dosyasina tasiyacagiz.
# -- .env yukleyici (ek kutuphane gerektirmez) ---------------------------
# Gizli anahtarlar bu dosyanin yanindaki .env dosyasindan okunur.
# .env dosyasi .gitignore icindedir, GitHub'a gitmez.
_env_dosyasi = Path(__file__).with_name(".env")
if _env_dosyasi.exists():
    for _satir in _env_dosyasi.read_text(encoding="utf-8").splitlines():
        _satir = _satir.strip()
        if _satir and not _satir.startswith("#") and "=" in _satir:
            _k, _v = _satir.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TRENDYOL_URL = "https://www.trendyol.com/apple/13-macbook-air-apple-m5-cip-10-cekirdekli-cpu-ve-8-cekirdekli-gpu-16-gb-ram-512-gb-ssd-gece-yarisi-p-1113548927?boutiqueId=690310&merchantId=968"


# -- 1. TAKIP EDILEN URUN SAYFALARI (HTML kaynaklar) ---------------------
URLLER = {
    "apple": "https://www.apple.com/tr/shop/buy-mac/macbook-air/13-in%C3%A7-g%C3%B6k-mavisi-m5-%C3%A7ip-10-%C3%A7ekirdekli-cpu-8-%C3%A7ekirdekli-gpu-16-gb-bellek-512gb-depolama",
    "vatan": "https://www.vatanbilgisayar.com/macbook-air-mdhh4tu-a-m5-16gb-512gb-ssd-liquid-retina-13-6inc-gok-mavisi.html",
    "mediamarkt": "https://www.mediamarkt.com.tr/tr/product/_apple-mdhh4tuamacbook-airapple-m5-islemci10-cekirdek-cpu-8-cekirdek-gpu16gb-ram512gb-ssd136gokyuzu-mavisi-1252860.html",
    "trendyol": TRENDYOL_URL,
}
# NOT (06.07.2026): Teknosa Cloudflare WAF ile sert engelliyor (headless VE headed
# Playwright'ta da "Sorry, you have been blocked"). requests ile asilamaz, listeden cikarildi.

# Kendimizi siradan bir Chrome gibi tanitiyoruz (bunsuz bircok site 403 doner).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 403 donduren siteler icin "isinma" turu: once ana sayfaya ugrayip cerez alalim.
ISINMA = {}

# -- 2. SITE BASINA FIYAT DESENLERI (kesif notlarindan) ------------------
DESENLER = {
    "vatan": [
        r'"ProductPrice"\s*:\s*"([\d.,]+)"',
        r'data-product-price="([\d.,]+)"',
    ],
    "mediamarkt": [
        r'"price"\s*:\s*"([\d.,]+)"\s*,\s*"priceCurrency"\s*:\s*"TRY"',
        r'"amount"\s*:\s*([\d.,]+)',
    ],
    "apple": [
        # JSON-LD urun verisinde priceCurrency, price'tan ONCE geliyor (06.07.2026 hata_apple.html'den dogrulandi).
        # Not: yakalama grubunda virgul YOK - bu JSON sayisi (84999.00), Turkce bicimli metin degil.
        r'"priceCurrency"\s*:\s*"TRY"\s*,\s*"price"\s*:\s*([\d.]+)',
        r'"price"\s*:\s*"?([\d.,]+)"?\s*,\s*"priceCurrency"\s*:\s*"TRY"',
        r'"currentPrice"[^{]*?"raw_amount"\s*:\s*"([\d.,]+)"',
        r'"price"\s*:\s*\{\s*"value"\s*:\s*([\d.,]+)',
    ],
    "trendyol": [
        # Sayfanin tek JSON-LD Product blogu, merchantId=968 (Trendyol'un kendi
        # listesi) icin dogru fiyati veriyor (06.07.2026 trendyol_test.html'den dogrulandi).
        r'"priceCurrency"\s*:\s*"TRY"\s*,\s*"price"\s*:\s*"?([\d.]+)"?',
    ],
}


# -- 3. YARDIMCILAR ------------------------------------------------------
def fiyati_sayiya_cevir(deger):
    """'84999', '84999.0', '84.999,00' veya sayi -> 84999.0 float."""
    if isinstance(deger, (int, float)):
        return float(deger)
    metin = str(deger).strip()
    if "," in metin:                       # Turkce bicim: 84.999,00
        metin = metin.replace(".", "").replace(",", ".")
    return float(metin)


def mantikli_mi(fiyat):
    """Aksesuar/tesaduf eslesmeye karsi sigorta: makul MacBook araligi."""
    return 20_000 <= fiyat <= 500_000


def sayfayi_indir(url, isinma_url=None, max_deneme=3, bekleme_suresi=5):
    """Ham HTML dondurur. isinma_url verilirse once oraya ugrar (cerez + Referer).
    Hata durumunda max_deneme kadar dener."""
    son_hata = None
    for deneme in range(1, max_deneme + 1):
        try:
            oturum = requests.Session()
            oturum.headers.update(HEADERS)
            if isinma_url:
                oturum.get(isinma_url, timeout=30)          # cerez topla
                oturum.headers["Referer"] = isinma_url       # "oradan geliyorum"
            yanit = oturum.get(url, timeout=30)
            yanit.raise_for_status()
            return yanit.text
        except Exception as e:
            son_hata = e
            if deneme < max_deneme:
                print(f"    [Deneme {deneme}/{max_deneme}] Hata olustu, {bekleme_suresi} sn sonra tekrar denenecek: {e}")
                time.sleep(bekleme_suresi)
    raise son_hata


def fiyat_ayikla(site, html):
    """Desenleri sirayla dener; (fiyat, kullanilan_desen) dondurur."""
    for desen in DESENLER[site]:
        eslesme = re.search(desen, html)
        if eslesme:
            fiyat = fiyati_sayiya_cevir(eslesme.group(1))
            if mantikli_mi(fiyat):
                return fiyat, desen
    return None, None


# -- 4. VERITABANI -------------------------------------------------------
def veritabanini_hazirla():
    baglanti = sqlite3.connect(DB_YOLU)
    baglanti.execute("""
        CREATE TABLE IF NOT EXISTS fiyatlar (
            tarih TEXT NOT NULL,
            site  TEXT NOT NULL,
            fiyat REAL,
            desen TEXT,
            PRIMARY KEY (tarih, site)
        )
    """)
    baglanti.commit()
    return baglanti


def kaydet(baglanti, tarih, site, fiyat, desen):
    baglanti.execute(
        "INSERT OR REPLACE INTO fiyatlar (tarih, site, fiyat, desen) VALUES (?, ?, ?, ?)",
        (tarih, site, fiyat, desen),
    )
    baglanti.commit()


def gecmis_fiyat(baglanti, site, tarih, gun_once=7):
    """`tarih`'ten `gun_once` gun onceye ait ya da ondan once kaydedilmis
    en yakin fiyati dondurur (yoksa None)."""
    hedef = (datetime.date.fromisoformat(tarih) - datetime.timedelta(days=gun_once)).isoformat()
    satir = baglanti.execute(
        "SELECT fiyat FROM fiyatlar WHERE site = ? AND tarih <= ? AND fiyat IS NOT NULL "
        "ORDER BY tarih DESC LIMIT 1",
        (site, hedef),
    ).fetchone()
    return satir[0] if satir else None


def karsilastirma_metni(fiyat, eski_fiyat):
    """'(7 gun once 86.999 TL idi, dustu: 2.000 TL / %2.3)' gibi bir ek metin uretir."""
    if eski_fiyat is None:
        return " (7 gunluk karsilastirma icin veri yok)"
    fark = fiyat - eski_fiyat
    if fark == 0:
        return " (7 gun once ile ayni)"
    yon = "dustu" if fark < 0 else "artti"
    yuzde = abs(fark) / eski_fiyat * 100
    return f" (7 gun once {eski_fiyat:,.0f} TL idi, {yon}: {abs(fark):,.0f} TL / %{yuzde:.1f})"


def durum_ozeti(baglanti):
    """En son toplanan fiyatlarin + 7 gunluk karsilastirmanin metin ozeti.
    Yeniden site cekmez, sadece db'deki en son kaydi okur (bot_dinleyici.py bunu kullanir)."""
    son_tarih_satir = baglanti.execute("SELECT MAX(tarih) FROM fiyatlar").fetchone()
    son_tarih = son_tarih_satir[0] if son_tarih_satir else None
    if not son_tarih:
        return "Henuz hic veri toplanmamis."

    satirlar = baglanti.execute(
        "SELECT site, fiyat FROM fiyatlar WHERE tarih = ? ORDER BY site", (son_tarih,)
    ).fetchall()

    mesaj = f"MacBook Air M5 Fiyat Durumu (son veri: {son_tarih})\n" + "-" * 30 + "\n"
    for site, fiyat in satirlar:
        if fiyat is None:
            mesaj += f"- {site.capitalize()}: veri yok\n"
            continue
        eski_fiyat = gecmis_fiyat(baglanti, site, son_tarih)
        mesaj += f"- {site.capitalize()}: {fiyat:,.0f} TL{karsilastirma_metni(fiyat, eski_fiyat)}\n"
    return mesaj


# -- 5. TELEGRAM ---------------------------------------------------------
def telegrama_mesaj_gonder(mesaj):
    if TELEGRAM_TOKEN.startswith("BURAYA") or TELEGRAM_CHAT_ID.startswith("BURAYA"):
        print("(Telegram bilgileri girilmedi, mesaj atlandi.)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        yanit = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}, timeout=30)
        sonuc = yanit.json()   # Telegram'in kendi hata cevabini da yakala
        if not sonuc.get("ok"):
            print(f"Telegram reddetti: {sonuc.get('description')}")
    except Exception as e:
        print(f"Telegram mesaji gitmedi: {e}")


# -- 6. ANA AKIS ---------------------------------------------------------
def main():
    bugun = datetime.date.today().isoformat()
    baglanti = veritabanini_hazirla()
    print(f"Fiyat toplama basliyor - {bugun}\n" + "-" * 45)

    mesaj = f"MacBook Air M5 Fiyatlar ({bugun})\n" + "-" * 30 + "\n"

    for site, url in URLLER.items():
        try:
            html = sayfayi_indir(url, isinma_url=ISINMA.get(site))
            fiyat, desen = fiyat_ayikla(site, html)
            if fiyat is None:
                dosya = os.path.join(BASE_DIR, f"hata_{site}.html")
                with open(dosya, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  {site:<11} FIYAT BULUNAMADI ({dosya})")
                mesaj += f"- {site.capitalize()}: fiyat cekilemedi\n"
            else:
                eski_fiyat = gecmis_fiyat(baglanti, site, bugun)
                ek = karsilastirma_metni(fiyat, eski_fiyat)
                print(f"  {site:<11} {fiyat:>12,.2f} TL{ek}")
                mesaj += f"- {site.capitalize()}: {fiyat:,.0f} TL{ek}\n"
            kaydet(baglanti, bugun, site, fiyat, desen)
        except Exception as hata:
            print(f"  {site:<11} HATA: {hata}")
            kaydet(baglanti, bugun, site, None, "hata")
            mesaj += f"- {site.capitalize()}: hata\n"

    baglanti.close()
    print("-" * 45 + "\nBitti. Kayitlar fiyatlar.db dosyasinda.")
    telegrama_mesaj_gonder(mesaj)


if __name__ == "__main__":
    main()