import json

def verify_fixture():
    print("Verificando fixture.json...")
    with open("fixture.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    fechas = {}
    
    # Agrupar por fecha -> liga -> partidos
    for f in data:
        nro = f["nroFecha"]
        liga = f["liga"]
        partidos = f["partidos"]
        
        if nro not in fechas:
            fechas[nro] = {}
        fechas[nro][liga] = partidos

    # Test 1: Oficina vs Santamarina (Femenino)
    # Regla: ESPEJO (Juegan juntos de local o de visitante)
    # Oficina en MAYORES-B, Santamarina en FEMENINO-A
    fallos_oficina = 0
    print("\n--- TEST: OFICINA (MAYORES-B) vs SANTAMARINA (FEMENINO-A) [ESPEJO] ---")
    
    for nro, ligas in fechas.items():
        if "MAYORES-B" not in ligas or "FEMENINO-A" not in ligas:
            continue
            
        oficina_local = False
        santamarina_fem_local = False
        
        for p in ligas["MAYORES-B"]:
            if p["local"] == "Oficina": oficina_local = True
            
        for p in ligas["FEMENINO-A"]:
            if p["local"] == "Santamarina": santamarina_fem_local = True
            
        # Si ambos false (ambos de visitante) o ambos true (ambos de local) -> OK
        if oficina_local != santamarina_fem_local:
            print(f"FALLO Fecha {nro}: Oficina Local={oficina_local}, Santamarina Fem Local={santamarina_fem_local}")
            fallos_oficina += 1
            
    if fallos_oficina == 0:
        print("EXITO! Oficina y Santamarina Femenino siempre juegan en la misma condicion.")
    else:
        print(f"ERROR: Se encontraron {fallos_oficina} fallos en la condicion.")

    # Test 2: Loma Negra (Mayores) vs Loma Negra (Menores)
    # Regla: ESPEJO (Juegan juntos)
    # Loma Negra en MAYORES-B, Loma Negra en MENORES-A
    fallos_loma = 0
    print("\n--- TEST: LOMA NEGRA (MAYORES-B) vs LOMA NEGRA (MENORES-A) [ESPEJO] ---")
    
    for nro, ligas in fechas.items():
        if "MAYORES-B" not in ligas or "MENORES-A" not in ligas:
            continue
            
        loma_may_local = False
        loma_men_local = False
        
        for p in ligas["MAYORES-B"]:
            if p["local"] == "Loma Negra": loma_may_local = True
            
        for p in ligas["MENORES-A"]:
            if p["local"] == "Loma Negra": loma_men_local = True
            
        # Si son distintos (uno local y otro visitante) -> FALLO
        if loma_may_local != loma_men_local:
            print(f"FALLO Fecha {nro}: Loma Negra Mayores Local={loma_may_local}, Menores Local={loma_men_local}")
            fallos_loma += 1
            
    if fallos_loma == 0:
        print("EXITO! Loma Negra Mayores y Menores siempre juegan en la misma condicion.")
    else:
        print(f"ERROR: Se encontraron {fallos_loma} fallos en la condicion.")

if __name__ == "__main__":
    verify_fixture()
