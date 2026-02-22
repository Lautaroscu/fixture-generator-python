import json

def limpiar_fixture(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Inyectar entidad faltante: Alumni/Defensores
    if not any(c['nombre'] == "Alumni/Defensores" for c in data['clubes']):
        data['clubes'].append({
            "nombre": "Alumni/Defensores",
            "estadioLocal": "Ferroviarios",
            "estadioPropio": False,
            "categorias_activas": ["quinta", "sexta", "septima", "octava", "novena", "decima"],
            "division_mayores": None,
            "division_menores": "B",
            "division_femenino": None
        })
        
        # Agregarlo al torneo correspondiente
        for t in data['torneos']:
            if t['id'] == "MENORES-B" and "Alumni/Defensores" not in t['participantes']:
                t['participantes'].append("Alumni/Defensores")

    # 2. Procesar y limpiar reglas
    reglas_limpias = []
    firmas_vistas = set()

    for r in data.get('reglas_institucionales', []):
        origen = r.get('clubA', r.get('club'))
        destino = r.get('clubB', r.get('club'))
        t1 = r.get('torneo1')
        t2 = r.get('torneo2')
        tipo = r.get('tipo')

        # Ignorar reglas corruptas con "None"
        if not t1 or not t2 or "None" in str(t1) or "None" in str(t2):
            continue

        # Crear firma única para detectar duplicados (orden alfabético para simetría)
        par = tuple(sorted([(origen, t1), (destino, t2)]))
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

    data['reglas_institucionales'] = reglas_limpias

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print(f"Limpieza completa. Reglas originales: {len(data.get('reglas_institucionales', []))}. Reglas finales: {len(reglas_limpias)}")

if __name__ == "__main__":
    limpiar_fixture("fixture_raw.json", "fixture_clean.json")