from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / 'current.json'
SUMMARY = ROOT / 'history-summary.json'
HISTORY = ROOT / 'price-history'
ACCESSORY_AUDIT = ROOT / 'accessory-audit-2026-09-18.json'

S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 AppleRabattBot/7.0',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.5',
})

PRICE_RE = re.compile(r'(?<!\d)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?\s*€')
ZPUE = {
    'iphone': ('https://www.zpue.de/produkte-tarife/mobiltelefone.html', 5.00),
    'ipad': ('https://www.zpue.de/produkte-tarife/tablets.html', 7.00),
    'mac': ('https://www.zpue.de/produkte-tarife/pcs.html', 10.55),
    'watch': ('https://www.zpue.de/produkte-tarife/smartwatches.html', 1.20),
}
LANDINGS = {
    'iphone': 'https://www.apple.com/de/shop/buy-iphone',
    'ipad': 'https://www.apple.com/de/shop/buy-ipad',
    'mac': 'https://www.apple.com/de/shop/buy-mac',
    'displays': 'https://www.apple.com/de/shop/buy-mac',
    'watch': 'https://www.apple.com/de/shop/buy-watch',
    'vision': 'https://www.apple.com/de/shop/buy-vision',
    'airpods': 'https://www.apple.com/de/shop/buy-airpods',
    'tvhome': 'https://www.apple.com/de/shop/smart-home/accessories',
}
ACCESS = 'https://www.apple.com/de/shop/accessories/all'
MADE = 'https://www.apple.com/de/shop/accessories/all/made-by-apple'

# Fixed public Apple category URLs. We do not depend on the navigation labels being
# present in one particular HTML rendering.
ACCESSORY_CATEGORIES = {
    'mice-keyboards': ACCESS + '/mice-keyboards',
    'health-fitness': ACCESS + '/health-fitness',
    'chargers-adapters': ACCESS + '/chargers-adapters',
    'headphones-speakers': ACCESS + '/headphones-speakers',
    'software': ACCESS + '/software',
    'office': ACCESS + '/office',
    'storage': ACCESS + '/drives-storage',
    'content': ACCESS + '/content-creation',
    'gaming': ACCESS + '/gaming',
    'cases-protection': ACCESS + '/cases-protection',
    'smart-home': ACCESS + '/homekit',
    'airtag': ACCESS + '/airtag',
    'beats': ACCESS + '/beats',
}
ACCESSORY_PRODUCTS = {
    'iphone': ACCESS + '/iphone',
    'ipad': ACCESS + '/ipad',
    'mac': ACCESS + '/mac',
    'watch': ACCESS + '/watch',
    'vision': ACCESS + '/vision',
    'airpods': ACCESS + '/airpods',
    'tvhome': ACCESS + '/tv-home',
    'airtag': ACCESS + '/airtag',
    'beats': ACCESS + '/beats',
}

CAT_LABELS = {
    'mäuse & tastaturen': 'mice-keyboards',
    'gesundheit & fitness': 'health-fitness',
    'ladegeräte & adapter': 'chargers-adapters',
    'kopfhörer & lautsprecher': 'headphones-speakers',
    'software': 'software',
    'zubehör fürs büro': 'office',
    'festplatten & speicher': 'storage',
    'content erstellung': 'content',
    'gaming': 'gaming',
    'hüllen & schutz': 'cases-protection',
    'smart home zubehör': 'smart-home',
    'airtag': 'airtag',
    'beats': 'beats',
}
PRODUCT_LABELS = {
    'iphone': 'iphone', 'ipad': 'ipad', 'mac': 'mac', 'apple watch': 'watch',
    'apple vision pro': 'vision', 'airpods': 'airpods', 'tv & home': 'tvhome',
    'airtag': 'airtag', 'beats': 'beats'
}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def clean(s: str | None) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def slug(s: str) -> str:
    return re.sub(
        r'[^a-z0-9]+', '-',
        s.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    ).strip('-')[:95]


