# bot_dinleyici.py
# Telegram'a herhangi bir mesaj (or, /fiyat) yazdiginda en son toplanan
# fiyatlari + 7 gunluk karsilastirmayi aninda cevap olarak doner.
# Yeniden site cekmez - sadece fiyatlar.db'deki en son kaydi okur.
#
# Surekli calisir (long polling). Durdurmak icin Ctrl+C ya da pencereyi kapat.
# Calistirma: pythonw bot_dinleyici.py   (konsol penceresi acmadan, arka planda)

import os
import time
import sqlite3
import requests

from fiyat_toplayici import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DB_YOLU, durum_ozeti

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OFFSET_YOLU = os.path.join(BASE_DIR, "bot_offset.txt")


def offset_oku():
    if os.path.exists(OFFSET_YOLU):
        with open(OFFSET_YOLU, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    return 0


def offset_yaz(offset):
    with open(OFFSET_YOLU, "w", encoding="utf-8") as f:
        f.write(str(offset))


def mesaj_gonder(metin):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": metin}, timeout=30)


def guncellemeleri_al(offset):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    yanit = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=40)
    yanit.raise_for_status()
    return yanit.json().get("result", [])


def main():
    print("Bot dinleyici basladi. Telegram'a herhangi bir mesaj yazinca fiyat durumu donecek.")
    offset = offset_oku()
    while True:
        try:
            guncellemeler = guncellemeleri_al(offset)
        except Exception as e:
            print(f"getUpdates hatasi: {e}")
            time.sleep(10)
            continue

        for guncelleme in guncellemeler:
            offset = guncelleme["update_id"] + 1
            offset_yaz(offset)

            mesaj_verisi = guncelleme.get("message", {})
            gonderen_chat_id = str(mesaj_verisi.get("chat", {}).get("id", ""))
            if gonderen_chat_id != str(TELEGRAM_CHAT_ID):
                continue  # sadece kendi chat_id'mizden gelen mesajlara cevap ver

            baglanti = sqlite3.connect(DB_YOLU)
            try:
                cevap = durum_ozeti(baglanti)
            finally:
                baglanti.close()

            print("Soru geldi, cevap gonderiliyor.")
            mesaj_gonder(cevap)


if __name__ == "__main__":
    main()
