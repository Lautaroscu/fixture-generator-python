import json

def verify_localia():
    with open("fixture.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    fechas = {}
    for f in data:
        nro = f["nroFecha"]
        liga = f["liga"]
        if nro not in fechas: fechas[nro] = {}
        fechas[nro][liga] = f["partidos"]
        
    def is_local(partidos, team):
        for p in partidos:
            if p["local"] == team: return True
            if p["visitante"] == team: return False
        return None
        
    fallos = []
    
    for nro, ligas in fechas.items():
        # 1. Juarense (INVERSO)
        j_may = is_local(ligas.get("MAYORES-A", []), "Juarense")
        j_fem = is_local(ligas.get("FEMENINO-A", []), "Juarense")
        if j_may is not None and j_fem is not None and j_may == j_fem:
            fallos.append(f"F{nro}: Juarense BOTH {'LOCAL' if j_may else 'VISITANTE'}")
            
        # 2. Independiente Rojo (MAYORES-B) y Independiente (FEMENINO-A) (ESPEJO)
        i_may = is_local(ligas.get("MAYORES-B", []), "Independiente (rojo)")
        i_fem = is_local(ligas.get("FEMENINO-A", []), "Independiente")
        if i_may is not None and i_fem is not None and i_may != i_fem:
            fallos.append(f"F{nro}: Independiente Rojo={i_may}, Fem={i_fem}")
            
        # 3. Ferro Azul (MENORES-B) y Ferrocarril Sud (FEMENINO-A) (ESPEJO)
        fa_men = is_local(ligas.get("MENORES-B", []), "Ferro Azul")
        fs_fem = is_local(ligas.get("FEMENINO-A", []), "Ferrocarril Sud")
        if fa_men is not None and fs_fem is not None and fa_men != fs_fem:
            fallos.append(f"F{nro}: Ferro Azul={fa_men}, Fem={fs_fem}")
            
        # 4. Loma Negra (ESPEJO)
        ln_may = is_local(ligas.get("MAYORES-B", []), "Loma Negra")
        ln_fem = is_local(ligas.get("FEMENINO-A", []), "Loma Negra")
        if ln_may is not None and ln_fem is not None and ln_may != ln_fem:
            fallos.append(f"F{nro}: Loma Negra Mayores={ln_may}, Fem={ln_fem}")

        # 5. Ayacucho (Sarmiento vs Ateneo)
        sa_may = is_local(ligas.get("MAYORES-A", []), "SARMIENTO AYACUCHO")
        ae_may = is_local(ligas.get("MAYORES-B", []), "ATENEO ESTRADA")
        if sa_may is not None and ae_may is not None and sa_may == ae_may:
            fallos.append(f"F{nro}: Sarmiento y Ateneo BOTH {'LOCAL' if sa_may else 'VISITANTE'}")

    return fallos

if __name__ == "__main__":
    fallos = verify_localia()
    if fallos:
        print(f"FAILED: {len(fallos)} constraint violations:")
        for f in fallos: print(f" - {f}")
    else:
        print("SUCCESS: All constraints valid!")
