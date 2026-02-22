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
                "estadioLocal": eq.get("estadioLocal", ""),
                "estadioPropio": eq.get("estadioPropio", True),
                "categorias_activas": [],
                "division_mayores": None,
                "division_menores": None, # Usaremos la de infantiles si difiere
            }
        
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
        tiene_menores = any(k in cats for k in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"])
        if tiene_menores:
            div = c_data.get("division_menores", "A")
            t_id = f"MENORES-{div}"
            if t_id not in torneos:
                torneos[t_id] = {"id": t_id, "nombre": f"Tira Juveniles e Infantiles - Liga {div}", "participantes": []}
            torneos[t_id]["participantes"].append(c_name)
            
        # Tiene Femenino?
        tiene_femenino = any("femenino" in k for k in cats)
        if tiene_femenino:
            t_id = f"FEMENINO-A"
            if t_id not in torneos:
                torneos[t_id] = {"id": t_id, "nombre": f"Tira Femenina - Liga A", "participantes": []}
            torneos[t_id]["participantes"].append(c_name)
            
    # Reglas Institucionales
    # Las viejas reglas mapeaban INVERSO o ESPEJO entre bloques.
    # En el nuevo modelo, los bloques son los propios Torneos.
    # Si un club juega Mayores e Inferiores, deberian ser INVERSOS por default (para no saturar cancha).
    # Vamos a generar reglas automáticas de INVERSO para Mismo Club (Mayores vs Menores)
    reglas = []
    for c_name, c_data in clubes.items():
        cats = c_data["categorias_activas"]
        tiene_mayores = "primera" in cats or "reserva" in cats
        tiene_menores = any(k in cats for k in ["quinta", "sexta", "septima", "octava", "novena", "decima", "undecima"])
        
        if tiene_mayores and tiene_menores:
            div_may = c_data.get("division_mayores", "A")
            div_men = c_data.get("division_menores", "A")
            reglas.append({
                "tipo": "INVERSO",
                "club": c_name,
                "torneo1": f"MAYORES-{div_may}",
                "torneo2": f"MENORES-{div_men}"
            })
            
        tiene_femenino = any("femenino" in k for k in cats)
        if tiene_femenino and tiene_mayores:
            div_may = c_data.get("division_mayores", "A")
            # Por defecto femenino cruza cruzado (ESPEJO) con el masculino
            tipo_fem = "ESPEJO"
            # Excepciones que van juntos (INVERSO) por compartir tira completa en mismo estadio
            if c_name in ["Loma Negra", "Independiente", "Independiente (rojo)"]:
                tipo_fem = "INVERSO"
                
            reglas.append({
                "tipo": tipo_fem,
                "club": c_name,
                "torneo1": f"MAYORES-{div_may}",
                "torneo2": "FEMENINO-A"
            })
            
    # Añadir las reglas explícitas viejas adaptadas
    for r in data.get("reglas", []):
        # Ej: "clubA": "Independiente", "clubB": "Independiente", "bloqueA": "MAYORES", "bloqueB": "FEM_MAYORES"
        if r["clubA"] == r["clubB"]:
            # Regla interna del club
            t1 = map_bloque_to_torneo(r["bloqueA"], r["clubA"], clubes)
            t2 = map_bloque_to_torneo(r["bloqueB"], r["clubB"], clubes)
            if t1 and t2 and t1 != t2:
                # Si una de las reglas viejas intentaba vincular MAYORES con FEMENINO la ignoramos 
                # porque ya fue cubierta en la generación automática de arriba
                if "FEMENINO-A" in [t1, t2] and any("MAYORES" in t for t in [t1, t2]):
                    continue
                    
                # Evitar duplicados
                existe = any(x.get("club") == r["clubA"] and ((x["torneo1"] == t1 and x["torneo2"] == t2) or (x["torneo1"] == t2 and x["torneo2"] == t1)) for x in reglas)
                if not existe:
                    reglas.append({
                        "tipo": r["tipo"],
                        "club": r["clubA"],
                        "torneo1": t1,
                        "torneo2": t2
                    })
        else:
            # Regla de estadios compartidos entre distintos clubes
            t1 = map_bloque_to_torneo(r["bloqueA"], r["clubA"], clubes)
            t2 = map_bloque_to_torneo(r["bloqueB"], r["clubB"], clubes)
            if t1 and t2:
                # Evitar chocar con la automatizacion de Femenino de la misma institucion
                base_a = r["clubA"].split("(")[0].strip()
                base_b = r["clubB"].split("(")[0].strip()
                if base_a == base_b and "FEMENINO-A" in [t1, t2] and any("MAYORES" in t for t in [t1, t2]):
                    continue
                    
                reglas.append({
                    "tipo": r["tipo"],
                    "clubA": r["clubA"],
                    "clubB": r["clubB"],
                    "torneo1": t1,
                    "torneo2": t2
                })

    # Aplicar la limpieza final (esquema unificado, sin duplicados, inyeccion de entidades)
    # 1. Inyectar entidad faltante: Alumni/Defensores (Fusión Menores)
    if not any(c['nombre'] == "Alumni/Defensores" for c in clubes.values()):
        clubes["Alumni/Defensores"] = {
            "nombre": "Alumni/Defensores",
            "estadioLocal": "Ferroviarios",
            "estadioPropio": False,
            "categorias_activas": ["quinta", "sexta", "septima", "octava", "novena", "decima"],
            "division_mayores": None,
            "division_menores": "B",
            "division_femenino": None
        }
    
    torneos_list = list(torneos.values())
    for t in torneos_list:
        if t['id'] == "MENORES-B" and "Alumni/Defensores" not in t['participantes']:
            t['participantes'].append("Alumni/Defensores")

    # 2. Procesar y limpiar reglas (esquema normalizado)
    reglas_limpias = []
    firmas_vistas = set()

    for r in reglas:
        origen = r.get('clubA', r.get('club'))
        destino = r.get('clubB', r.get('club'))
        t1 = r.get('torneo1')
        t2 = r.get('torneo2')
        tipo = r.get('tipo')

        # Ignorar reglas corruptas con "None"
        if not t1 or not t2 or "None" in str(t1) or "None" in str(t2):
            continue

        # Crear firma única para detectar duplicados (orden alfabético para simetría)
        par = tuple(sorted([(str(origen), str(t1)), (str(destino), str(t2))]))
        firma = (tipo, par)

        if firma not in firmas_vistas:
            firmas_vistas.add(firma)
            reglas_limpias.append({
                "tipo": tipo,
                "equipo_origen": origen,
                "torneo_origen": t1,
                "equipo_destino": destino,
                "torneo_destino": t2
            })

    # Regla espejo explícita para la fusión
    reglas_limpias.append({
        "tipo": "ESPEJO",
        "equipo_origen": "Alumni/Defensores",
        "torneo_origen": "MENORES-B",
        "equipo_destino": "Alumni",
        "torneo_destino": "MAYORES-B"
    })

    nuevo_json = {
        "clubes": list(clubes.values()),
        "torneos": torneos_list,
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
    elif bloque in ["FEM_MAYORES", "FEM_MENORES"]:
        if c_data.get('division_femenino'):
            return "FEMENINO-A"
        return None
    return None

if __name__ == "__main__":
    migrate()
