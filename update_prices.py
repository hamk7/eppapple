from __future__ import annotations
import hashlib,json,re,time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent; CURRENT=ROOT/'current.json'; SUMMARY=ROOT/'history-summary.json'; HISTORY=ROOT/'price-history'
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 AppleRabattBot/4.0','Accept-Language':'de-DE,de;q=0.9,en;q=0.5'})
PRICE_RE=re.compile(r'(?<!\d)(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?\s*€')
ZPUE={'iphone':('https://www.zpue.de/produkte-tarife/mobiltelefone.html',5.0),'ipad':('https://www.zpue.de/produkte-tarife/tablets.html',7.0),'mac':('https://www.zpue.de/produkte-tarife/pcs.html',10.55),'watch':('https://www.zpue.de/produkte-tarife/smartwatches.html',1.2)}
LANDINGS={'iphone':'https://www.apple.com/de/shop/buy-iphone','ipad':'https://www.apple.com/de/shop/buy-ipad','mac':'https://www.apple.com/de/shop/buy-mac','displays':'https://www.apple.com/de/shop/buy-mac','watch':'https://www.apple.com/de/shop/buy-watch','vision':'https://www.apple.com/de/shop/buy-vision','airpods':'https://www.apple.com/de/shop/buy-airpods','tvhome':'https://www.apple.com/de/shop/smart-home/accessories'}
ACCESS='https://www.apple.com/de/shop/accessories/all'; MADE='https://www.apple.com/de/shop/accessories/all/made-by-apple'
CAT_LABELS={'mäuse & tastaturen':'mice-keyboards','gesundheit & fitness':'health-fitness','ladegeräte & adapter':'chargers-adapters','kopfhörer & lautsprecher':'headphones-speakers','software':'software','zubehör fürs büro':'office','festplatten & speicher':'storage','content erstellung':'content','gaming':'gaming','hüllen & schutz':'cases-protection','smart home zubehör':'smart-home','airtag':'airtag','beats':'beats'}
PRODUCT_LABELS={'iphone':'iphone','ipad':'ipad','mac':'mac','apple watch':'watch','apple vision pro':'vision','airpods':'airpods','tv & home':'tvhome','airtag':'airtag','beats':'beats'}

def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower().replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss')).strip('-')[:85]
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def dump(p,o): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def get(url):
    last=None
    for i in range(3):
        try:
            r=S.get(url,timeout=35);r.raise_for_status();return r.text
        except Exception as e: last=e;time.sleep(1+i)
    raise last
def price(s):
    m=PRICE_RE.search(clean(s));
    return float(m.group(1).replace('.','')+'.'+(m.group(2) or '00')) if m else None
def soup(h): return BeautifulSoup(h,'html.parser')
def image(h,u):
    x=soup(h)
    for a in ({'property':'og:image'},{'name':'twitter:image'}):
        t=x.find('meta',attrs=a)
        if t and t.get('content'): return urljoin(u,t['content'])
    for im in x.find_all('img'):
        src=im.get('src') or im.get('data-src')
        if src and 'storeimages' in src:return urljoin(u,src)
    return ''
