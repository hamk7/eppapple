from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "current.json"
SUMMARY = ROOT / "history-summary.json"
HISTORY = ROOT / "price-history"

BASE = "https://www.apple.com"
VAT = Decimal("0.19")
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36 AppleRabattBot/3.0",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
})

ZPUE = {
    "iphone": ("https://www.zpue.de/produkte-tarife/mobiltelefone.html", [r"Verbraucher-Mobiltelefone:\s*([0-9]+,[0-9]+)\s*€", r"([0-9]+,[0-9]+)\s*€"]),
    "ipad": ("https://www.zpue.de/produkte-tarife/tablets.html", [r"Verbraucher-Tablet:\s*([0-9]+,[0-9]+)\s*€", r"([0-9]+,[0-9]+)\s*€"]),
    "mac": ("https://www.zpue.de/produkte-tarife/pcs.html", [r"Verbraucher-PCs?:\s*([0-9]+,[0-9]+)\s*€", r"([0-9]+,[0-9]+)\s*€"]),
    "watch": ("https://www.zpue.de/produkte-tarife/smartwatches.html", [r"Smartwatches?:\s*([0-9]+,[0-9]+)\s*€", r"([0-9]+,[0-9]+)\s*€"]),
}

LANDINGS = {
    "iphone": ["https://www.apple.com/de/shop/buy-iphone"],
    "ipad": ["https://www.apple.com/de/shop/buy-ipad"],
    "mac": ["https://www.apple.com/de/shop/buy-mac"],
    "displays": ["https://www.apple.com/de/shop/buy-mac"],
    "watch": ["https://www.apple.com/de/shop/buy-watch"],
    "vision": ["https://www.apple.com/de/shop/buy-vision"],
    "airpods": ["https://www.apple.com/de/shop/buy-airpods"],
    "tvhome": [
        "https://www.apple.com/de/shop/buy-tv",
        "https://www.apple.com/de/shop/buy-homepod/homepod",
        "https://www.apple.com/de/shop/buy-homepod/homepod-mini",
    ],
}

ACCESSORIES_ALL = "https://www.apple.com/de/shop/accessories/all"
ACCESSORIES_APPLE = "https://www.apple.com/de/shop/accessories/all/made-by-apple"

ACCESSORY_LABEL_TO_ID = {
    "airtag": "airtag",
    "adapter": "adapter",
    "adapters": "adapter",
    "kabel": "kabel",
    "cables": "kabel",
    "cases & cover": "cases",
    "cases & covers": "cases",
    "ladegeräte": "ladegeraete",
    "chargers": "ladegeraete",
    "kopfhörer": "kopfhoerer",
    "headphones": "kopfhoerer",
    "illustration & design": "design",
    "armbänder": "armbaender",
    "watch bands": "armbaender",
    "wallets": "wallets",
    "tastaturen": "tastaturen",
    "keyboards": "tastaturen",
    "mäuse": "maeuse",
    "mice": "maeuse",
    "poliertuch": "poliertuch",
    "polishing cloth": "poliertuch",
    "fernbedienungen": "fernbedienungen",
    "remotes": "fernbedienungen",
    "lautsprecher": "lautsprecher",
    "speakers": "lautsprecher",
    "trackpads": "trackpads",
    "displays": "displays",
}

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?\s*€")
STORAGE_RE = re.compile(r"(?<!\d)(128|256|512)\s*GB|(?<!\d)(1|2|4|8)\s*TB", re.I)
RAM_RE = re.compile(r"(?<!\d)(8|12|16|18|24|32|36|48|64|96|128|192)\s*GB\s*(?:Arbeitsspeicher|gemeinsamer Arbeitsspeicher|Unified Memory)?", re.I)
SIZE_RE = re.compile(r"(?<!\d)(8[,.]3|11|13|14|15|16|24|40|42|44|46|49)(?:\s*\"|\s*Zoll|\s*mm)", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def slugify(s: str) -> str:
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:90]


