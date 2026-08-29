from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urljoin, unquote
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / 'current.json'
SUMMARY = ROOT / 'history-summary.json'
HISTORY = ROOT / 'price-history'
UA = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36 PriceFinderBot/1.0'}
S = requests.Session(); S.headers.update(UA)
VAT = Decimal('0.19')


ZPUE = {
    'iphone': ('https://www.zpue.de/produkte-tarife/mobiltelefone.html', r'Verbraucher-Mobiltelefone:\s*([0-9]+,[0-9]+)€'),
    'ipad': ('https://www.zpue.de/produkte-tarife/tablets.html', r'Verbraucher-Tablet:\s*([0-9]+,[0-9]+)€'),
    'mac': ('https://www.zpue.de/produkte-tarife/pcs.html', r'Verbraucher-PCs:\s*([0-9]+,[0-9]+)€'),
    'watch': ('https://www.zpue.de/produkte-tarife/smartwatches.html', r'Smartwatches:\s*([0-9]+,[0-9]+)€'),
}

LANDINGS = {
    'iphone':'https://www.apple.com/de/shop/buy-iphone',
    'ipad':'https://www.apple.com/de/shop/buy-ipad',
    'mac':'https://www.apple.com/de/shop/buy-mac',
    'watch':'https://www.apple.com/de/shop/buy-watch',
    'vision':'https://www.apple.com/de/shop/buy-vision',
}

PRICE_RE = re.compile(r'(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*€')
AB_RE = re.compile(r'Ab\s+(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?\s*€', re.I)
STORAGE_RE = re.compile(r'(?<!\d)(256|512)\s*GB|(?<!\d)(1|2|4)\s*TB', re.I)

def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def clean(s): return re.sub(r'\s+', ' ', s or '').strip()
def euro_num(m): return float((m.group(1).replace('.','') + '.' + (m.group(2) or '00')))
def get(url):
    r=S.get(url,timeout=35); r.raise_for_status(); return r.text

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))
def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')

