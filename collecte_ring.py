#!/usr/bin/env python3
"""
Collecte MIV -> ring.json
Lit selection_ring.json (boucles retenues), télécharge le flux minute,
agrège par segment/direction et écrit ring.json pour la PWA.
Stdlib only.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

DATA_URL = "http://miv.opendata.belfla.be/miv/verkeersdata"
SELECTION = "selection_ring.json"
OUTPUT = "ring.json"

# Classes de véhicules retenues : 2 = voitures, 3 = camionnettes,
# 4 = camions rigides, 5 = semi-remorques (classe 1 non fiable)
KLASSEN = {"2", "3", "4", "5"}
SPEED_INVALID = 250  # au-delà : valeur sentinelle (pas de passage / capteur muet)


def main():
    with open(SELECTION, encoding="utf-8") as f:
        selection = json.load(f)

    # id boucle -> (segment, direction, kmp, nom)
    lookup = {}
    for seg, directions in selection.items():
        for ident8, pts in directions.items():
            for p in pts:
                lookup[str(p["id"])] = (seg, ident8, p["kmp"], p["naam"])

    req = urllib.request.Request(DATA_URL, headers={"User-Agent": "azertida-radar-ring/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        root = ET.parse(resp).getroot()

    publicatie = root.findtext("tijd_publicatie")

    # Mesures valides : {(seg, dir): {kmp: [(vitesse, intensite), ...]}}
    mesures = defaultdict(lambda: defaultdict(list))
    noms = {}

    for mp in root.iter("meetpunt"):
        uid = mp.get("unieke_id")
        if uid not in lookup:
            continue
        seg, ident8, kmp, naam = lookup[uid]
        noms[(seg, ident8, kmp)] = naam

        for md in mp.iter("meetdata"):
            if md.get("klasse_id") not in KLASSEN:
                continue
            try:
                intensiteit = int(md.findtext("verkeersintensiteit") or 0)
                snelheid = int(md.findtext("voertuigsnelheid_harmonisch") or 0)
            except ValueError:
                continue
            if intensiteit > 0 and 0 < snelheid < SPEED_INVALID:
                mesures[(seg, ident8)][kmp].append((snelheid, intensiteit))

    resultat = {"publicatie": publicatie, "segments": {}}

    for (seg, ident8), par_kmp in sorted(mesures.items()):
        emplacements = []
        for kmp, obs in sorted(par_kmp.items()):
            poids = sum(i for _, i in obs)
            v_moy = round(sum(v * i for v, i in obs) / poids)
            emplacements.append({
                "kmp": kmp,
                "naam": noms[(seg, ident8, kmp)],
                "vitesse": v_moy,
                "vehicules_min": poids,
            })

        if not emplacements:
            continue

        poids_total = sum(e["vehicules_min"] for e in emplacements)
        v_segment = round(sum(e["vitesse"] * e["vehicules_min"] for e in emplacements) / poids_total)
        pire = min(emplacements, key=lambda e: e["vitesse"])

        cle = f"{seg}_{ident8}"
        resultat["segments"][cle] = {
            "segment": seg,
            "ident8": ident8,
            "vitesse_moyenne": v_segment,
            "point_le_plus_lent": {"naam": pire["naam"], "vitesse": pire["vitesse"], "kmp": pire["kmp"]},
            "emplacements_actifs": len(emplacements),
            "detail": emplacements,
        }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=1)

    for cle, s in resultat["segments"].items():
        print(f"{cle}: {s['vitesse_moyenne']} km/h "
              f"(min {s['point_le_plus_lent']['vitesse']} @ {s['point_le_plus_lent']['naam']})")


if __name__ == "__main__":
    main()