def parse_price(text: str) -> float | None:
    m = PRICE_RE.search(clean(text))
    if not m:
        return None
    return float(m.group(1).replace(".", "") + "." + (m.group(2) or "00"))


def get(url: str) -> str:
    last = None
    for attempt in range(3):
        try:
            r = S.get(url, timeout=40)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def signature(data) -> str:
    keep = {k: data.get(k) for k in ("vat", "levies", "categories", "products")}
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def soup_for(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def apple_image(html: str, base_url: str) -> str | None:
    soup = soup_for(html)
    for attrs in (
        {"property": "og:image"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return urljoin(base_url, tag["content"])
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if src and ("store.storeimages" in src or "www.apple.com" in src or "/v/" in src):
            return urljoin(base_url, src)
    return None


def nearest_text_with_price(node, max_up=5) -> str:
    cur = node
    best = ""
    for _ in range(max_up):
        if not cur:
            break
        text = clean(cur.get_text(" ", strip=True)) if hasattr(cur, "get_text") else ""
        if text and PRICE_RE.search(text):
            best = text
            if 10 <= len(text) <= 700:
                return text
        cur = getattr(cur, "parent", None)
    return best[:1200]


def page_model_cards(html: str, landing_url: str):
    """Return likely store model cards from a public Apple category landing page."""
    soup = soup_for(html)
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(landing_url, a["href"])
        if "/de/shop/buy-" not in href:
            continue
        text = clean(a.get_text(" ", strip=True))
        box = a
        for _ in range(5):
            box = box.parent if box else None
            if not box:
                break
            bt = clean(box.get_text(" ", strip=True))
            if "Ab " in bt and "€" in bt and len(bt) < 900:
                text = bt
                break
        price = None
        m = re.search(r"\bAb\s+" + PRICE_RE.pattern, text, re.I)
        if m:
            # nested groups from PRICE_RE are groups 1/2 here too
            raw = m.group(0)
            price = parse_price(raw)
        if price is None:
            continue
        # Find the most plausible model name in nearby headings / anchor text.
        name = clean(a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True))
        if not name or len(name) < 3 or "kaufen" == name.lower():
            for h in (a.find_previous(["h2", "h3", "h4"]), box.find(["h2", "h3", "h4"]) if box else None):
                if h:
                    candidate = clean(h.get_text(" ", strip=True))
                    if candidate and len(candidate) < 100:
                        name = candidate
                        break
        name = re.sub(r"\s+(Genauer ansehen|Kaufen|Vorbestellen).*", "", name, flags=re.I).strip()
        if not name or any(x in name.lower() for x in ["shopping", "zubehör", "specialist", "trade in"]):
            continue
        key = (name.lower(), href.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "gross": price, "url": href.split("?")[0]})
    return out


def infer_series(name: str, category: str) -> tuple[str, int]:
    n = clean(name)
    if category == "iphone":
        if "Pro Max" in n:
            m = re.search(r"iPhone\s+(\d+)", n, re.I); return ("iphone-pro-max", int(m.group(1)) if m else 0)
        if " Pro" in n:
            m = re.search(r"iPhone\s+(\d+)", n, re.I); return ("iphone-pro", int(m.group(1)) if m else 0)
        if re.search(r"\d+e", n):
            m = re.search(r"iPhone\s+(\d+)e", n, re.I); return ("iphone-e", int(m.group(1)) if m else 0)
        if "Air" in n:
            return ("iphone-air", 1)
        m = re.search(r"iPhone\s+(\d+)", n, re.I); return ("iphone-standard", int(m.group(1)) if m else 0)
    if category == "ipad":
        if "Pro" in n: return ("ipad-pro", 0)
        if "Air" in n: return ("ipad-air", 0)
        if "mini" in n.lower(): return ("ipad-mini", 0)
        return ("ipad-standard", 0)
    if category == "watch":
        if "Hermès" in n and "Ultra" in n: return ("watch-hermes-ultra", _num_after(n, "Ultra"))
        if "Hermès" in n: return ("watch-hermes-series", _num_after(n, "Series"))
        if "Ultra" in n: return ("watch-ultra", _num_after(n, "Ultra"))
        if "SE" in n: return ("watch-se", _num_after(n, "SE"))
        return ("watch-series", _num_after(n, "Series"))
    if category == "airpods":
        if "Pro" in n: return ("airpods-pro", _num_after(n, "Pro"))
        if "Max" in n: return ("airpods-max", _num_after(n, "Max"))
        return ("airpods", _num_after(n, "AirPods"))
    return (slugify(n), 0)


def _num_after(text: str, token: str) -> int:
    m = re.search(re.escape(token) + r"\s*(\d+)", text, re.I)
    return int(m.group(1)) if m else 0


def infer_subcategory(name: str, category: str) -> str:
    n = name.lower()
    if category == "iphone":
        if "pro" in n: return "pro"
        if "air" in n: return "air"
        return "standard"
    if category == "ipad":
        if "pro" in n: return "pro"
        if "air" in n: return "air"
        if "mini" in n: return "mini"
        return "standard"
    if category == "mac":
        if "macbook" in n: return "macbooks"
        if "imac" in n: return "imac"
        if "mini" in n: return "mac-mini"
        if "studio" in n: return "mac-studio"
        return "desktop"
    if category == "watch":
        if "hermès" in n: return "hermes"
        if "ultra" in n: return "ultra"
        if "se" in n: return "se"
        return "series"
    return "all"


def refresh_levies(data):
    for cat, (url, patterns) in ZPUE.items():
        try:
            text = clean(soup_for(get(url)).get_text(" ", strip=True))
            amount = None
            for pat in patterns:
                vals = re.findall(pat, text, flags=re.I)
                if vals:
                    # ZPÜ usually shows list price first and Gesamtvertrag amount later.
                    candidates = [float(v.replace(",", ".")) for v in vals]
                    if cat == "iphone": candidates = [v for v in candidates if 1 <= v <= 20]
                    if cat == "ipad": candidates = [v for v in candidates if 1 <= v <= 30]
                    if cat == "mac": candidates = [v for v in candidates if 1 <= v <= 40]
                    if cat == "watch": candidates = [v for v in candidates if 0.1 <= v <= 10]
                    if candidates:
                        amount = candidates[-1]
                        break
            if amount is None:
                continue
            data.setdefault("levies", {}).setdefault(cat, {})
            data["levies"][cat].update({
                "amount": amount,
                "source": f"ZPÜ {cat} · Gesamtvertragsmitglieder",
                "verified": True,
                "checkedAt": now_iso(),
            })
            for p in data.get("products", []):
                if p.get("category") == cat:
                    for v in p.get("variants", []):
                        v["fee"] = amount
        except Exception as exc:
            print("levy refresh failed", cat, exc)


def discover_models(data):
    by_id = {p["id"]: p for p in data.get("products", [])}
    by_name = {clean(p["name"]).lower(): p for p in data.get("products", [])}
    discovered = set()
    for category, urls in LANDINGS.items():
        cards = []
        for url in urls:
            try:
                html = get(url)
                cards.extend(page_model_cards(html, url))
            except Exception as exc:
                print("landing discovery failed", category, url, exc)
        for card in cards:
            name = card["name"]
            lname0 = name.lower()
            # Displays are intentionally a top-level category rather than Mac.
            if category == "mac" and "display" in lname0:
                continue
            if category == "displays" and "display" not in lname0:
                continue
            if category == "tvhome" and not any(x in lname0 for x in ("apple tv", "homepod")):
                continue
            # Landing pages sometimes combine two products in one card; keep existing hand-curated
            # split models and use the card only to refresh the lowest base price.
            target = None
            lname = name.lower()
            for p in data.get("products", []):
                if p.get("category") != category:
                    continue
                pn = p["name"].lower()
                if pn == lname or pn in lname or lname in pn:
                    target = p
                    break
            if target is None:
                series, gen = infer_series(name, category)
                pid = f"auto-{category}-{slugify(name)}"
                target = {
                    "id": pid,
                    "category": category,
                    "subcategory": infer_subcategory(name, category),
                    "seriesKey": series,
                    "generation": gen,
                    "name": name,
                    "subtitle": "",
                    "sourceUrl": card["url"] or url,
                    "imageUrl": "",
                    "brandType": "apple",
                    "autoDiscovered": True,
                    "variants": [{"id": "base", "label": "Standard", "gross": card["gross"], "fee": data.get("levies", {}).get(category, {}).get("amount", 0)}],
                }
                data.setdefault("products", []).append(target)
                by_id[pid] = target
                by_name[lname] = target
            else:
                # Never destroy detailed variants; only adjust a sole base placeholder here.
                if len(target.get("variants", [])) == 1 and target["variants"][0].get("id") == "base":
                    target["variants"][0]["gross"] = card["gross"]
                if not target.get("sourceUrl") or target.get("autoDiscovered"):
                    target["sourceUrl"] = card["url"] or target.get("sourceUrl") or url
            discovered.add(target["id"])
    return discovered


def storage_from(text: str) -> str | None:
    m = STORAGE_RE.search(text)
    if not m:
        return None
    return f"{m.group(1)} GB" if m.group(1) else f"{m.group(2)} TB"


def size_from(text: str) -> str | None:
    m = SIZE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    if raw in {"40", "42", "44", "46", "49"}:
        return raw + " mm"
    return raw + '"'


def options_from_text(text: str, href: str, product: dict) -> dict:
    t = clean(unquote(text + " " + href)).replace("‑", "-")
    low = t.lower()
    opts = {}
    st = storage_from(t)
    if st: opts["Speicher"] = st
    sz = size_from(t)
    if sz: opts["Größe"] = sz
    rm = RAM_RE.search(t)
    if rm and product.get("category") == "mac": opts["Arbeitsspeicher"] = rm.group(1) + " GB"

    if product.get("category") == "ipad":
        if "wifi-cellular" in low or "wi-fi + cellular" in low or "wi-fi+cellular" in low:
            opts["Verbindung"] = "Wi‑Fi + Cellular"
        elif "wifi" in low or "wi-fi" in low:
            opts["Verbindung"] = "Wi‑Fi"
        if "nanotextur" in low: opts["Glas"] = "Nanotexturglas"
        elif "standardglas" in low or "standardglas" in t: opts["Glas"] = "Standardglas"

    if product.get("category") == "iphone":
        # Screen is only needed to split shared Apple configurator pages.
        if '6,9' in t or '6.9' in t: opts["Display"] = '6,9"'
        elif '6,7' in t or '6.7' in t: opts["Display"] = '6,7"'
        elif '6,5' in t or '6.5' in t: opts["Display"] = '6,5"'
        elif '6,3' in t or '6.3' in t: opts["Display"] = '6,3"'
        elif '6,1' in t or '6.1' in t: opts["Display"] = '6,1"'

    if product.get("category") == "watch":
        if "gps + cellular" in low or "cellular" in low: opts["Verbindung"] = "GPS + Cellular"
        elif re.search(r"\bgps\b", low): opts["Verbindung"] = "GPS"
        if "aluminium" in low: opts["Material"] = "Aluminium"
        elif "titan" in low: opts["Material"] = "Titan"
        # Preserve the last comma segment as the band because Apple product titles follow
        # "Watch …, case description, band description".
        chunks = [clean(x) for x in re.split(r",", text) if clean(x)]
        if len(chunks) >= 3:
            band = chunks[-1]
            if any(k in band.lower() for k in ["armband", "loop", "milanaise", "bracelet"]):
                opts["Armband"] = band[:90]

    if product.get("category") == "mac":
        chip_patterns = [
            r"(M\d+\s*Max)", r"(M\d+\s*Pro)", r"(M\d+)",
        ]
        for pat in chip_patterns:
            cm = re.search(pat, t, re.I)
            if cm:
                opts["Chip"] = re.sub(r"\s+", " ", cm.group(1)).upper().replace("PRO", "Pro").replace("MAX", "Max")
                break
        if "nanotextur" in low: opts["Display"] = "Nanotextur"
        elif "standard-display" in low or "standardglas" in low: opts["Display"] = "Standard"
        if "standfuß" in low or "standfuss" in low: opts["Basis"] = "Standfuß"
        elif "vesa" in low: opts["Basis"] = "VESA"

    if product.get("category") == "vision":
        pass
    return opts


def text_matches_product(text: str, href: str, p: dict) -> bool:
    low = clean(text + " " + unquote(href)).lower()
    name = p["name"].lower()
    cat = p.get("category")
    if cat == "iphone":
        if "pro max" in name: return ("6,9" in low or "6.9" in low or "pro max" in low) and "iphone" in low
        if name.endswith(" pro"): return ("6,3" in low or "6.3" in low or ("pro" in low and "pro max" not in low)) and "iphone" in low
        if "16 plus" in name: return ("6,7" in low or "6.7" in low or "16 plus" in low)
        if name == "iphone 16": return ("6,1" in low or "6.1" in low) and "16" in low and "plus" not in low
        return name.replace("iphone ", "") in low or name in low
    if cat == "watch":
        token = "ultra" if "ultra" in name else ("se" if " se " in f" {name} " else "series")
        return token in low and "watch" in low
    if cat == "airpods":
        return name.replace("apple ", "").lower() in low or "airpods" in low
    return True


def configuration_candidates(html: str, source_url: str, product: dict):
    soup = soup_for(html)
    candidates = []

    # 1) Links to concrete configurator URLs are the cleanest source.
    source_path = urlparse(source_url).path.rstrip("/")
    base_parts = source_path.split("/")
    model_root = source_path
    if "/shop/buy-" in source_path:
        # Keep /de/shop/buy-X/model as root, dropping an already concrete config path.
        parts = source_path.split("/")
        try:
            i = parts.index(next(x for x in parts if x.startswith("buy-")))
            model_root = "/".join(parts[: i + 2])
        except Exception:
            model_root = source_path
    for a in soup.find_all("a", href=True):
        href = urljoin(source_url, a["href"]).split("?")[0]
        if "/de/shop/buy-" not in href:
            continue
        hpath = unquote(urlparse(href).path)
        if model_root and model_root not in hpath and product.get("category") not in {"iphone", "ipad"}:
            continue
        text = clean(a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True))
        near = nearest_text_with_price(a)
        if near and len(near) < 850:
            text = clean(text + " " + near)
        pr = parse_price(text)
        if pr is None:
            continue
        if not text_matches_product(text, href, product):
            continue
        opts = options_from_text(text, href, product)
        if opts:
            candidates.append((opts, pr, href, text))

    # 2) Apple often renders configurator inputs rather than links. Inspect small DOM blocks
    # containing a price and parse their text.
    for node in soup.find_all(string=lambda s: bool(s and "€" in s)):
        parent = node.parent
        text = nearest_text_with_price(parent, max_up=4)
        if not text or len(text) > 850:
            continue
        pr = parse_price(text)
        if pr is None or not text_matches_product(text, source_url, product):
            continue
        href = source_url
        anc = parent.find_parent("a", href=True) if parent else None
        if anc: href = urljoin(source_url, anc["href"]).split("?")[0]
        opts = options_from_text(text, href, product)
        if opts:
            candidates.append((opts, pr, href, text))

    # Normalize and dedupe. Colors are intentionally ignored: color normally does not affect
    # the price and would otherwise create dozens of duplicate configurations.
    fee = product_fee(product)
    best = {}
    for opts, pr, href, text in candidates:
        # Remove display option when it was only needed to distinguish iPhone siblings.
        if product.get("category") == "iphone":
            opts.pop("Display", None)
        key = tuple(sorted(opts.items()))
        if not key:
            continue
        # Prefer the lowest price for identical option combinations (different colors).
        if key not in best or pr < best[key][0]:
            best[key] = (pr, href, text)

    # Avoid pathological explosion on Watch; 240 configs is already plenty for a phone UI.
    items = sorted(best.items(), key=lambda kv: (kv[1][0], kv[0]))[:240]
    variants = []
    for idx, (key, (pr, href, text)) in enumerate(items):
        opts = dict(key)
        label_parts = [v for _, v in key]
        label = " · ".join(label_parts)
        variants.append({
            "id": f"cfg-{idx+1}-{slugify(label)[:45]}",
            "label": label,
            "gross": pr,
            "fee": fee,
            "options": opts,
            "sourceUrl": href,
        })
    return variants


