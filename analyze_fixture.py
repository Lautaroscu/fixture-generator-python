import json

with open("fixture.json", "r", encoding="utf-8") as f:
    fixture = json.load(f)

counts = {}
for entry in fixture:
    fecha = entry["nroFecha"]
    liga = entry["liga"]
    if liga == "MAYORES-A":
        counts[fecha] = len(entry["partidos"])

print("MAYORES-A Match counts per date:")
for f in sorted(counts.keys()):
    print(f"Fecha {f}: {counts[f]} matches")
