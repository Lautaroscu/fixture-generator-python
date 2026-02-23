import json

with open("equipos_tiras.json", "r", encoding="utf-8") as f:
    data = json.load(f)

clubs = {c["nombre"]: c for c in data["clubes"]}
torneos = {t["id"]: t for t in data["torneos"]}

target = "MENORES-B"
participants = torneos[target]["participantes"]

cats = ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"]
density = {cat: 0 for cat in cats}
missing = {cat: [] for cat in cats}

for p in participants:
    club = clubs.get(p)
    if not club: continue
    active_cats = club.get("categorias_activas", [])
    for cat in cats:
        if cat in active_cats:
            density[cat] += 1
        else:
            missing[cat].append(p)

print(f"Density for {target}:")
for cat, count in density.items():
    print(f"  {cat}: {count} teams (Missing: {', '.join(missing[cat])})")