def product_fee(p: dict) -> float:
    return float(p.get("fee", 0) or 0)


def refresh_product_details(data):
    levy_map = {k: float(v.get("amount", 0)) for k, v in data.get("levies", {}).items()}
    for p in data.get("products", []):
        url = p.get("sourceUrl")
        if not url or p.get("category") == "accessories":
            continue
        try:
            html = get(url)
        except Exception as exc:
            print("detail fetch failed", p.get("name"), exc)
            continue
        img = apple_image(html, url)
        if img:
            p["imageUrl"] = img
        # Ensure the correct levy is copied into all variants before parsing.
        fee = levy_map.get(p.get("category"), 0)
        p["fee"] = fee
        for v in p.get("variants", []): v["fee"] = fee
        try:
            variants = configuration_candidates(html, url, p)
        except Exception as exc:
            print("config parse failed", p.get("name"), exc)
            variants = []
        # Require at least as much information as we already have, except placeholder-base products.
        old = p.get("variants", [])
        placeholder = len(old) <= 1 and (not old or old[0].get("id") == "base")
        if variants and (placeholder or len(variants) >= len(old)):
            p["variants"] = variants


def accessory_filter_links(html: str, base_url: str):
    soup = soup_for(html)
    found = {}
    for a in soup.find_all("a", href=True):
        label = clean(a.get_text(" ", strip=True)).lower()
        if label in ACCESSORY_LABEL_TO_ID:
            cid = ACCESSORY_LABEL_TO_ID[label]
            found[cid] = urljoin(base_url, a["href"])
    return found


