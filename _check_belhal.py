import os, json

# Check BELHAL sub result for grid dims
with open('BELHAL_result.json', encoding='utf-8') as f:
    sub = json.load(f)
gd = sub.get('gridDims', {})
print('Grid dims:', gd)

# Check BELHAL super result for heights
with open('BELHAL_super_result.json', encoding='utf-8') as f:
    sup = json.load(f)
fh = sup.get('floorHeights', {})
print('Floor heights:', fh)

# Check old arch result
with open('BELHAL_arch_result.json', encoding='utf-8') as f:
    arch = json.load(f)
items = arch.get('items', [])
print(f'Old arch items: {len(items)}')
for it in items:
    iid = it.get("id", "")
    q = it.get("q", 0)
    u = it.get("u", "")
    print(f'  {iid:<24} => {q:>10}  {u}')

dw = arch.get('dw', [])
print(f'\nOld D&W: {len(dw)}')
for d in dw:
    did = d.get("id", "?")
    cat = d.get("cat", "?")
    w = d.get("w", 0)
    h = d.get("h", 0)
    n = d.get("n", 0)
    a = d.get("a", 0)
    print(f'  {did}: {cat} {w}x{h}m n={n} a={a}')
