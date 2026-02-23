import json

def migrate():
    with open("equipos.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    clubes = {}
    
    # Recopilar clubes y sus categorías reales
    for eq in data.get("equipos", []):
        club_name = eq.get("clubPadre", eq["nombre"])
        if club_name not in clubes:
            clubes[club_name] = {
                "nombre": club_name,
                "estadioLocal": {"default": eq.get("estadioLocal", "")},
                "estadioPropio": eq.get("estadioPropio", True),
                "categorias_activas": [],
                "division_mayores": None,
                "division_menores": None, # Usaremos la de infantiles si difiere
            }
        
        # Guardar estadio por bloque si se especifica en esta entrada
        estadio = eq.get("estadioLocal")
        if estadio:
            cats_en_entrada = eq.get("categorias", {})
            if any(cats_en_entrada.get(c) for c in ["primera", "reserva"]):
                clubes[club_name]["estadioLocal"]["MAYORES"] = estadio
            if any(cats_en_entrada.get(c) for c in ["quinta", "sexta", "septima", "octava"]):
                clubes[club_name]["estadioLocal"]["JUVENILES"] = estadio
            if any(cats_en_entrada.get(c) for c in ["novena", "decima", "undecima"]):
                clubes[club_name]["estadioLocal"]["INFANTILES"] = estadio
            if any("femenino" in c and cats_en_entrada.get(c) for c in cats_en_entrada):
                clubes[club_name]["estadioLocal"]["FEMENINO-A"] = estadio
            
            # El primero que llega manda el default si no habia
            if not clubes[club_name]["estadioLocal"].get("default"):
                clubes[club_name]["estadioLocal"]["default"] = estadio

        # Guardar divisiones (A, B, C)
        div_mayor = eq.get("divisionMayor", "A").upper()
        div_infantil = eq.get("divisionInfantiles", div_mayor).upper()
        
        # Las categorías que tengan true
        for cat, active in eq.get("categorias", {}).items():
            if active:
                if cat not in clubes[club_name]["categorias_activas"]:
                    clubes[club_name]["categorias_activas"].append(cat)
                    
                # Determinar en qué división juegan sus torneos
                if cat in ["primera", "reserva"]:
                    clubes[club_name]["division_mayores"] = div_mayor
                elif cat in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"]:
                    # Juveniles usa divisionMayor, Infantiles usa divisionInfantiles
                    # Para simplificar, asumiremos que van juntos en la división de Juveniles (divisionMayor)
                    # a menos que explícitamente el club solo tenga infantiles.
                    if cat in ["novena", "decima", "undecima"]:
                        clubes[club_name]["division_menores"] = div_infantil
                    else:
                        clubes[club_name]["division_menores"] = div_mayor
                elif "femenino" in cat:
                    clubes[club_name]["division_femenino"] = "A" # Femenino suele ser A
                    
    # Armar los Torneos
    torneos = {}
    
    for c_name, c_data in clubes.items():
        cats = c_data["categorias_activas"]
        
        # Tiene Mayores?
        if "primera" in cats or "reserva" in cats:
            div = c_data.get("division_mayores", "A")
            t_id = f"MAYORES-{div}"
            if t_id not in torneos:
                torneos[t_id] = {"id": t_id, "nombre": f"Primera y Reserva - Liga {div}", "participantes": []}
            torneos[t_id]["participantes"].append(c_name)
            
        # Tiene Menores (Juveniles o Infantiles)?
        # Caso Especial: Ateneo Estrada se divide
        if c_name == "ATENEO ESTRADA":
            # MENORES-B: Quinta, Sexta, Septima
            if any(k in cats for k in ["quinta", "sexta", "septima"]):
                t_id = "MENORES-B"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Tira Juveniles e Infantiles - Liga B", "participantes": []}
                if c_name not in torneos[t_id]["participantes"]:
                    torneos[t_id]["participantes"].append(c_name)
            # MENORES-C: Novena, Decima, Undecima (y Octava si tuviera)
            if any(k in cats for k in ["octava", "novena", "decima", "undecima"]):
                t_id = "MENORES-C"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Tira Juveniles e Infantiles - Liga C", "participantes": []}
                if c_name not in torneos[t_id]["participantes"]:
                    torneos[t_id]["participantes"].append(c_name)
        else:
            tiene_menores = any(k in cats for k in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"])
            if tiene_menores:
                div = c_data.get("division_menores", "A")
                t_id = f"MENORES-{div}"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": f"Tira Juveniles e Infantiles - Liga {div}", "participantes": []}
                if c_name not in torneos[t_id]["participantes"]:
                    torneos[t_id]["participantes"].append(c_name)
            
        # Tiene Femenino Mayores? (Incluye Primera y Sub-16)
        if any(k in cats for k in ["femenino_primera", "femenino_sub16"]):
            # Excepción de usuario: Juve Blanco es solo Mayores
            if c_name == "Juventud Unida (Blanco)":
                t_id = "FEMENINO-MAYORES"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Femenino - Primera", "participantes": []}
                torneos[t_id]["participantes"].append(c_name)
            elif c_name == "Juventud Unida (Negro)":
                # El Negro NO va en mayores (solo menores)
                pass
            else:
                t_id = "FEMENINO-MAYORES"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Femenino - Primera", "participantes": []}
                torneos[t_id]["participantes"].append(c_name)
            
        # Tiene Femenino Menores? (Sub-14 y Sub-12)
        if any(k in cats for k in ["femenino_sub14", "femenino_sub12"]):
            # Excepción de usuario: Juve Blanco es solo Mayores
            # Juve Negro (Juventud Unida (Negro)) es solo Menores
            if c_name == "Juventud Unida (Negro)":
                t_id = "FEMENINO-MENORES"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Femenino - Inferiores", "participantes": []}
                torneos[t_id]["participantes"].append(c_name)
            elif c_name != "Juventud Unida (Blanco)":
                t_id = "FEMENINO-MENORES"
                if t_id not in torneos:
                    torneos[t_id] = {"id": t_id, "nombre": "Femenino - Inferiores", "participantes": []}
                torneos[t_id]["participantes"].append(c_name)
            
    # Reglas Institucionales
    reglas = []
    for c_name, c_data in clubes.items():
        cats = c_data["categorias_activas"]
        tiene_mayores = "primera" in cats or "reserva" in cats
        # Torneos de menores en los que participa este club
        torneos_men_club = [t_id for t_id, t_info in torneos.items() if "MENORES" in t_id and c_name in t_info["participantes"]]
        
        # Sincronizar Mayores con cada uno de sus torneos de Menores
        if tiene_mayores and torneos_men_club:
            div_may = c_data.get("division_mayores", "A")
            for t_men in torneos_men_club:
                reglas.append({
                    "tipo": "ESPEJO",
                    "club": c_name,
                    "torneo1": f"MAYORES-{div_may}",
                    "torneo2": t_men,
                    "hard": True
                })
            
        tiene_fem_may = "femenino_primera" in cats or "femenino_sub16" in cats
        tiene_fem_men = any(k in cats for k in ["femenino_sub14", "femenino_sub12"])
        
        if tiene_fem_may and tiene_mayores:
            div_may = c_data.get("division_mayores", "A")
            tipo_fem = "ESPEJO" if c_name == "Loma Negra" else "INVERSO"
            reglas.append({
                "tipo": tipo_fem,
                "club": c_name,
                "torneo1": f"MAYORES-{div_may}",
                "torneo2": "FEMENINO-MAYORES",
                "hard": True
            })

        if tiene_fem_men and tiene_mayores:
            div_may = c_data.get("division_mayores", "A")
            tipo_fem = "INVERSO"
            reglas.append({
                "tipo": tipo_fem,
                "club": c_name,
                "torneo1": f"MAYORES-{div_may}",
                "torneo2": "FEMENINO-MENORES",
                "hard": True
            })
            
    # ------ EXCEPCIONES EXPLICITAS FEMENINAS ------
    for t_fem in ["FEMENINO-MAYORES", "FEMENINO-MENORES"]:
        reglas.append({
            "tipo": "ESPEJO",
            "clubA": "Independiente (rojo)",
            "clubB": "Independiente",
            "torneo1": "MAYORES-B",
            "torneo2": t_fem,
            "hard": True
        })
    
    for t_fem in ["FEMENINO-MAYORES", "FEMENINO-MENORES"]:
        reglas.append({
            "tipo": "ESPEJO",
            "clubA": "Ferro Azul",
            "clubB": "Ferrocarril Sud",
            "torneo1": "MENORES-B",
            "torneo2": t_fem,
            "hard": True
        })
    
    # ------ REGLAS AYACUCHO ------
    # Sarmiento y Ateneo Estrada deben cruzar en Mayores
    reglas.append({
        "tipo": "INVERSO",
        "clubA": "SARMIENTO AYACUCHO",
        "clubB": "ATENEO ESTRADA",
        "torneo1": "MAYORES-A",
        "torneo2": "MAYORES-B",
        "hard": True
    })

    # Añadir las reglas explícitas de equipos.json adaptadas
    for r in data.get("reglas", []):
        if r["clubA"] == r["clubB"]:
            t1 = map_bloque_to_torneo(r["bloqueA"], r["clubA"], clubes)
            t2 = map_bloque_to_torneo(r["bloqueB"], r["clubB"], clubes)
            if t1 and t2 and t1 != t2:
                # Evitar chocar con la automatización de Femenino o Mayores vs Menores ya hecha
                if any("FEMENINO" in t for t in [t1, t2]) or (any("MAYORES" in t for t in [t1, t2]) and any("MENORES" in t for t in [t1, t2])):
                    continue
                    
                reglas.append({
                    "tipo": r["tipo"],
                    "club": r["clubA"],
                    "torneo1": t1,
                    "torneo2": t2,
                    "hard": r.get("hard", False)
                })
        else:
            t1 = map_bloque_to_torneo(r["bloqueA"], r["clubA"], clubes)
            t2 = map_bloque_to_torneo(r["bloqueB"], r["clubB"], clubes)
            if t1 and t2:
                if any(x in [t1, t2] for x in ["FEMENINO-MAYORES", "FEMENINO-MENORES"]) and any("MAYORES" in t for t in [t1, t2]):
                    continue
                    
                reglas.append({
                    "tipo": r["tipo"],
                    "clubA": r["clubA"],
                    "clubB": r["clubB"],
                    "torneo1": t1,
                    "torneo2": t2,
                    "hard": r.get("hard", False)
                })

    # 2. Procesar y limpiar reglas (esquema normalizado)
    firmas_vistas = {}
    for r in reglas:
        origen = r.get('clubA', r.get('club'))
        destino = r.get('clubB', r.get('club'))
        t1 = r.get('torneo1')
        t2 = r.get('torneo2')
        tipo = r.get('tipo')

        if not t1 or not t2: continue

        par = tuple(sorted([(str(origen), str(t1)), (str(destino), str(t2))]))
        firmas_vistas[par] = {
            "tipo": tipo,
            "equipo_origen": origen,
            "torneo_origen": t1,
            "equipo_destino": destino,
            "torneo_destino": t2,
            "hard": r.get("hard", False)
        }

    reglas_limpias = list(firmas_vistas.values())

    nuevo_json = {
        "clubes": list(clubes.values()),
        "torneos": list(torneos.values()),
        "reglas_institucionales": reglas_limpias
    }
    
    with open("equipos_tiras.json", "w", encoding="utf-8") as f:
        json.dump(nuevo_json, f, indent=4, ensure_ascii=False)
        
    print("Migración a tiras completada y limpiada en equipos_tiras.json")

def map_bloque_to_torneo(bloque, club_name, clubes):
    if not club_name in clubes: return None
    c_data = clubes[club_name]
    
    if bloque == "MAYORES":
        div = c_data.get('division_mayores')
        return f"MAYORES-{div}" if div else None
    elif bloque in ["JUVENILES", "INFANTILES"]:
        div = c_data.get('division_menores')
        return f"MENORES-{div}" if div else None
    elif bloque == "FEM_MAYORES":
        return "FEMENINO-MAYORES"
    elif bloque == "FEM_MENORES":
        return "FEMENINO-MENORES"
    return None

if __name__ == "__main__":
    migrate()