def signature(d):
    k={x:d.get(x) for x in ('vat','levies','categories','products')};return hashlib.sha256(json.dumps(k,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def refresh_levies(d):
    for k,(url,fallback) in ZPUE.items():
        amount=fallback
        try:
            txt=clean(soup(get(url)).get_text(' ',strip=True))
            vals=[float(a.replace(',','.')) for a in re.findall(r'(\d{1,2},\d{2})\s*€',txt)]
            # choose value nearest known contract rate to avoid unrelated tariff figures
            if vals: amount=min(vals,key=lambda v:abs(v-fallback))
        except Exception as e: print('levy',k,e)
        d.setdefault('levies',{}).setdefault(k,{})['amount']=amount
        for p in d.get('products',[]):
            if p.get('category')==k:
                for v in p.get('variants',[]):v['fee']=amount

def model_cards(html,url):
    s=soup(html);out=[];seen=set()
    for a in s.find_all('a',href=True):
        href=urljoin(url,a['href']).split('?')[0]
        if '/de/shop/buy-' not in href:continue
        box=a
        txt=clean(a.get('aria-label') or a.get('title') or a.get_text(' ',strip=True))
        for _ in range(6):
            box=getattr(box,'parent',None)
            if not box:break
            bt=clean(box.get_text(' ',strip=True))
            if '€' in bt and len(bt)<900:txt=bt;break
        pr=price(txt)
        if pr is None:continue
        name=clean(a.get('aria-label') or a.get('title') or a.get_text(' ',strip=True))
        if not name or name.lower() in ('kaufen','mehr erfahren'):
            h=box.find(['h2','h3','h4']) if box else None
            if h:name=clean(h.get_text(' ',strip=True))
        name=re.sub(r'\s+(Kaufen|Genauer ansehen|Vorbestellen).*','',name,flags=re.I).strip()
        if not name or len(name)>110:continue
        key=(name.lower(),href)
        if key in seen:continue
        seen.add(key);out.append((name,pr,href))
    return out

def discover_new_models(d):
    existing_urls={p.get('sourceUrl','').rstrip('/'):p for p in d.get('products',[])}
    existing_names={p.get('name','').lower():p for p in d.get('products',[])}
    for cat,url in LANDINGS.items():
        try: cards=model_cards(get(url),url)
        except Exception as e:print('landing',cat,e);continue
        for name,pr,href in cards:
            # Update matching known base price only if it is a clear exact model match.
            p=existing_urls.get(href.rstrip('/')) or existing_names.get(name.lower())
            if p is None:
                lname0=name.lower()
                # Apple sometimes has one landing card for two variants (e.g. Pro + Pro Max, 16 + 16 Plus).
                p=next((x for x in d.get('products',[]) if x.get('category')==cat and x.get('name','').lower() in lname0),None)
            if p and p.get('variants'):
                # Known products are seeded from the current EPP PDFs / verified values.
                # Public landing cards can temporarily show a different promo or a stale
                # base configuration, so do not overwrite a verified base automatically.
                # Keep the observation for diagnostics; new models are still discovered.
                p['observedLandingGross']=pr
                p['observedLandingAt']=now_iso()
                continue
            # Avoid accidental cross-model cards; only add clearly named current products.
            lname=name.lower()
            if cat=='iphone' and 'iphone' not in lname:continue
            if cat=='ipad' and 'ipad' not in lname:continue
            if cat=='watch' and 'watch' not in lname:continue
            if cat=='airpods' and 'airpods' not in lname:continue
            if cat=='vision' and 'vision' not in lname:continue
            if cat=='mac' and not any(x in lname for x in ('macbook','imac','mac mini','mac studio')):continue
            if cat=='displays' and 'display' not in lname:continue
            if cat=='tvhome' and not any(x in lname for x in ('homepod','apple tv')):continue
            pid='auto-'+slug(name)
            if any(x.get('id')==pid for x in d.get('products',[])):continue
            fee=float(d.get('levies',{}).get(cat,{}).get('amount',0))
            sub='standard'
            if cat=='mac':sub='macbooks' if 'macbook' in lname else 'desktop'
            elif cat=='displays':sub='xdr' if 'xdr' in lname else 'studio'
            elif cat=='tvhome':sub='homepod' if 'homepod' in lname else 'apple-tv'
            elif cat=='watch':sub='hermes' if 'herm' in lname else ('ultra' if 'ultra' in lname else ('se' if ' se ' in ' '+lname+' ' else 'series'))
            elif cat=='ipad':sub='pro' if 'pro' in lname else ('air' if 'air' in lname else ('mini' if 'mini' in lname else 'standard'))
            elif cat=='iphone':sub='pro' if 'pro' in lname else ('air' if 'air' in lname else 'standard')
            elif cat=='airpods':sub='pro' if 'pro' in lname else ('max' if 'max' in lname else 'standard')
            d['products'].append({'id':pid,'category':cat,'subcategory':sub,'seriesKey':pid,'generation':0,'name':name,'subtitle':'Neu erkannt','sourceUrl':href,'imageUrl':'','brandType':'apple','tags':['automatisch erkannt'],'autoConfig':True,'variants':[{'id':'base','label':'Basismodell','gross':pr,'fee':fee}]})

def config_links(h,base):
    s=soup(h);basep=urlparse(base).path.rstrip('/');out=[]
    for a in s.find_all('a',href=True):
        u=urljoin(base,a['href']).split('?')[0]
        path=urlparse(u).path.rstrip('/')
        if path.startswith(basep+'/') and len(path)>len(basep)+3 and u not in out:out.append(u)
    return out

def parse_config_page(h,u,p):
    s=soup(h)
    h1=clean(s.find('h1').get_text(' ',strip=True)) if s.find('h1') else ''
    tt=clean(s.find('title').get_text(' ',strip=True)) if s.find('title') else ''
    # Apple config pages often have a generic H1 but a detailed document title.
    title=tt if (len(tt)>len(h1)+12 or ' GB ' in tt or ' TB ' in tt or ',' in tt) else (h1 or tt)
    main=s.find('main') or s
    text=clean(main.get_text(' ',strip=True))
    floor=min((float(v.get('gross',0)) for v in p.get('variants',[]) if v.get('gross')),default=0)
    threshold=max(50,floor*.72)
    prices=[]
    for m in PRICE_RE.finditer(text):
        pr=float(m.group(1).replace('.','')+'.'+(m.group(2) or '00'))
        # Ignore gift cards, monthly payments and trade-in amounts shown before the product price.
        if pr>=threshold:prices.append(pr)
    if not prices:return None
    pr=prices[0]
    opts={}
    patterns=[('Größe',r'(\d{2})[- ]?(?:Zoll|mm)'),('Arbeitsspeicher',r'(8|16|24|32|36|48|64|96|128|192|256|512)\s*GB\s+(?:Arbeitsspeicher|gemeinsamer Arbeitsspeicher)'),('Speicher',r'(128|256|512)\s*GB\s+(?:SSD\s*)?(?:Speicher|SSD)|\b(1|2|4|8|16)\s*TB\s+(?:SSD\s*)?(?:Speicher|SSD)')]
    for k,pat in patterns:
        m=re.search(pat,title,re.I)
        if m:
            val=next((g for g in m.groups() if g),m.group(0));opts[k]=val+(' mm' if k=='Größe' and 'mm' in m.group(0) else (' Zoll' if k=='Größe' else (' GB' if k=='Arbeitsspeicher' else (' TB' if 'TB' in m.group(0) else ' GB'))))
    for token in ['M6','M5 Ultra','M5 Max','M5 Pro','M5','M4','A18 Pro']:
        if token.lower() in title.lower():opts['Chip']=token;break
    if 'Nanotextur' in title:opts['Glas']='Nanotexturglas'
    elif p.get('category') in ('mac','displays') and ('Display' in title or 'MacBook' in title or 'iMac' in title):opts['Glas']='Standardglas'
    if 'Cellular' in title:opts['Verbindung']='GPS + Cellular' if p.get('category')=='watch' else 'Wi-Fi + Cellular'
    elif p.get('category')=='watch' and 'GPS' in title:opts['Verbindung']='GPS'
    # Watch band tail
    if p.get('category')=='watch' and ',' in title: opts['Armband']=title.split(',')[-1].replace('kaufen','').strip()
    label=' · '.join(opts.values()) if opts else re.sub(r'\s+kaufen.*','',title,flags=re.I)[:130]
    return {'id':'auto-'+slug(u.split('/')[-1]),'label':label or 'Konfiguration','gross':pr,'fee':float(p.get('variants',[{}])[0].get('fee',0)),'options':opts,'sourceUrl':u}

def deep_configs(d):
    # Only deep scan products flagged autoConfig. Existing detailed manual grids (iPhone/iPad/Vision) remain protected.
    for p in d.get('products',[]):
        if not p.get('autoConfig') or not p.get('sourceUrl'):continue
        try: h=get(p['sourceUrl']); links=config_links(h,p['sourceUrl'])
        except Exception as e:print('config root',p.get('name'),e);continue
        # cap requests: enough to populate useful standard configurations while keeping scheduled runs polite.
        cap=90 if p.get('category')=='watch' else 55
        found={}
        for u in links[:cap]:
            try:
                v=parse_config_page(get(u),u,p)
                if v:
                    key=(tuple(sorted(v.get('options',{}).items())),v['gross'])
                    found.setdefault(key,v)
            except Exception:pass
        vals=list(found.values())
        if vals:
            # Merge, never replace: verified seed variants remain the source of truth for
            # current starting prices and exact EPP exceptions. Deep scans only add useful
            # configurations found on Apple's public configurator pages.
            old=list(p.get('variants',[]))
            floor=min((float(v.get('gross',1e12)) for v in old), default=0)
            # Avoid a lower public promo/stale card silently changing the verified EPP start.
            vals=[v for v in vals if float(v.get('gross',0)) + 0.01 >= floor]
            combined={}
            for v in old + vals:
                k=(tuple(sorted((v.get('options') or {}).items())), round(float(v.get('gross',0)),2), v.get('label',''))
                combined.setdefault(k,v)
            p['variants']=sorted(combined.values(), key=lambda x:(float(x.get('gross',0)),x.get('label','')))
        im=image(h,p['sourceUrl'])
        if im and not str(p.get('imageUrl','')).endswith('.png'):p['imageUrl']=im

def acc_links(h,base,labels=CAT_LABELS):
    s=soup(h);out={}
    for a in s.find_all('a',href=True):
        lab=clean(a.get_text(' ',strip=True)).lower()
        if lab in labels:out[labels[lab]]=urljoin(base,a['href'])
    return out

def acc_cards(h,url):
    s=soup(h);out={}
    for a in s.find_all('a',href=True):
        href=urljoin(url,a['href']).split('?')[0]
        if '/shop/product/' not in href:continue
        box=a;txt=clean(a.get('aria-label') or a.get('title') or a.get_text(' ',strip=True))
        for _ in range(6):
            if not box:break
            bt=clean(box.get_text(' ',strip=True))
            if '€' in bt and len(bt)<1400:txt=bt;break
            box=box.parent
        pr=price(txt)
        if pr is None:continue
        name=''
        if box:
            hh=box.find(['h2','h3','h4'])
            if hh:name=clean(hh.get_text(' ',strip=True))
        if not name:name=clean(a.get('aria-label') or a.get('title') or a.get_text(' ',strip=True))
        name=re.sub(r'\s+(kaufen|anzeigen|weitere infos).*','',name,flags=re.I).strip()
        if len(name)<2:continue
        img=''
        if box:
            im=box.find('img'); src=(im.get('src') or im.get('data-src')) if im else ''
            if src:img=urljoin(url,src)
        out[href]=(name,pr,img)
    return out

def refresh_accessories(d):
    try: allh=get(ACCESS); madeh=get(MADE)
    except Exception as e:print('access root',e);return
    filters=acc_links(allh,ACCESS,CAT_LABELS); productfilters=acc_links(allh,ACCESS,PRODUCT_LABELS); made=set(acc_cards(madeh,MADE))
    # discover Apple-only category links too
    madefilters=acc_links(madeh,MADE,CAT_LABELS)
    for _,u in madefilters.items():
        try:made.update(acc_cards(get(u),u))
        except Exception:pass
    cards={};catfor={};compatfor={}
    for cat,u in filters.items():
        try:
            cc=acc_cards(get(u),u);cards.update(cc)
            for x in cc:catfor[x]=cat
        except Exception as e:print('acc cat',cat,e)
    for comp,u in productfilters.items():
        try:
            cc=acc_cards(get(u),u);cards.update(cc)
            for x in cc:compatfor.setdefault(x,set()).add(comp)
        except Exception as e:print('acc product',comp,e)
    # root catches products that do not appear in discovered filters
    cards.update(acc_cards(allh,ACCESS))
    existing={p.get('sourceUrl','').split('?')[0]:p for p in d.get('products',[]) if p.get('category')=='accessories' and p.get('sourceUrl')}
    seen=set()
    for href,(name,pr,img) in cards.items():
        ln=name.lower()
        if any(x in ln for x in ('airpods','homepod','studio display')):continue
        cat=catfor.get(href) or ('airtag' if 'airtag' in ln else ('beats' if 'beats' in ln else 'office'))
        brand='apple' if href in made or 'beats' in ln else 'third-party'
        p=existing.get(href)
        if p is None:
            p={'id':'acc-'+slug(href.split('/product/')[-1]),'category':'accessories','subcategory':cat,'seriesKey':'acc-'+slug(name),'generation':0,'name':name,'subtitle':'','sourceUrl':href,'imageUrl':img,'brandType':brand,'tags':[cat,name],'compat':sorted(compatfor.get(href,set())),'autoDiscovered':True,'variants':[{'id':'one','label':'Standard','gross':pr,'fee':0}]}
            d['products'].append(p);existing[href]=p
        else:
            p.update({'name':name,'subcategory':cat,'brandType':brand,'available':True});p.setdefault('tags',[]);p['compat']=sorted(set(p.get('compat',[]))|compatfor.get(href,set()))
            if img:p['imageUrl']=img
            if p.get('variants'):
                old=p['variants'][0]
                if abs(float(old.get('gross',0))-pr)>.001:old['gross']=pr;old.pop('epp',None)
        seen.add(p['id'])
    if len(seen)>10:
        for p in d.get('products',[]):
            if p.get('category')=='accessories' and p.get('autoDiscovered'):p['available']=p['id'] in seen

def archive(old,new):
    HISTORY.mkdir(exist_ok=True)
    day=datetime.now().astimezone().strftime('%Y-%m-%d'); daily=HISTORY/f'{day}-daily.json'
    if not daily.exists():dump(daily,{**deepcopy(old),'snapshotAt':now()})
    if signature(old)!=signature(new):
        stamp=datetime.now().astimezone().strftime('%Y-%m-%dT%H-%M-%S%z');dump(HISTORY/f'{stamp}-before-change.json',{**deepcopy(old),'snapshotAt':now()});return True
    return False

def update_summary(old,new):
    s=load(SUMMARY) if SUMMARY.exists() else {'series':{}}; day=datetime.now().astimezone().strftime('%Y-%m-%d')
    for p in old.get('products',[])+new.get('products',[]):
        if not p.get('variants'):continue
        arr=s.setdefault('series',{}).setdefault(p.get('seriesKey') or p['id'],[]); sig=json.dumps(p['variants'],sort_keys=True,ensure_ascii=False)
        if not any(x.get('id')==p['id'] and json.dumps(x.get('variants',[]),sort_keys=True,ensure_ascii=False)==sig for x in arr):arr.append({'id':p['id'],'name':p['name'],'generation':p.get('generation',0),'date':day,'variants':p['variants']})
    s['updatedAt']=now();dump(SUMMARY,s)

def main():
    old=load(CURRENT);new=deepcopy(old);new['lastCheckedAt']=now();refresh_levies(new);discover_new_models(new)
    # Deep configuration scan only once daily or when a product still has <=2 variants.
    hour=datetime.now().astimezone().hour
    if hour<6 or any(p.get('autoConfig') and len(p.get('variants',[]))<=2 for p in new.get('products',[])):deep_configs(new)
    refresh_accessories(new)
    changed=archive(old,new)
    if changed:new['updatedAt']=now();new['lastChangedAt']=new['updatedAt']
    else:new.setdefault('lastChangedAt',old.get('lastChangedAt') or old.get('updatedAt'))
    dump(CURRENT,new);update_summary(old,new);print('checked',new['lastCheckedAt'],'changed',changed,'products',len(new.get('products',[])))
if __name__=='__main__':main()
