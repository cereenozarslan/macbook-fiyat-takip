# mcp_server.py
# MacBook Air M5 fiyat takibi icin salt-okunur MCP server.
# fiyatlar.db'ye HICBIR SEY yazmaz, sadece fiyat_toplayici.py'deki
# fonksiyonlari kullanarak veritabanini okur.
#
# Kurulum:    pip install mcp
# Calistirma: python mcp_server.py   (stdio uzerinden bir MCP istemcisine baglanir)

import sqlite3

from mcp.server.fastmcp import FastMCP

from fiyat_toplayici import DB_YOLU, URLLER, durum_ozeti, gecmis_fiyat

mcp = FastMCP("macbook-fiyat-takibi")


def _salt_okunur_baglanti():
    # uri=True + mode=ro: veritabanini kesinlikle degistirmeden acar.
    return sqlite3.connect(f"file:{DB_YOLU}?mode=ro", uri=True)


@mcp.tool()
def guncel_fiyatlar() -> str:
    """En son toplanan MacBook Air M5 fiyatlarinin ve 7 gunluk karsilastirmanin ozetini dondurur."""
    baglanti = _salt_okunur_baglanti()
    try:
        return durum_ozeti(baglanti)
    finally:
        baglanti.close()


@mcp.tool()
def gecmis_fiyat_sorgula(site: str, tarih: str, gun_once: int = 7) -> str:
    """Belirtilen site icin `tarih`'ten `gun_once` gun onceye ait en yakin kaydedilmis fiyati dondurur.

    site: apple, vatan, mediamarkt veya trendyol
    tarih: YYYY-AA-GG formatinda (orn. 2026-07-07)
    """
    if site not in URLLER:
        return f"Bilinmeyen site: {site}. Gecerli siteler: {', '.join(URLLER)}"
    baglanti = _salt_okunur_baglanti()
    try:
        fiyat = gecmis_fiyat(baglanti, site, tarih, gun_once)
    finally:
        baglanti.close()
    if fiyat is None:
        return f"{site} icin {tarih} tarihinden {gun_once} gun once/oncesine ait veri bulunamadi."
    return f"{site}: {tarih} tarihinden {gun_once} gun once/oncesine ait en yakin fiyat {fiyat:,.0f} TL"


if __name__ == "__main__":
    mcp.run()