def accessory_cards(html: str, page_url: str):
    soup = soup_for(html)
    out = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"]).split("?")[0]
        if "/de/shop/product/" not in href and "/shop/product/" not in href:
            continue
        box = a
        text = clean(a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True))
        for _ in range(5):
            if box is None: break
            bt = clean(box.get_text(" ", strip=True))
            if PRICE_RE.search(bt) and len(bt) < 1000:
                text = clean(text + " " + bt)
                break
            box = box.parent
        pr = parse_price(text)
        if pr is None:
            continue
        # Name preference: heading > aria label > short text before price.
        name = ""
        if box:
            h = box.find(["h2", "h3", "h4"])
            if h: name = clean(h.get_text(" ", strip=True))
        if not name:
            name = clean(a.get("aria-label") or a.get("title") or a.get_text(" ", strip=True))
        if not name:
            name = PRICE_RE.split(text)[0].strip(" -–·")[:120]
        name = re.sub(r"\s+(kaufen|anzeigen|weitere infos).*$", "", name, flags=re.I).strip()
        if len(name) < 2:
            continue
        # Try card image before requiring a product-page request.
        img = ""
        if box:
            im = box.find("img")
            if im:
                src = im.get("src") or im.get("data-src")
                if src: img = urljoin(page_url, src)
        out[href] = {"name": name, "gross": pr, "url": href, "imageUrl": img}
    return out


