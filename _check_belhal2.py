import os, json

# Check BELHAL sub result for grid dims in different locations
with open('BELHAL_result.json', encoding='utf-8') as f:
    sub = json.load(f)

print('gridDims:', sub.get('gridDims', {}))

# Check qtoItems for excavation breakdown (has L and W)
for it in sub.get('qtoItems', []):
    if it.get('id') in ('excavation', 'slab_on_grade', 'blockwall_solid_sub'):
        print(f"  {it['id']}: qty={it.get('totalQty')} bd={it.get('breakdown','')[:80]}")

# Check observed elements
obs = sub.get('observedElements', [])
print(f'\nObserved elements: {len(obs)}')
for el in obs[:5]:
    print(f"  {el.get('type','')} {el.get('mark','')} — {el.get('dims',{})}")
