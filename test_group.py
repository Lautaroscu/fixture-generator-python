import json

with open("equipos.json", "r", encoding="utf-8") as f:
    data = json.load(f)

grupos = {"Primera A": [], "Primera B": [], "Infantiles A": [], "Infantiles B": [], "Infantiles C": [], "Femenino": []}

for eq in data["equipos"]:
    cats = eq.get("categorias", {})
    div = eq.get("divisionMayor", "")
    nombre = eq["nombre"]
    
    has_primera = cats.get("primera", False) or cats.get("reserva", False)
    has_infantiles = any(cats.get(k, False) for k in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"])
    has_femenino = any(cats.get(k, False) for k in ["femenino_primera", "femenino_sub16", "femenino_sub14", "femenino_sub12"])
    
    if has_primera and div == "A": grupos["Primera A"].append(nombre)
    if has_primera and div == "B": grupos["Primera B"].append(nombre)
    if has_infantiles and div == "A": grupos["Infantiles A"].append(nombre)
    if has_infantiles and div == "B": grupos["Infantiles B"].append(nombre)
    if has_infantiles and div == "C": grupos["Infantiles C"].append(nombre)
    if has_femenino: grupos["Femenino"].append(nombre)

for k, v in grupos.items():
    print(f"{k} ({len(v)} equipos): {v}")
