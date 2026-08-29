from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
D=json.loads((ROOT/'current.json').read_text(encoding='utf-8'))

def q(v, places='0.01'):
    return Decimal(str(v)).quantize(Decimal(places), rounding=ROUND_HALF_UP)

def calc(gross, fee, rate):
    gross=Decimal(str(gross)); fee=Decimal(str(fee)); rate=Decimal(str(rate))
    net=q(gross/Decimal('1.19'))
    base=net-fee
    discounted_cents=q(base*(Decimal('1')-rate/Decimal('100')))
    discounted_whole=discounted_cents.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    subtotal=q(discounted_whole+fee)
    vat=q(subtotal*Decimal('0.19'))
    return q(subtotal+vat)

# The important rounding edge case: Apple rounds the discounted net amount to cents
# before the final whole-euro rounding. Without that step 1,449 € incorrectly becomes
# 1,203.09 € instead of 1,204.28 € at 17%.
assert calc(1449,5,17)==Decimal('1204.28')
assert calc(1449,5,27)==Decimal('1059.10')
assert calc(45,0,27)==Decimal('33.32')
assert calc(65,0,27)==Decimal('47.60')
assert calc(85,0,27)==Decimal('61.88')
assert calc(3999,0,17)==Decimal('3318.91')
assert calc(4219,0,17)==Decimal('3502.17')

expected17={
'iPhone 17 Pro':1079.33,'iPhone Air':996.03,'iPhone 17':788.97,'iPhone 16':705.67,'iPhone 17e':580.72,
'MacBook Neo':665.86,'MacBook Air':1163.28,'MacBook Pro':1827.30,'iMac':1495.29,'Mac mini':872.92,'Mac Studio':2491.32,
'Studio Display':1410.15,'Studio Display XDR':2571.59,'Apple Watch Series 11':372.71,'Apple Watch SE 3':222.77,
'Apple Watch Ultra 3':746.37,'Apple Watch Hermès':1160.49,'Apple Watch Hermès Ultra 3':1310.43,
'iPad Pro':1079.33,'iPad Air':664.02,'iPad':415.31,'iPad mini':565.25,'Apple Vision Pro':3318.91,
'AirPods Pro 3':207.06,'AirPods 4':123.76,'AirPods Max 2':480.76,'HomePod':330.82,'HomePod mini':115.43,'Apple TV 4K':190.40,
}
products={p['name']:p for p in D['products']}
for name,want in expected17.items():
    p=products[name]
    v=min(p['variants'],key=lambda x:float(x.get('gross',1e99)))
    got=(v.get('epp') or {}).get('17')
    assert got is not None and abs(float(got)-want)<.005,(name,got,want)

# Core assortment/configurability checks.
assert len(products['iPhone 17 Pro']['variants'])==3
assert len(products['iPhone 17 Pro Max']['variants'])==4
assert len(products['Apple Vision Pro']['variants'])==3
for name in ['MacBook Air','MacBook Pro','Mac mini','Mac Studio','Apple Watch Series 11','Apple Watch SE 3','Apple Watch Ultra 3','Apple Watch Hermès','Apple Watch Hermès Ultra 3','Studio Display','Studio Display XDR']:
    assert products[name].get('autoConfig') is True,name

# Every local image reference shipped by the seed must exist.
for p in D['products']:
    img=str(p.get('imageUrl') or '')
    if img and not img.startswith('http'):
        assert (ROOT/img).exists(),(p['name'],img)

html=(ROOT/'index.html').read_text(encoding='utf-8')
for token in ['data-theme-value="system"','data-theme-value="light"','data-theme-value="dark"','discountedCents','Preisvergleich mit Vorgängermodellen']:
    assert token in html,token

# Theme regression checks: System is the default and both palettes must have explicit surfaces.
assert "localStorage.getItem('ar_theme')||'system'" in html
for token in ['html[data-theme="light"]','--bg:#f5f5f7','--panel:#ffffff','html[data-theme="dark"]','--bg:#050506','--panel:#111114','.fallbackArt{background:var(--surface2)']:
    assert token in html,token

print('self-test OK:',len(D['products']),'seed products')
