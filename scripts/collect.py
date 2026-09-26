#!/usr/bin/env python3
"""
Mevzuat Takip – günlük toplayıcı.

1) Resmî Gazete günlük fihristini (son başarılı tarihten bugüne, en fazla 7 gün) çeker,
   bölüm/başlık/bağlantı olarak ayrıştırır, anahtar kelime eşleşmelerini işaretler.
2) config/sources.yml içindeki duyuru/bülten sayfalarını tarar ve bir önceki
   çalıştırmaya göre YENİ bağlantıları çıkarır (fark takibi).
3) Sonuçları data/latest.json, data/latest.md ve data/archive/YYYY-MM-DD.json olarak yazar.

Günde tek istek/kaynak yapılır; özetleme ve hukuki değerlendirme bu betiğin işi değildir.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
import yaml
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.yml"
STATE_DIR = ROOT / "state"
DATA_DIR = ROOT / "data"
TZ = ZoneInfo("Europe/Istanbul")

RG_BASE = "https://www.resmigazete.gov.tr"
RG_FIHRIST = RG_BASE + "/fihrist?tarih={d}"
MAX_BACKFILL_DAYS = 7

UA = "MevzuatTakip/1.0 (gunluk tek istek; kisisel mevzuat takibi)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})

NOT_PUBLISHED_MARKERS = ["yayımlanması çalışmaları devam", "yayimlanmasi calismalari devam"]
LINK_NOISE = {"pdf görüntüle", "önceki sayı", "sonraki sayı", "yardım", "bize ulaşın"}


# ----------------------------------------------------------------------------- yardımcılar
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:  # ağ / HTTP hatası
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def clean(text: str) -> str:
    return " ".join(text.split()).strip()


def tr_lower(s: str) -> str:
    s = s.replace("I", "ı").replace("İ", "i").lower()
    # Şapkalı harfler (İLÂN / ilan) karşılaştırmada eşit sayılır
    return s.translate(str.maketrans("âîû", "aiu"))


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    t = tr_lower(text)
    return sorted({k for k in keywords if tr_lower(k) in t})


# ----------------------------------------------------------------------------- Resmî Gazete
def is_heading(txt: str) -> bool:
    if not (4 <= len(txt) <= 90):
        return False
    if txt.startswith(("–", "-", "—")) or any(ch.isdigit() for ch in txt):
        return False
    letters = [c for c in txt if c.isalpha()]
    return bool(letters) and txt == txt.upper() and tr_lower(txt) not in LINK_NOISE


def parse_fihrist(html: str, page_url: str, keywords: list[str], skip_sections: list[str]) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    # select/option: tarih ve mükerrer seçim kutuları (günün içeriği değil)
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "select", "option"]):
        t.decompose()

    full_text = clean(soup.get_text(" "))
    if any(m in tr_lower(full_text) for m in NOT_PUBLISHED_MARKERS):
        return {"status": "henuz_yayimlanmadi", "items": [], "notes": []}

    m = re.search(r"(\d{1,2}\s+\S+\s+\d{4})\s+Tarihli\s+ve\s+(\d+)\s+Say", full_text)
    header = {"tarih_metni": m.group(1), "sayi": m.group(2)} if m else {}

    items, notes, seen_anchor_ids = [], [], set()
    section = subsection = None
    body = soup.body or soup
    for node in body.descendants:
        if not isinstance(node, NavigableString):
            continue
        txt = clean(str(node))
        if not txt:
            continue
        anchor = node.find_parent("a")
        if anchor is not None:
            if id(anchor) in seen_anchor_ids:
                continue
            seen_anchor_ids.add(id(anchor))
            title = clean(anchor.get_text(" ")).lstrip("–—- ").strip()
            href = anchor.get("href") or ""
            if len(title) < 12 or tr_lower(title) in LINK_NOISE or not href or href.startswith("#"):
                continue
            url = urljoin(page_url, href)
            if "resmigazete.gov.tr" not in url:
                continue
            if section and any(tr_lower(s) in tr_lower(section) for s in skip_sections):
                continue
            items.append({
                "bolum": section,
                "tur": subsection,
                "baslik": title,
                "url": url,
                "mukerrer": bool(re.search(r"\d{8}M\d", url, re.I)) or "mükerrer" in tr_lower(title),
                "anahtar_kelime": keyword_hits(title, keywords),
            })
        elif is_heading(txt):
            if txt.endswith("BÖLÜMÜ"):
                section, subsection = txt, None
            else:
                subsection = txt
        elif "mükerrer" in tr_lower(txt) and len(txt) >= 15:
            # tek kelimelik "Mükerrer" sekme/buton etiketleri not sayılmaz
            notes.append(txt)

    status = "ok" if items or header else "bos_veya_ayristirilamadi"
    return {"status": status, **header, "items": items, "notes": sorted(set(notes))}


def collect_resmi_gazete(cfg: dict, today: date) -> dict:
    state_path = STATE_DIR / "resmi_gazete.json"
    state = load_json(state_path, {})
    last_ok = state.get("son_basarili_tarih")
    start = today if not last_ok else date.fromisoformat(last_ok) + timedelta(days=1)
    start = max(start, today - timedelta(days=MAX_BACKFILL_DAYS - 1))

    issues, d = [], start
    while d <= today:
        url = RG_FIHRIST.format(d=d.isoformat())
        rec = {"tarih": d.isoformat(), "url": url}
        try:
            parsed = parse_fihrist(fetch(url), url, cfg.get("keywords", []), cfg.get("rg_skip_sections", []))
            rec.update(parsed)
            if parsed["status"] == "ok":
                state["son_basarili_tarih"] = d.isoformat()
        except Exception as e:  # erişim hatası dahil
            rec.update({"status": "erisilemedi", "hata": str(e)[:300], "items": [], "notes": []})
        issues.append(rec)
        d += timedelta(days=1)
        time.sleep(2)

    save_json(state_path, state)
    return {"kaynak": "Resmî Gazete", "sayilar": issues}


# ----------------------------------------------------------------------------- duyuru sayfaları
def collect_listing(src: dict, keywords: list[str]) -> dict:
    sid = src["id"]
    state_path = STATE_DIR / f"seen_{sid}.json"
    seen: list[str] = load_json(state_path, [])
    first_run = not seen
    out = {"id": sid, "kaynak": src["name"], "url": src["url"], "yeni": []}
    try:
        html = fetch(src["url"])
        soup = BeautifulSoup(html, "html.parser")
        scope = soup.select_one(src["selector"]) if src.get("selector") else soup
        if scope is None:
            raise RuntimeError(f"selector bulunamadı: {src['selector']}")
        pattern = re.compile(src["link_pattern"]) if src.get("link_pattern") else None
        found, seen_set = [], set(seen)
        for a in scope.find_all("a", href=True):
            title = clean(a.get_text(" "))
            url = urljoin(src["url"], a["href"])
            if len(title) < src.get("min_title_len", 15) or (pattern and not pattern.search(url)):
                continue
            if url in seen_set or any(f["url"] == url for f in found):
                continue
            found.append({"baslik": title, "url": url, "anahtar_kelime": keyword_hits(title, keywords)})
        if first_run:
            out["durum"] = "ilk_calistirma_referans_alindi"
        else:
            out["durum"] = "yeni_kayit" if found else "degisiklik_yok"
            out["yeni"] = found
        save_json(state_path, ([f["url"] for f in found] + seen)[:1000])
    except Exception as e:
        out["durum"] = "erisilemedi"
        out["hata"] = str(e)[:300]
    return out


# ----------------------------------------------------------------------------- çıktı
def render_md(result: dict) -> str:
    lines = [f"# Mevzuat Takip – Ham Toplama ({result['tarih']})", "",
             f"Oluşturulma: {result['olusturulma']}", ""]
    for issue in result["resmi_gazete"]["sayilar"]:
        lines.append(f"## Resmî Gazete {issue['tarih']} – sayı {issue.get('sayi', '?')} – durum: {issue['status']}")
        if issue.get("hata"):
            lines.append(f"Hata: {issue['hata']}")
        for n in issue.get("notes", []):
            lines.append(f"> Not: {n}")
        cur = None
        for it in issue.get("items", []):
            key = (it["bolum"], it["tur"])
            if key != cur:
                lines.append(f"\n**{it['bolum'] or '-'} / {it['tur'] or '-'}**")
                cur = key
            flag = f" `[{', '.join(it['anahtar_kelime'])}]`" if it["anahtar_kelime"] else ""
            muk = " (mükerrer)" if it["mukerrer"] else ""
            lines.append(f"- [{it['baslik']}]({it['url']}){muk}{flag}")
        lines.append("")
    lines.append("## Kurum sayfaları")
    for s in result["kurumlar"]:
        lines.append(f"### {s['kaynak']} – {s['durum']}")
        if s.get("hata"):
            lines.append(f"Hata: {s['hata']}")
        for it in s.get("yeni", []):
            flag = f" `[{', '.join(it['anahtar_kelime'])}]`" if it["anahtar_kelime"] else ""
            lines.append(f"- [{it['baslik']}]({it['url']}){flag}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    now = datetime.now(TZ)
    today = now.date()
    result = {
        "tarih": today.isoformat(),
        "olusturulma": now.isoformat(timespec="seconds"),
        "resmi_gazete": collect_resmi_gazete(cfg, today),
        "kurumlar": [collect_listing(s, cfg.get("keywords", [])) for s in cfg.get("sources", []) if s.get("enabled", True)],
    }
    save_json(DATA_DIR / "latest.json", result)
    save_json(DATA_DIR / "archive" / f"{today.isoformat()}.json", result)
    (DATA_DIR / "latest.md").write_text(render_md(result), encoding="utf-8")

    rg_status = [i["status"] for i in result["resmi_gazete"]["sayilar"]]
    print(f"Resmî Gazete: {rg_status}")
    for s in result["kurumlar"]:
        print(f"{s['kaynak']}: {s['durum']} ({len(s.get('yeni', []))} yeni)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