def load(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def dump(p: Path, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def get(url: str) -> str:
    last = None
    for i in range(3):
        try:
            r = S.get(url, timeout=35)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(1 + i)
    raise last


def soup(h: str):
    return BeautifulSoup(h, 'html.parser')


def price(s: str | None):
    m = PRICE_RE.search(clean(s))
    return float(m.group(1).replace('.', '') + '.' + (m.group(2) or '00')) if m else None


def all_prices(s: str | None):
    out = []
    for m in PRICE_RE.finditer(clean(s)):
        out.append(float(m.group(1).replace('.', '') + '.' + (m.group(2) or '00')))
    return out


def image(h: str, u: str):
    x = soup(h)
    for attrs in ({'property': 'og:image'}, {'name': 'twitter:image'}):
        t = x.find('meta', attrs=attrs)
        if t and t.get('content'):
            return urljoin(u, t['content'])
    for im in x.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-srcset')
        if src:
            src = src.split(',')[0].strip().split(' ')[0]
            if any(k in src for k in ('storeimages', 'store.storeimages', '/is/image/')):
                return urljoin(u, src)
    return ''


def signature(d):
    k = {x: d.get(x) for x in ('vat', 'levies', 'categories', 'products')}
    return hashlib.sha256(json.dumps(k, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fee_for(d, cat: str) -> float:
    return float(d.get('levies', {}).get(cat, {}).get('amount', 0) or 0)


def refresh_levies(d):
    for k, (url, fallback) in ZPUE.items():
        amount = fallback
        try:
            txt = clean(soup(get(url)).get_text(' ', strip=True))
            vals = [float(a.replace(',', '.')) for a in re.findall(r'(\d{1,2},\d{2})\s*€', txt)]
            if vals:
                amount = min(vals, key=lambda v: abs(v - fallback))
        except Exception as e:
            print('levy', k, repr(e))
        d.setdefault('levies', {}).setdefault(k, {})['amount'] = amount
        for p in d.get('products', []):
            if p.get('category') == k:
                for v in p.get('variants', []):
                    v['fee'] = amount


def model_cards(html: str, url: str):
    s = soup(html)
    out, seen = [], set()
    for a in s.find_all('a', href=True):
        href = urljoin(url, a['href']).split('?')[0]
        if '/de/shop/buy-' not in href:
            continue
        box = a
        txt = clean(a.get('aria-label') or a.get('title') or a.get_text(' ', strip=True))
        for _ in range(7):
            box = getattr(box, 'parent', None)
            if not box:
                break
            bt = clean(box.get_text(' ', strip=True))
            if '€' in bt and len(bt) < 1200:
                txt = bt
                break
        pr = price(txt)
        if pr is None:
            continue
        name = clean(a.get('aria-label') or a.get('title') or a.get_text(' ', strip=True))
        if not name or name.lower() in ('kaufen', 'mehr erfahren', 'genauer ansehen'):
            h = box.find(['h2', 'h3', 'h4']) if box else None
            if h:
                name = clean(h.get_text(' ', strip=True))
        name = re.sub(r'\s+(Kaufen|Genauer ansehen|Vorbestellen).*', '', name, flags=re.I).strip()
        if not name or len(name) > 120:
            continue
        key = (name.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, pr, href))
    return out


def family_meta(cat: str, name: str):
    n = name.lower()
    generation = 0
    nums = re.findall(r'(?<!\d)(\d{1,2})(?!\d)', name)
    if nums:
        # iPhone 17, Watch 11, AirPods 4 etc.; sizes are filtered below by family rules.
        generation = int(nums[0])

    if cat == 'iphone':
        if 'pro max' in n:
            return 'pro', 'iphone-pro-max', generation
        if 'pro' in n:
            return 'pro', 'iphone-pro', generation
        if 'air' in n:
            return 'air', 'iphone-air', generation
        if re.search(r'\be\b', n) or re.search(r'\d+e\b', n):
            return 'standard', 'iphone-e', generation
        if 'plus' in n:
            return 'standard', 'iphone-standard-plus', generation
        return 'standard', 'iphone-standard', generation
    if cat == 'ipad':
        if 'pro' in n: return 'pro', 'ipad-pro', generation
        if 'air' in n: return 'air', 'ipad-air', generation
        if 'mini' in n: return 'mini', 'ipad-mini', generation
        return 'standard', 'ipad-standard', generation
    if cat == 'watch':
        if 'herm' in n and 'ultra' in n: return 'hermes', 'watch-hermes-ultra', generation
        if 'herm' in n: return 'hermes', 'watch-hermes', generation
        if 'ultra' in n: return 'ultra', 'watch-ultra', generation
        if re.search(r'\bse\b', n): return 'se', 'watch-se', generation
        return 'series', 'watch-series', generation
    if cat == 'airpods':
        if 'pro' in n: return 'pro', 'airpods-pro', generation
        if 'max' in n: return 'max', 'airpods-max', generation
        return 'standard', 'airpods', generation
    if cat == 'mac':
        if 'macbook' in n:
            if 'air' in n: return 'macbooks', 'macbook-air', generation
            if 'pro' in n: return 'macbooks', 'macbook-pro', generation
            if 'neo' in n: return 'macbooks', 'macbook-neo', generation
            return 'macbooks', 'macbook', generation
        if 'mini' in n: return 'desktop', 'mac-mini', generation
        if 'studio' in n: return 'desktop', 'mac-studio', generation
        if 'imac' in n: return 'desktop', 'imac', generation
        return 'desktop', slug(name), generation
    if cat == 'displays':
        return ('xdr' if 'xdr' in n else 'studio'), ('studio-display-xdr' if 'xdr' in n else 'studio-display'), generation
    if cat == 'tvhome':
        if 'homepod mini' in n: return 'homepod', 'homepod-mini', generation
        if 'homepod' in n: return 'homepod', 'homepod', generation
        return 'tv', 'apple-tv', generation
    if cat == 'vision':
        return 'standard', 'vision-pro', generation
    return 'standard', slug(name), generation


def discover_new_models(d):
    existing_urls = {p.get('sourceUrl', '').rstrip('/'): p for p in d.get('products', []) if p.get('sourceUrl')}
    existing_names = {p.get('name', '').lower(): p for p in d.get('products', [])}
    for cat, url in LANDINGS.items():
        try:
            cards = model_cards(get(url), url)
        except Exception as e:
            print('landing', cat, repr(e))
            continue
        for name, pr, href in cards:
            p = existing_urls.get(href.rstrip('/')) or existing_names.get(name.lower())
            if p is None:
                lname0 = name.lower()
                p = next((x for x in d.get('products', []) if x.get('category') == cat and x.get('name', '').lower() in lname0), None)
            if p and p.get('variants'):
                # Record the observation but do not silently replace a verified configuration.
                p['observedLandingGross'] = pr
                p['observedLandingAt'] = now()
                continue

            lname = name.lower()
            if cat == 'iphone' and 'iphone' not in lname: continue
            if cat == 'ipad' and 'ipad' not in lname: continue
            if cat == 'watch' and 'watch' not in lname: continue
            if cat == 'airpods' and 'airpods' not in lname: continue
            if cat == 'vision' and 'vision' not in lname: continue
            if cat == 'mac' and not any(x in lname for x in ('macbook', 'imac', 'mac mini', 'mac studio')): continue
            if cat == 'displays' and 'display' not in lname: continue
            if cat == 'tvhome' and not any(x in lname for x in ('homepod', 'apple tv')): continue

            sub, series_key, generation = family_meta(cat, name)
            pid = 'auto-' + slug(name)
            if any(x.get('id') == pid for x in d.get('products', [])):
                continue
            d['products'].append({
                'id': pid, 'category': cat, 'subcategory': sub, 'seriesKey': series_key,
                'generation': generation, 'name': name, 'subtitle': 'Neu erkannt',
                'sourceUrl': href, 'imageUrl': '', 'brandType': 'apple',
                'tags': ['automatisch erkannt'], 'autoConfig': True,
                'variants': [{'id': 'base', 'label': 'Basismodell', 'gross': pr, 'fee': fee_for(d, cat)}]
            })
            print('new model', name, pr)


def config_links(h: str, base: str):
    s = soup(h)
    basep = urlparse(base).path.rstrip('/')
    out = []
    for a in s.find_all('a', href=True):
        u = urljoin(base, a['href']).split('?')[0]
        path = urlparse(u).path.rstrip('/')
        if path.startswith(basep + '/') and len(path) > len(basep) + 3 and u not in out:
            out.append(u)
    return out


def parse_config_page(h: str, u: str, p: dict):
    s = soup(h)
    h1 = clean(s.find('h1').get_text(' ', strip=True)) if s.find('h1') else ''
    tt = clean(s.find('title').get_text(' ', strip=True)) if s.find('title') else ''
    title = tt if (len(tt) > len(h1) + 12 or ' GB ' in tt or ' TB ' in tt or ',' in tt) else (h1 or tt)
    main = s.find('main') or s
    text = clean(main.get_text(' ', strip=True))
    floor = min((float(v.get('gross', 0)) for v in p.get('variants', []) if v.get('gross')), default=0)
    threshold = max(40, floor * .70)
    prices = [x for x in all_prices(text) if x >= threshold]
    if not prices:
        return None
    pr = prices[0]
    opts = {}

    # Size. Quoted inch notation first, then textual Zoll/mm.
    m = re.search(r'(?<!\d)(11|13|14|15|16|24|27|32)["”]', title)
    if m: opts['Größe'] = m.group(1) + ' Zoll'
    else:
        m = re.search(r'(?<!\d)(40|42|44|46|49)\s*mm', title, re.I)
        if m: opts['Größe'] = m.group(1) + ' mm'
        else:
            m = re.search(r'(?<!\d)(11|13|14|15|16|24|27|32)[- ]?Zoll', title, re.I)
            if m: opts['Größe'] = m.group(1) + ' Zoll'

    # Memory and storage.
    m = re.search(r'(8|16|24|32|36|48|64|96|128|192|256|512)\s*GB\s+(?:Arbeitsspeicher|gemeinsamer Arbeitsspeicher)', title, re.I)
    if m: opts['Arbeitsspeicher'] = m.group(1) + ' GB'
    m = re.search(r'(?<!\d)(128|256|512)\s*GB\s+(?:SSD\s*)?(?:Speicher|SSD)', title, re.I)
    if m: opts['Speicher'] = m.group(1) + ' GB'
    m2 = re.search(r'(?<!\d)(1|2|4|8|16)\s*TB\s+(?:SSD\s*)?(?:Speicher|SSD)', title, re.I)
    if m2: opts['Speicher'] = m2.group(1) + ' TB'

    for token in ['M6', 'M5 Ultra', 'M5 Max', 'M5 Pro', 'M5', 'M4', 'A18 Pro']:
        if token.lower() in title.lower():
            opts['Chip'] = token
            break
    if 'Nanotextur' in title:
        opts['Glas'] = 'Nanotexturglas'
    elif p.get('category') in ('mac', 'displays') and any(x in title for x in ('Display', 'MacBook', 'iMac')):
        opts['Glas'] = 'Standardglas'

    if 'Cellular' in title:
        opts['Verbindung'] = 'GPS + Cellular' if p.get('category') == 'watch' else 'Wi-Fi + Cellular'
    elif p.get('category') == 'watch' and 'GPS' in title:
        opts['Verbindung'] = 'GPS'

    # Watch material and band information are unusually useful for comparison.
    if p.get('category') == 'watch':
        if 'Aluminium' in title: opts['Material'] = 'Aluminium'
        elif 'Titan' in title: opts['Material'] = 'Titan'
        if ',' in title:
            tail = title.split(',')[-1]
            tail = re.sub(r'\s+kaufen.*', '', tail, flags=re.I).strip()
            if tail and len(tail) < 80: opts['Armband'] = tail

    label = ' · '.join(opts.values()) if opts else re.sub(r'\s+kaufen.*', '', title, flags=re.I)[:130]
    return {
        'id': 'auto-' + slug(u.split('/')[-1]), 'label': label or 'Konfiguration',
        'gross': pr, 'fee': float(p.get('variants', [{}])[0].get('fee', 0)),
        'options': opts, 'sourceUrl': u
    }


def _variant_identity(v: dict):
    opts = tuple(sorted((v.get('options') or {}).items()))
    if opts:
        return ('opts', opts)
    return ('label', clean(v.get('label')).lower())


def deep_configs(d):
    for p in d.get('products', []):
        if not p.get('autoConfig') or not p.get('sourceUrl'):
            continue
        try:
            h = get(p['sourceUrl'])
            links = config_links(h, p['sourceUrl'])
        except Exception as e:
            print('config root', p.get('name'), repr(e))
            continue

        cap = 120 if p.get('category') == 'watch' else 85
        found = {}
        for u in links[:cap]:
            try:
                v = parse_config_page(get(u), u, p)
                if v:
                    found[_variant_identity(v)] = v
            except Exception:
                pass

        if found:
            old = list(p.get('variants', []))
            floor = min((float(v.get('gross', 1e12)) for v in old), default=0)
            merged = {_variant_identity(v): deepcopy(v) for v in old}
            for ident, v in found.items():
                if float(v.get('gross', 0)) + .01 < floor:
                    continue
                if ident in merged:
                    # Keep exact EPP/reference metadata but refresh public gross/source details.
                    base = merged[ident]
                    old_gross = base.get('gross')
                    base['gross'] = v['gross']
                    if old_gross != v['gross']:
                        base.pop('epp', None)
                        base.pop('eppBaseGross', None)
                    base['sourceUrl'] = v.get('sourceUrl', base.get('sourceUrl'))
                    if v.get('label'): base['label'] = v['label']
                    base['options'] = v.get('options') or base.get('options', {})
                else:
                    merged[ident] = v
            p['variants'] = sorted(merged.values(), key=lambda x: (float(x.get('gross', 0)), x.get('label', '')))

        im = image(h, p['sourceUrl'])
        # Local PNGs are curated fallbacks. A fresh Apple image may replace only a remote/empty image.
        if im and (not p.get('imageUrl') or str(p.get('imageUrl')).startswith('http')):
            p['imageUrl'] = im


def acc_links(h: str, base: str, labels=CAT_LABELS):
    s = soup(h)
    out = {}
    for a in s.find_all('a', href=True):
        lab = clean(a.get_text(' ', strip=True)).lower()
        if lab in labels:
            out[labels[lab]] = urljoin(base, a['href'])
    return out


def norm_name(s: str | None):
    t = clean(s).lower()
    t = t.replace('‑','-').replace('–','-').replace('—','-').replace('™','').replace('®','')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def facet_links(h: str, base: str, max_links=90):
    """Collect useful single-filter pages (types/brands/features) for exhaustive accessory discovery.

    Apple category landing pages often expose only the first product grid. Individual facet pages
    expose additional SKUs. We intentionally avoid deep combination URLs and old device-compatibility
    filters where possible to keep the scan fast enough for GitHub Actions.
    """
    s = soup(h)
    bp = urlparse(base).path.rstrip('/')
    out = []
    skip_words = ('iphone ', 'ipad ', 'macbook', 'mac mini', 'mac studio', 'mac pro', 'imac',
                  'apple vision', 'airpods ', 'apple tv', 'ipod ', 'generation', 'retina')
    color_words = {'schwarz','blau','braun','pink','violett','rot','weiß','weiss','gelb','grün','gruen','orange','mehrfarbig'}
    for a in s.find_all('a', href=True):
        lab = clean(a.get_text(' ', strip=True))
        if not lab or len(lab) > 80:
            continue
        low = lab.lower()
        if any(w in low for w in skip_words) or low in color_words:
            continue
        u = urljoin(base, a['href']).split('?')[0]
        p = urlparse(u)
        if p.netloc and p.netloc != urlparse(base).netloc:
            continue
        path = p.path.rstrip('/')
        if not path.startswith(bp + '/') or '/shop/product/' in path:
            continue
        rest = path[len(bp)+1:]
        if not rest or rest.count('/') > 0:
            continue
        if u not in out:
            out.append(u)
        if len(out) >= max_links:
            break
    return out


def infer_accessory_subcat(name: str):
    n = norm_name(name)
    if any(x in n for x in ('case','cover','folio','wallet','hülle','huelle','bumper','grip','sling','organizer','crossbody','trageband','ohrpolster','ohreinsätze','ohreinsaetze')):
        return 'cases-protection'
    if any(x in n for x in ('lade','charger','powerbank','power adapter','netzteil','adapter','kabel','dock','batterie','battery','magsafe','usb-c','thunderbolt','airfly')):
        return 'chargers-adapters'
    if any(x in n for x in ('keyboard','tastatur','mouse','maus','trackpad','combo touch','keys-to-go','rugged folio')):
        return 'mice-keyboards'
    if any(x in n for x in ('airpods','earpods','beats','kopfhörer','kopfhoerer','lautsprecher','pill')):
        return 'headphones-speakers'
    if any(x in n for x in ('ssd','festplatte','raid','drive','speicher')):
        return 'storage'
    if any(x in n for x in ('camera','kamera','stativ','tripod','pencil','drucker','micro','mic','selfie','pro dock','prodock')):
        return 'content'
    if any(x in n for x in ('withings','hidrate','gesundheit','blutdruck','körperwaage','koerperwaage')):
        return 'health-fitness'
    if any(x in n for x in ('controller','gaming','dualsense','backbone','steelseries')):
        return 'gaming'
    if any(x in n for x in ('homekit','matter','smart lock','hue','nanoleaf','eve ','aqara','nuki','thermo','weather','water guard')):
        return 'smart-home'
    if any(x in n for x in ('microsoft','filemaker')):
        return 'software'
    if 'airtag' in n:
        return 'airtag'
    if 'beats' in n:
        return 'beats'
    return 'office'


def plausible_accessory_price(name: str, cat: str, value, old_value=None):
    """Reject prices that clearly belong to the parent device/financing block instead of the accessory.

    Apple accessory pages can contain the price of a compatible iPhone/Mac in addition to the
    accessory itself.  The previous crawler used the largest early euro amount and could therefore
    turn a 45 € charger into 949 €.  This guard is deliberately conservative: when a value looks
    suspicious we keep the previous verified price and let the detail-page parser try another amount.
    """
    try:
        v = float(value)
    except Exception:
        return False
    if not (5 <= v <= 5000):
        return False
    n = norm_name(name)
    # Tight ceilings for product types whose Apple Store prices are nowhere near a device price.
    if any(x in n for x in ('case', 'cover', 'hülle', 'huelle', 'folio')) and v > 250:
        return False
    if any(x in n for x in ('crossbody', 'handgelenk', 'wallet', 'band')) and v > 300:
        return False
    if any(x in n for x in ('kabel', 'cable', 'power adapter', 'netzteil', 'adapter', 'ladegerät', 'ladegeraet', 'charger', 'magsafe')) and v > 500:
        return False
    if 'poliertuch' in n and v > 100:
        return False
    # Category-level ceilings are intentionally generous to allow premium third-party products.
    ceilings = {
        'cases-protection': 350, 'chargers-adapters': 750, 'airtag': 500, 'beats': 1000,
        'mice-keyboards': 1200, 'headphones-speakers': 1500, 'content': 2500,
        'health-fitness': 2500, 'gaming': 1500, 'smart-home': 2500, 'office': 2500,
        'software': 5000, 'storage': 5000
    }
    if v > ceilings.get(cat, 2500):
        return False
    if old_value not in (None, ''):
        try:
            old = float(old_value)
            if old >= 5:
                ratio = v / old
                # Normal price changes are fine; 45 -> 949 or 59 -> 949 are not.
                if ratio > 3.0 or ratio < 0.25:
                    return False
        except Exception:
            pass
    return True


def load_accessory_audit():
    try:
        a = load(ACCESSORY_AUDIT)
        return a, {norm_name(x) for x in a.get('knownUniqueNames', [])}
    except Exception:
        return {}, set()


def acc_cards(h: str, url: str, allow_missing_price=False):
    s = soup(h)
    out = {}
    for a in s.find_all('a', href=True):
        href = urljoin(url, a['href']).split('?')[0]
        if '/shop/product/' not in href:
            continue
        box = a
        txt = clean(a.get('aria-label') or a.get('title') or a.get_text(' ', strip=True))
        for _ in range(8):
            if not box:
                break
            bt = clean(box.get_text(' ', strip=True))
            if '€' in bt and len(bt) < 1800:
                txt = bt
                break
            box = box.parent
        pr = price(txt)
        if pr is None and not allow_missing_price:
            continue
        name = ''
        if box:
            hh = box.find(['h2', 'h3', 'h4'])
            if hh:
                name = clean(hh.get_text(' ', strip=True))
        if not name:
            name = clean(a.get('aria-label') or a.get('title') or a.get_text(' ', strip=True))
        name = re.sub(r'\s+(kaufen|anzeigen|weitere infos).*', '', name, flags=re.I).strip()
        if len(name) < 2 or len(name) > 190:
            continue
        img = ''
        if box:
            im = box.find('img')
            src = (im.get('src') or im.get('data-src')) if im else ''
            if src:
                img = urljoin(url, src.split(',')[0].strip().split(' ')[0])
        out[href] = (name, pr, img)
    return out


def accessory_detail(href: str, fallback_name: str = '', fallback_img: str = ''):
    try:
        h = get(href)
    except Exception:
        return fallback_name, None, fallback_img
    s = soup(h)
    title = clean((s.find('h1') or s.find('title')).get_text(' ', strip=True)) if (s.find('h1') or s.find('title')) else fallback_name
    title = re.sub(r'\s+[-–]\s+Apple.*$', '', title).strip()
    cat = infer_accessory_subcat(title or fallback_name)

    # Gather candidates in order of confidence.  Crucially, never choose the *largest* early
    # price: device prices and trade-in values can appear on an accessory page too.
    candidates = []
    for attrs in ({'property':'product:price:amount'}, {'itemprop':'price'}, {'name':'price'}):
        t = s.find('meta', attrs=attrs)
        if t and t.get('content'):
            raw = str(t.get('content')).strip()
            try:
                val = float(raw.replace('.', '').replace(',', '.')) if ',' in raw else float(raw)
                candidates.append(val)
            except Exception:
                pass
    for tag in s.find_all(attrs={'itemprop':'price'}):
        raw = tag.get('content') or tag.get_text(' ', strip=True)
        val = price(raw)
        if val is not None:
            candidates.append(val)
    for sc in s.find_all('script', attrs={'type':'application/ld+json'}):
        try:
            obj = json.loads(sc.string or '{}')
            stack = obj if isinstance(obj, list) else [obj]
            for node in stack:
                if isinstance(node, dict):
                    off = node.get('offers')
                    offers = off if isinstance(off, list) else [off] if isinstance(off, dict) else []
                    for offer in offers:
                        if isinstance(offer, dict) and offer.get('price') is not None:
                            candidates.append(float(str(offer['price']).replace(',', '.')))
        except Exception:
            pass
    text_main = clean((s.find('main') or s).get_text(' ', strip=True))
    candidates.extend(all_prices(text_main))

    pr = next((v for v in candidates if plausible_accessory_price(title or fallback_name, cat, v)), None)
    return title or fallback_name, pr, image(h, href) or fallback_img

def looks_apple_product(name: str, href: str, made_hrefs: set[str]):
    n = name.lower()
    if href in made_hrefs or 'beats' in n:
        return True
    return n.startswith(('apple ', 'magic ', 'airtag', 'poliertuch', 'siri remote', 'studio display', 'usb-c auf ', 'thunderbolt ', 'magsafe ', 'power adapter'))


def refresh_accessories(d):
    try:
        allh = get(ACCESS)
    except Exception as e:
        print('access root', repr(e))
        return

    # Merge fixed URLs with whatever Apple currently exposes in its nav.
    filters = dict(ACCESSORY_CATEGORIES)
    filters.update(acc_links(allh, ACCESS, CAT_LABELS))
    productfilters = dict(ACCESSORY_PRODUCTS)
    productfilters.update(acc_links(allh, ACCESS, PRODUCT_LABELS))

    made_hrefs = set()
    try:
        madeh = get(MADE)
        made_hrefs.update(acc_cards(madeh, MADE, True))
        madefilters = acc_links(madeh, MADE, CAT_LABELS)
        for _, u in madefilters.items():
            try:
                made_hrefs.update(acc_cards(get(u), u, True))
            except Exception:
                pass
    except Exception as e:
        print('made-by-apple', repr(e))

    cards = {}
    catfor = {}
    compatfor = {}
    audit, known_names = load_accessory_audit()
    d['accessoryCatalogAudit'] = {
        'auditedAt': audit.get('auditedAt', '2026-09-18'),
        'directCategoryUniqueCount': int(audit.get('categoryPageUniqueCount', 0) or 0),
        'knownMinimumUniqueCount': int(audit.get('knownMinimumUniqueCount', 0) or 0),
        'note': audit.get('note', '')
    }

    # Each public category page is queried directly. Then useful one-filter facet pages
    # (product type / brand / feature) are crawled in parallel. This is what turns the
    # 30-card landing pages into a much more complete store inventory.
    facet_jobs = []
    for cat, u in filters.items():
        try:
            h = get(u)
            cc = acc_cards(h, u, True)
            cards.update(cc)
            for x in cc:
                catfor[x] = cat
            for fu in facet_links(h, u):
                facet_jobs.append((cat, fu))
        except Exception as e:
            print('acc cat', cat, repr(e))
    if facet_jobs:
        with ThreadPoolExecutor(max_workers=14) as ex:
            futs = {ex.submit(get, u):(cat,u) for cat,u in facet_jobs[:650]}
            for fut in as_completed(futs):
                cat,u = futs[fut]
                try:
                    cc = acc_cards(fut.result(), u, True)
                    cards.update(cc)
                    for x in cc:
                        catfor.setdefault(x, cat)
                except Exception:
                    pass

    # Device filters are used for search compatibility tags.
    for comp, u in productfilters.items():
        try:
            cc = acc_cards(get(u), u, True)
            cards.update(cc)
            for x in cc:
                compatfor.setdefault(x, set()).add(comp)
        except Exception as e:
            print('acc product', comp, repr(e))

    cards.update(acc_cards(allh, ACCESS, True))

    # The Von-Apple page is also a catalog source, not just a brand-classification helper.
    try:
        made_cards = acc_cards(madeh, MADE, True) if 'madeh' in locals() else {}
        cards.update(made_cards)
    except Exception:
        pass

    existing = {
        p.get('sourceUrl', '').split('?')[0]: p
        for p in d.get('products', [])
        if p.get('category') == 'accessories' and p.get('sourceUrl')
    }
    existing_by_name = {norm_name(p.get('name')):p for p in d.get('products', []) if p.get('category') == 'accessories'}
    seen = set()
    unresolved = []

    for href, (name, pr, img) in cards.items():
        ln = name.lower()
        if any(x in ln for x in ('airpods pro', 'airpods max', 'homepod', 'studio display')):
            continue
        cat = catfor.get(href) or infer_accessory_subcat(name)
        brand = 'apple' if looks_apple_product(name, href, made_hrefs) else 'third-party'
        p = existing.get(href) or existing_by_name.get(norm_name(name))
        old_price = p.get('variants', [{}])[0].get('gross') if p and p.get('variants') else None
        if pr is None or not plausible_accessory_price(name, cat, pr, old_price):
            unresolved.append((href, name, img))
            continue
        if p is None:
            p = {
                'id': 'acc-' + slug(href.split('/product/')[-1]), 'category': 'accessories',
                'subcategory': cat, 'seriesKey': 'acc-' + slug(name), 'generation': 0,
                'name': name, 'subtitle': '', 'sourceUrl': href, 'imageUrl': img,
                'brandType': brand, 'tags': [cat, name], 'compat': sorted(compatfor.get(href, set())),
                'autoDiscovered': True, 'variants': [{'id': 'one', 'label': 'Standard', 'gross': pr, 'fee': 0}]
            }
            d['products'].append(p)
            existing[href] = p
        else:
            p.update({'name': name, 'subcategory': cat, 'brandType': brand, 'available': True, 'sourceUrl': href})
            p.setdefault('tags', [])
            p['compat'] = sorted(set(p.get('compat', [])) | compatfor.get(href, set()))
            if img and (not p.get('imageUrl') or str(p.get('imageUrl')).startswith('http')):
                p['imageUrl'] = img
            if p.get('variants'):
                old = p['variants'][0]
                if abs(float(old.get('gross', 0)) - pr) > .001:
                    old['gross'] = pr
                    old.pop('epp', None)
                    old.pop('eppBaseGross', None)
        seen.add(p['id'])

    # If Apple rendered prices only client-side, resolve public product pages. A full
    # catch-up scan runs once per day; between those scans only a small batch of newly seen
    # links is checked. Parallelism keeps the GitHub Action comfortably below its timeout.
    deep_last = d.get('accessoriesDeepAt')
    try:
        deep_age = datetime.now().astimezone() - datetime.fromisoformat(deep_last) if deep_last else timedelta(days=99)
    except Exception:
        deep_age = timedelta(days=99)
    detail_limit = 900 if deep_age >= timedelta(hours=20) else 120
    todo = []
    for href, name, img in unresolved:
        p = existing.get(href)
        if p and p.get('variants') and p['variants'][0].get('gross'):
            seen.add(p['id'])
        else:
            todo.append((href, name, img))
    todo = todo[:detail_limit]
    resolved = []
    if todo:
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = {ex.submit(accessory_detail, href, name, img):(href,name,img) for href,name,img in todo}
            for fut in as_completed(futs):
                href, name, img = futs[fut]
                try:
                    n2, pr, im2 = fut.result()
                    if pr is not None: resolved.append((href,n2,pr,im2))
                except Exception:
                    pass
    for href, n2, pr, im2 in resolved:
        p = existing.get(href) or existing_by_name.get(norm_name(n2))
        ln = n2.lower()
        cat = catfor.get(href) or infer_accessory_subcat(n2)
        brand = 'apple' if looks_apple_product(n2, href, made_hrefs) else 'third-party'
        old_price = p.get('variants', [{}])[0].get('gross') if p and p.get('variants') else None
        if not plausible_accessory_price(n2, cat, pr, old_price):
            continue
        if p is None:
            p = {
                'id': 'acc-' + slug(href.split('/product/')[-1]), 'category': 'accessories',
                'subcategory': cat, 'seriesKey': 'acc-' + slug(n2), 'generation': 0,
                'name': n2, 'subtitle': '', 'sourceUrl': href, 'imageUrl': im2,
                'brandType': brand, 'tags': [cat, n2], 'compat': sorted(compatfor.get(href, set())),
                'autoDiscovered': True, 'variants': [{'id': 'one', 'label': 'Standard', 'gross': pr, 'fee': 0}]
            }
            d['products'].append(p); existing[href] = p
        else:
            p.update({'name': n2, 'subcategory': cat, 'brandType': brand, 'available': True, 'sourceUrl': href})
            if im2 and (not p.get('imageUrl') or str(p.get('imageUrl')).startswith('http')): p['imageUrl'] = im2
            if p.get('variants'):
                old = p['variants'][0]
                if abs(float(old.get('gross', 0)) - pr) > .001:
                    old['gross'] = pr
                    old.pop('epp', None)
                    old.pop('eppBaseGross', None)
                    old.pop('eppBaseGross', None)
        seen.add(p['id'])
    if deep_age >= timedelta(hours=20):
        d['accessoriesDeepAt'] = now()

    if len(seen) > 120:
        for p in d.get('products', []):
            if p.get('category') == 'accessories' and p.get('autoDiscovered'):
                p['available'] = p['id'] in seen
    d['accessoriesLastScanAt'] = now()
    available_acc = [p for p in d.get('products', []) if p.get('category') == 'accessories' and p.get('available', True) and p.get('variants')]
    d['accessoriesDetected'] = len(available_acc)
    detected_names = {norm_name(p.get('name')) for p in available_acc}
    if known_names:
        missing = sorted(known_names - detected_names)
        d['accessoryAuditKnownMatched'] = len(known_names) - len(missing)
        d['accessoryAuditKnownMissing'] = missing
        d['accessoryAuditKnownComplete'] = not missing


def archive(old, new):
    HISTORY.mkdir(exist_ok=True)
    day = datetime.now().astimezone().strftime('%Y-%m-%d')
    daily = HISTORY / f'{day}-daily.json'
    if not daily.exists():
        dump(daily, {**deepcopy(old), 'snapshotAt': now()})
    if signature(old) != signature(new):
        stamp = datetime.now().astimezone().strftime('%Y-%m-%dT%H-%M-%S%z')
        dump(HISTORY / f'{stamp}-before-change.json', {**deepcopy(old), 'snapshotAt': now()})
        return True
    return False


def _add_to_summary(s, snapshot, date_hint=''):
    date = date_hint or str(snapshot.get('snapshotAt') or snapshot.get('lastCheckedAt') or snapshot.get('updatedAt') or '')[:10]
    for p in snapshot.get('products', []):
        if not p.get('variants'):
            continue
        key = p.get('seriesKey') or p['id']
        arr = s.setdefault('series', {}).setdefault(key, [])
        sig = json.dumps(p['variants'], sort_keys=True, ensure_ascii=False)
        if not any(x.get('id') == p['id'] and json.dumps(x.get('variants', []), sort_keys=True, ensure_ascii=False) == sig for x in arr):
            arr.append({
                'id': p['id'], 'name': p['name'], 'generation': p.get('generation', 0),
                'date': date, 'variants': deepcopy(p['variants'])
            })


def update_summary(old, new):
    # Rebuild from retained snapshots as well as the current pair. Therefore even if the
    # summary file was accidentally overwritten during an upload, comparison history returns.
    s = {'series': {}}
    for f in sorted(HISTORY.glob('*.json')):
        try:
            snap = load(f)
            _add_to_summary(s, snap, f.name[:10])
        except Exception:
            pass
    _add_to_summary(s, old)
    _add_to_summary(s, new)
    for arr in s['series'].values():
        arr.sort(key=lambda x: (str(x.get('date', '')), int(x.get('generation', 0) or 0), x.get('name', '')))
    s['updatedAt'] = now()
    dump(SUMMARY, s)


def safe_step(name, fn, d):
    try:
        fn(d)
    except Exception as e:
        # A temporary Apple/ZPÜ HTML/network issue must never take the website offline.
        print('WARNING', name, repr(e))


def main():
    old = load(CURRENT)
    new = deepcopy(old)
    new['lastCheckedAt'] = now()
    new['schemaVersion'] = max(int(new.get('schemaVersion', 1) or 1), 7)
    new['calculationVersion'] = '8.1-accessory-price-guard-first-valid-price'

    safe_step('levies', refresh_levies, new)
    safe_step('models', discover_new_models, new)

    # Deep configuration scan once per day, plus incomplete configurable products.
    hour = datetime.now().astimezone().hour
    if hour < 5 or any(p.get('autoConfig') and len(p.get('variants', [])) <= 2 for p in new.get('products', [])):
        safe_step('configs', deep_configs, new)

    safe_step('accessories', refresh_accessories, new)

    changed = archive(old, new)
    if changed:
        new['updatedAt'] = now()
        new['lastChangedAt'] = new['updatedAt']
    else:
        new.setdefault('lastChangedAt', old.get('lastChangedAt') or old.get('updatedAt'))
    dump(CURRENT, new)
    update_summary(old, new)
    print('checked', new['lastCheckedAt'], 'changed', changed, 'products', len(new.get('products', [])), 'accessories', new.get('accessoriesDetected', 'n/a'))


if __name__ == '__main__':
    main()