def category_guess_from_name(name: str) -> str:
    n = name.lower()
    rules = [
        ("airtag", ["airtag"]),
        ("poliertuch", ["poliertuch", "polishing cloth"]),
        ("trackpads", ["trackpad"]),
        ("maeuse", ["magic mouse", " mouse", "maus"]),
        ("tastaturen", ["keyboard", "tastatur"]),
        ("wallets", ["wallet"]),
        ("armbaender", ["armband", "loop", "milanaise"]),
        ("fernbedienungen", ["remote", "fernbedien"]),
        ("kabel", ["kabel", "cable", "thunderbolt"]),
        ("ladegeraete", ["ladegerät", "charger", "magsafe", "charging"]),
        ("adapter", ["adapter", "power adapter", "netzteil"]),
        ("cases", ["case", "cover", "hülle", "crossbody", "popsocket"]),
        ("kopfhoerer", ["kopfhörer", "headphone", "earpods"]),
        ("design", ["apple pencil", "pencil", "illustration"]),
        ("lautsprecher", ["speaker", "lautsprecher"]),
        ("displays", ["display", "monitor"]),
    ]
    for cid, terms in rules:
        if any(term in n for term in terms): return cid
    return "sonstiges"


def refresh_accessories(data):
    try:
        all_html = get(ACCESSORIES_ALL)
        apple_html = get(ACCESSORIES_APPLE)
    except Exception as exc:
        print("accessories root failed", exc)
        return
    all_filters = accessory_filter_links(all_html, ACCESSORIES_ALL)
    apple_filters = accessory_filter_links(apple_html, ACCESSORIES_APPLE)

    all_cards = accessory_cards(all_html, ACCESSORIES_ALL)
    apple_cards = accessory_cards(apple_html, ACCESSORIES_APPLE)
    category_for_url = {}

    # Fetch each actual filter link discovered from Apple's own navigation. This follows Apple's
    # current category structure instead of hard-coding URL slugs.
    for cid, url in all_filters.items():
        if cid == "displays":
            continue  # displays are a separate top-level section in this app
        try:
            cards = accessory_cards(get(url), url)
            all_cards.update(cards)
            for href in cards: category_for_url[href] = cid
        except Exception as exc:
            print("accessory filter failed", cid, exc)
    apple_urls = set(apple_cards)
    for cid, url in apple_filters.items():
        if cid == "displays":
            continue
        try:
            cards = accessory_cards(get(url), url)
            apple_urls.update(cards)
            # Apple-only pages can also provide cleaner product names/images.
            apple_cards.update(cards)
        except Exception as exc:
            print("apple accessory filter failed", cid, exc)

    existing = {p.get("sourceUrl", "").split("?")[0]: p for p in data.get("products", []) if p.get("category") == "accessories"}
    seen = set()
    for href, card in all_cards.items():
        # AirPods, HomePods and Displays have their own top-level categories here.
        lname = card["name"].lower()
        if "airpods" in lname or "homepod" in lname or "studio display" in lname:
            continue
        cid = category_for_url.get(href) or category_guess_from_name(card["name"])
        if cid == "displays":
            continue
        p = existing.get(href)
        brand = "apple" if (href in apple_urls or "beats" in lname) else "third-party"
        if p is None:
            sku = href.split("/product/")[-1].split("/")[0] if "/product/" in href else slugify(card["name"])
            p = {
                "id": f"acc-{slugify(sku)}",
                "category": "accessories",
                "subcategory": cid,
                "seriesKey": "accessory-" + slugify(card["name"]),
                "generation": 0,
                "name": card["name"],
                "subtitle": "",
                "sourceUrl": href,
                "imageUrl": card.get("imageUrl", ""),
                "brandType": brand,
                "autoDiscovered": True,
                "tags": [cid],
                "variants": [{"id": "one", "label": "Standard", "gross": card["gross"], "fee": 0}],
            }
            data.setdefault("products", []).append(p)
            existing[href] = p
        else:
            p["name"] = card["name"] or p.get("name")
            p["subcategory"] = cid
            p["brandType"] = brand
            p.setdefault("tags", [])
            if cid not in p["tags"]: p["tags"].append(cid)
            if card.get("imageUrl"): p["imageUrl"] = card["imageUrl"]
            if len(p.get("variants", [])) == 1:
                p["variants"][0]["gross"] = card["gross"]
        seen.add(p["id"])

    # Only mark automatically discovered accessories as unavailable; never delete them from history.
    if len(seen) >= 5:
        for p in data.get("products", []):
            if p.get("category") == "accessories" and p.get("autoDiscovered"):
                p["available"] = p["id"] in seen