def content_signature(data):
    stripped={'vat':data.get('vat'),'levies':data.get('levies'),'categories':data.get('categories'),'products':data.get('products')}
    return hashlib.sha256(json.dumps(stripped,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def storage_label(text, href=''):
    s=clean(text+' '+unquote(href))
    m=STORAGE_RE.search(s)
    if not m: return None
    return f"{m.group(1)} GB" if m.group(1) else f"{m.group(2)} TB"

def variant_id(label): return label.lower().replace(' ','').replace('gb','gb').replace('tb','tb')

def extract_anchor_prices(html):
    soup=BeautifulSoup(html,'html.parser'); out=[]
    for a in soup.find_all('a', href=True):
        text=clean(a.get_text(' ',strip=True)); href=urljoin('https://www.apple.com',a['href'])
        m=PRICE_RE.search(text)
        if m: out.append((href,text,euro_num(m)))
    return out, soup


def refresh_levies(data):
    """Read the current consumer rates for Gesamtvertragsmitglieder from ZPÜ.
    The regex intentionally searches the whole page and takes the LAST matching amount,
    because ZPÜ first shows the tariff and then the discounted Gesamtvertrag rate.
    """
    for cat,(url,pattern) in ZPUE.items():
        try:
            text=clean(BeautifulSoup(get(url),'html.parser').get_text(' ',strip=True))
            vals=re.findall(pattern,text,re.I)
            if not vals: continue
            amount=float(vals[-1].replace(',','.'))
            data['levies'].setdefault(cat,{})
            data['levies'][cat].update({'amount':amount,'source':f'ZPÜ {cat} · Gesamtvertragsmitglieder','verified':True,'checkedAt':now_iso()})
            for p in data.get('products',[]):
                if p.get('category')==cat:
                    for v in p.get('variants',[]): v['fee']=amount
        except Exception as e:
            print('levy refresh failed',cat,e)

def refresh_iphone(data):
    urls=sorted({p.get('sourceUrl') for p in data['products'] if p['category']=='iphone' and p.get('sourceUrl')})
    parsed=[]
    for url in urls:
        try: anchors,_=extract_anchor_prices(get(url))
        except Exception as e: print('iphone fetch failed',url,e); continue
        route=url.split('/buy-iphone/')[-1].split('/')[0]
        for href,text,price in anchors:
            if f'/buy-iphone/{route}/' not in href: continue
            label=storage_label(text,href)
            if not label: continue
            path=unquote(href).lower()
            screen=None
            sm=re.search(r'(\d)[,.](\d)[\"”]?[- ]?(?:display|zoll)',path)
            if sm: screen=f'{sm.group(1)}.{sm.group(2)}'
            parsed.append((route,screen,label,price,href))
    if not parsed: return
    groups={}
    for route,screen,label,price,href in parsed:
        key=(route,screen)
        groups.setdefault(key,{})[label]=min(price,groups.setdefault(key,{}).get(label,price))
    for p in data['products']:
        if p['category']!='iphone': continue
        route=(p.get('sourceUrl') or '').split('/buy-iphone/')[-1].split('/')[0]
        target_screen='6.9' if 'Pro Max' in p['name'] else ('6.3' if p['name'].endswith('Pro') else None)
        candidates=[]
        for (r,s),vals in groups.items():
            if r!=route: continue
            if target_screen and s and s!=target_screen: continue
            candidates.append(vals)
        if not candidates: continue
        vals=max(candidates,key=len)
        new=[]
        fee=data['levies']['iphone']['amount']
        for label in ['256 GB','512 GB','1 TB','2 TB','4 TB']:
            if label in vals: new.append({'id':variant_id(label),'label':label,'gross':vals[label],'fee':fee})
        if new: p['variants']=new

def refresh_ipad(data):
    urls=sorted({p.get('sourceUrl') for p in data['products'] if p['category']=='ipad' and p.get('sourceUrl')})
    all_anchors=[]
    for url in urls:
        try: anchors,_=extract_anchor_prices(get(url)); all_anchors.extend(anchors)
        except Exception as e: print('ipad fetch failed',url,e)
    if not all_anchors: return
    fee=data['levies']['ipad']['amount']
    for p in data['products']:
        if p['category']!='ipad' or 'iPad Pro' not in p['name']: continue
        size='13' if '13"' in p['name'] else '11'
        vals={}
        for href,text,price in all_anchors:
            path=unquote(href).lower()
            if '/buy-ipad/ipad-pro/' not in path: continue
            if f'/{size}-zoll-display-' not in path: continue
            if 'cellular' in path or 'nanotextur' in path: continue
            if 'wifi-standardglas' not in path: continue
            label=storage_label(text,href)
            if label: vals[label]=min(price,vals.get(label,price))
        new=[]
        for label in ['256 GB','512 GB','1 TB','2 TB']:
            if label in vals:new.append({'id':variant_id(label),'label':label,'gross':vals[label],'fee':fee})
        if new:
            p['variants']=new
            joined=' '.join(t for h,t,pr in all_anchors if f'/{size}-zoll-display-' in unquote(h).lower())
            cm=re.search(r'M(\d+)\s*Chip',joined,re.I)
            if cm:
                gen=int(cm.group(1)); p['generation']=gen
                p['seriesKey']=f'ipad-pro-{size}'
                p['name']=f'iPad Pro {size}\" M{gen}'

def landing_start_prices(url):
    html=get(url); soup=BeautifulSoup(html,'html.parser'); results=[]
    # Apple overview cards generally keep name, "Ab … €" and a buy link close together.
    for heading in soup.find_all(['h2','h3']):
        name=clean(heading.get_text(' ',strip=True))
        if not name or len(name)>80: continue
        box=heading.parent
        for _ in range(4):
            txt=clean(box.get_text(' ',strip=True)) if box else ''
            m=AB_RE.search(txt)
            if m:
                href=''
                links=box.find_all('a',href=True) if box else []
                a=next((x for x in links if '/shop/buy-' in x.get('href','')), links[0] if links else None)
                if a: href=urljoin(url,a['href'])
                results.append((name,euro_num(m),href)); break
            box=box.parent if box else None
    # fallback from full text, useful for health checks only
    return results

def refresh_overview_bases(data):
    maps={
      'mac': [('MacBook Air','macbook-air'),('MacBook Pro','macbook-pro'),('Mac mini','mac-mini-m6'),('Mac Studio','mac-studio'),('iMac','imac')],
      'watch':[('Apple Watch Series 11','watch-series-11'),('Apple Watch SE 3','watch-se-3'),('Apple Watch Ultra 3','watch-ultra-3')]
    }
    for cat,pairs in maps.items():
        try:
            html=get(LANDINGS[cat]); text=clean(BeautifulSoup(html,'html.parser').get_text(' ',strip=True))
        except Exception as e: print('landing failed',cat,e); continue
        for display,pid in pairs:
            p=next((x for x in data['products'] if x['id']==pid),None)
            if not p: continue
            # Search a compact window after product name for the first "Ab" price.
            pos=text.find(display)
            if pos<0: continue
            m=AB_RE.search(text[pos:pos+350])
            if not m: continue
            p['variants'][0]['gross']=euro_num(m)

def infer_identity(name, cat):
    n=clean(name)
    if cat=='iphone':
        m=re.search(r'iPhone\s+(\d+)\s+Pro Max',n,re.I)
        if m:return ('iphone-pro-max',int(m.group(1)))
        m=re.search(r'iPhone\s+(\d+)\s+Pro',n,re.I)
        if m:return ('iphone-pro',int(m.group(1)))
        m=re.search(r'iPhone\s+(\d+)e',n,re.I)
        if m:return ('iphone-e',int(m.group(1)))
        m=re.search(r'iPhone\s+(\d+)',n,re.I)
        if m:return ('iphone-standard',int(m.group(1)))
        if 'Air' in n:return ('iphone-air',0)
    if cat=='ipad':
        if 'iPad Pro' in n:return ('ipad-pro',0)
        if 'iPad Air' in n:return ('ipad-air',0)
        if 'iPad mini' in n:return ('ipad-mini',0)
        return ('ipad',0)
    if cat=='mac':
        return (re.sub(r'[^a-z0-9]+','-',n.lower()).strip('-'),0)
    if cat=='watch':
        m=re.search(r'Series\s+(\d+)',n,re.I)
        if m:return ('watch-series',int(m.group(1)))
        m=re.search(r'Ultra\s+(\d+)',n,re.I)
        if m:return ('watch-ultra',int(m.group(1)))
        m=re.search(r'SE\s+(\d+)',n,re.I)
        if m:return ('watch-se',int(m.group(1)))
    return (re.sub(r'[^a-z0-9]+','-',n.lower()).strip('-'),0)

def discover_new_overview_products(data):
    known_names={clean(p['name']).lower() for p in data['products']}
    fee_by_cat={k:v['amount'] for k,v in data['levies'].items()}
    for cat,url in LANDINGS.items():
        try: cards=landing_start_prices(url)
        except Exception as e: print('discover failed',cat,e); continue
        for name,price,href in cards:
            lname=clean(name).lower()
            if any(lname==k or lname in k or k in lname for k in known_names): continue
            if cat=='iphone' and not lname.startswith('iphone'): continue
            if cat=='ipad' and 'ipad' not in lname: continue
            if cat=='mac' and not any(x in lname for x in ['mac','studio display']): continue
            if cat=='watch' and 'watch' not in lname: continue
            if cat=='vision' and 'vision' not in lname: continue
            names=[name]
            if cat=='iphone':
                m=re.search(r'iPhone\s+(\d+)\s+Pro.*iPhone\s+\1\s+Pro Max',name,re.I)
                if m:names=[f'iPhone {m.group(1)} Pro',f'iPhone {m.group(1)} Pro Max']
            for one in names:
                lk=one.lower()
                if lk in known_names: continue
                series,generation=infer_identity(one,cat)
                sid=re.sub(r'[^a-z0-9]+','-',lk.replace('ä','a').replace('ö','o').replace('ü','u')).strip('-')[:60]
                data['products'].append({'id':f'auto-{sid}','category':cat,'seriesKey':series,'generation':generation,'name':one,'subtitle':'automatisch entdeckt','sourceUrl':href or url,'variants':[{'id':'base','label':'ab','gross':price,'fee':fee_by_cat.get(cat,0)}]})
                known_names.add(lk)

def archive_if_needed(old,new):
    HISTORY.mkdir(parents=True,exist_ok=True)
    old_sig=content_signature(old); new_sig=content_signature(new)
    # First snapshot of every calendar day, so 1/8/9 September are preserved automatically.
    day=datetime.now().astimezone().strftime('%Y-%m-%d')
    daily=HISTORY/f'{day}-daily.json'
    if not daily.exists():
        snap=json.loads(json.dumps(old)); snap['snapshotAt']=now_iso(); dump(daily,snap)
    if old_sig!=new_sig:
        stamp=datetime.now().astimezone().strftime('%Y-%m-%dT%H-%M-%S%z')
        snap=json.loads(json.dumps(old)); snap['snapshotAt']=now_iso(); dump(HISTORY/f'{stamp}-before-change.json',snap)
    return old_sig!=new_sig

def update_summary(summary, old, new):
    before=json.dumps(summary.get('series',{}),ensure_ascii=False,sort_keys=True)
    summary.setdefault('series',{})
    # Preserve every model/price combination ever seen in compact form.
    for p in old.get('products',[])+new.get('products',[]):
        key=p.get('seriesKey') or p['id']; arr=summary['series'].setdefault(key,[])
        sig=json.dumps(p.get('variants',[]),sort_keys=True)
        exists=any(x.get('id')==p['id'] and json.dumps(x.get('variants',[]),sort_keys=True)==sig for x in arr)
        if not exists:
            arr.append({'id':p['id'],'name':p['name'],'generation':p.get('generation',0),'date':datetime.now().astimezone().strftime('%Y-%m-%d'),'variants':p.get('variants',[]),'source':'Apple Store DE'})
    after=json.dumps(summary.get('series',{}),ensure_ascii=False,sort_keys=True)
    if after!=before: summary['updatedAt']=now_iso()
    return summary

def main():
    old=load(CURRENT); new=json.loads(json.dumps(old))
    refresh_levies(new)
    discover_new_overview_products(new)
    refresh_iphone(new)
    refresh_ipad(new)
    refresh_overview_bases(new)
    changed=archive_if_needed(old,new)
    if changed:
        new['updatedAt']=now_iso()
        dump(CURRENT,new)
    # Daily history summary update is useful even without a price change.
    summary=load(SUMMARY) if SUMMARY.exists() else {'series':{}}
    summary=update_summary(summary,old,new)
    dump(SUMMARY,summary)
    print('changed=',changed,'products=',len(new['products']))

if __name__=='__main__': main()