def refresh_simple_images(data):
    # Accessory card images may be missing; fetch a reasonable number of product pages and extract
    # their OG image. Capped to keep the scheduled job polite.
    todo = [p for p in data.get("products", []) if p.get("category") == "accessories" and p.get("available", True) and not p.get("imageUrl")]
    for p in todo[:30]:
        try:
            html = get(p["sourceUrl"])
            img = apple_image(html, p["sourceUrl"])
            if img: p["imageUrl"] = img
        except Exception:
            pass


def archive_if_needed(old, new):
    HISTORY.mkdir(parents=True, exist_ok=True)
    old_sig, new_sig = signature(old), signature(new)
    day = datetime.now().astimezone().strftime("%Y-%m-%d")
    daily = HISTORY / f"{day}-daily.json"
    if not daily.exists():
        snap = deepcopy(old); snap["snapshotAt"] = now_iso(); dump(daily, snap)
    if old_sig != new_sig:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S%z")
        snap = deepcopy(old); snap["snapshotAt"] = now_iso(); dump(HISTORY / f"{stamp}-before-change.json", snap)
    return old_sig != new_sig


def update_summary(summary, old, new):
    summary.setdefault("series", {})
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    for p in old.get("products", []) + new.get("products", []):
        if not p.get("variants"):
            continue
        key = p.get("seriesKey") or p["id"]
        arr = summary["series"].setdefault(key, [])
        sig = json.dumps(p.get("variants", []), sort_keys=True, ensure_ascii=False)
        if not any(x.get("id") == p["id"] and json.dumps(x.get("variants", []), sort_keys=True, ensure_ascii=False) == sig for x in arr):
            arr.append({
                "id": p["id"], "name": p["name"], "generation": p.get("generation", 0),
                "date": today, "variants": p.get("variants", []), "source": "Apple Store DE",
            })
    summary["updatedAt"] = now_iso()
    return summary


def main():
    old = load(CURRENT)
    new = deepcopy(old)
    new["lastCheckedAt"] = now_iso()
    refresh_levies(new)
    discover_models(new)
    refresh_product_details(new)
    refresh_accessories(new)
    refresh_simple_images(new)

    changed = archive_if_needed(old, new)
    if changed:
        new["updatedAt"] = now_iso()
        new["lastChangedAt"] = new["updatedAt"]
    else:
        new.setdefault("lastChangedAt", old.get("lastChangedAt") or old.get("updatedAt"))
    dump(CURRENT, new)  # lastCheckedAt is intentionally persisted even when prices did not change

    summary = load(SUMMARY) if SUMMARY.exists() else {"series": {}}
    summary = update_summary(summary, old, new)
    dump(SUMMARY, summary)
    print("checked=", new["lastCheckedAt"], "changed=", changed, "products=", len(new.get("products", [])))


if __name__ == "__main__":
    main()
