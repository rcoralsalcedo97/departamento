"""Generate SYNTHETIC fixtures (fake listings + fake map layers) for tests and the format preview.

Everything here is invented: example.com URLs, '(DEMO)' names, landline-style numbers that
cannot produce WhatsApp links, and a square 'district' boundary. Run:
    python tests/fixtures/make_synthetic.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).parent
rng = random.Random(42)

# ------------------------------------------------------------------ synthetic map (square district)
N_LAT, S_LAT, W_LON, E_LON = -12.105, -12.135, -77.055, -77.010


def node(i, lat, lon, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


def way(i, pts, **tags):
    return {"type": "way", "id": i, "geometry": [{"lat": a, "lon": b} for a, b in pts], "tags": tags}


def square(lat, lon, d=0.0012):
    return [(lat - d, lon - d), (lat - d, lon + d), (lat + d, lon + d), (lat + d, lon - d), (lat - d, lon - d)]


elements = [
    {"type": "relation", "id": 1, "tags": {"boundary": "administrative", "admin_level": "8", "name": "Miraflores"},
     "members": [{"type": "way", "role": "outer", "geometry": [{"lat": a, "lon": b} for a, b in
                                                               [(N_LAT, W_LON), (N_LAT, E_LON), (S_LAT, E_LON),
                                                                (S_LAT, W_LON), (N_LAT, W_LON)]]}]},
    way(10, [(-12.100, -77.030), (-12.140, -77.030)], highway="primary", name="Av. Demo Arterial (DEMO)"),
    way(11, [(-12.100, -77.0195), (-12.140, -77.0195)], highway="motorway", name="Vía Demo Expresa (DEMO)"),
    way(12, [(-12.120, -77.058), (-12.120, -77.005)], highway="secondary", name="Calle Demo Secundaria (DEMO)"),
    way(13, [(-12.106, -77.0505), (-12.134, -77.0505)], highway="residential", name="Malecón Demo (DEMO)"),
    node(20, -12.1212, -77.0312, amenity="nightclub", name="Discoteca Demo (DEMO)"),
]
k = 100
for dlat, dlon in [(0.0003, 0.0002), (-0.0004, 0.0006), (0.0007, -0.0001), (0.0001, 0.0009), (-0.0008, 0.0004)]:
    elements.append(node(k, -12.1215 + dlat, -77.0305 + dlon, amenity="bar", name=f"Bar Demo {k} (DEMO)"))
    k += 1
for _ in range(14):
    elements.append(node(k, -12.1215 + rng.uniform(-0.0012, 0.0012), -77.0305 + rng.uniform(-0.0012, 0.0012),
                         amenity="restaurant", name=f"Restaurante Demo {k}"))
    k += 1
for lat, lon in [(-12.110, -77.040), (-12.125, -77.045), (-12.130, -77.025), (-12.115, -77.022)]:
    elements.append(node(k, lat, lon, shop="supermarket", name=f"Súper Demo {k}"))
    elements.append(node(k + 1, lat + 0.001, lon - 0.001, amenity="pharmacy", name=f"Farmacia Demo {k}"))
    elements.append(node(k + 2, lat - 0.001, lon + 0.001, amenity="cafe", name=f"Café Demo {k}"))
    k += 3
for lat in (-12.108, -12.115, -12.122, -12.129):
    elements.append(node(k, lat, -77.0297, highway="bus_stop", name=f"Paradero Demo {k}"))
    k += 1
for lat, lon in [(-12.112, -77.046), (-12.127, -77.038), (-12.118, -77.015)]:
    elements.append(way(k, square(lat, lon), leisure="park", name=f"Parque Demo {k}"))
    k += 1
(HERE / "synthetic_osm.json").write_text(json.dumps({"elements": elements, "_fetched_at": "2026-09-24T00:00:00+00:00",
                                                    "_endpoint": "SYNTHETIC"}, indent=1), encoding="utf-8")

# ------------------------------------------------------------------ synthetic listings
DESCS = [
    "Departamento {furn} con vista interior, muy tranquilo, ventanas con doble vidrio. Cocina equipada, "
    "lavandería independiente, closets amplios. Edificio con ascensor y vigilancia 24 horas. Contrato mínimo 1 año, "
    "2 meses de garantía y 1 mes de adelanto. Mantenimiento S/ {maint}.",
    "Lindo depa {furn} con balcón y vista a la avenida, a pocos pasos del parque. Portería 24h, zona de parrilla. "
    "Se aceptan mascotas pequeñas. Garantía: dos meses. Contrato de 12 meses.",
    "Flat {furn} en piso {floor}, iluminado, cerca de supermercados y del malecón. Terraza, estudio / home office. "
    "Edificio con gimnasio y piscina. Mantenimiento aprox. {maint} soles.",
    "Departamento {furn}, calle tranquila y residencial, contrafrente. Dos baños completos, walk-in closet. "
    "Incluye estacionamiento. Contrato mínimo 6 meses.",
    "Departamento {furn} frente a la avenida principal, ideal para ejecutivos. Recepción 24 horas, coworking.",
]
FURN = ["amoblado", "semi-amoblado", "sin amoblar", "totalmente amoblado", ""]

records = []
spots = [  # lat, lon, note — chosen to exercise the noise model
    (-12.112, -77.047, "quiet west"), (-12.118, -77.044, "quiet west"), (-12.128, -77.046, "near malecon"),
    (-12.1214, -77.0310, "nightlife"), (-12.1217, -77.0302, "nightlife"), (-12.1200, -77.0301, "on arterial"),
    (-12.110, -77.0197, "next to expressway"), (-12.126, -77.0198, "next to expressway"),
    (-12.132, -77.036, "south quiet"), (-12.108, -77.038, "north"), (-12.115, -77.025, "east"),
    (-12.124, -77.041, "center-west"), (-12.130, -77.028, "south-east"), (-12.117, -77.035, "center"),
]
lid = 1000
for i in range(34):
    lat, lon, _ = spots[i % len(spots)]
    lat += rng.uniform(-0.0015, 0.0015)
    lon += rng.uniform(-0.0012, 0.0012)
    beds = rng.choice([1, 1, 2, 2, 2])
    area = round(rng.uniform(36, 66) if beds == 1 else rng.uniform(52, 98))
    rent = round(rng.uniform(620, 1080) / 10) * 10
    maint = rng.choice([250, 300, 350, 420, 500, None])
    furn = rng.choice(FURN)
    floor = rng.randint(1, 14)
    desc = rng.choice(DESCS).format(furn=furn, maint=maint or 300, floor=floor)
    lid += 1
    src = "urbania" if i % 2 == 0 else "adondevivir"
    img = f"https://example.com/img/{lid:06d}abcdef1234-{lid}.jpg"
    if i % 3 == 0:   # flat actor-style shape
        rec = {"_source": src, "id": f"{lid}", "url": f"https://example.com/demo/{src}/{lid}",
               "title": f"Alquiler departamento {beds} dormitorio{'s' if beds > 1 else ''} Miraflores (DEMO {lid})",
               "description": desc, "price": rent, "currency": "USD",
               "expenses": f"S/ {maint}" if maint else None, "bedrooms": beds, "bathrooms": rng.choice([1, 1.5, 2]),
               "totalArea": area + rng.randint(0, 8), "coveredArea": area,
               "latitude": round(lat, 6), "longitude": round(lon, 6), "showExactLocation": rng.random() > 0.3,
               "address": f"Calle Ejemplo {100 + i} (DEMO)", "district": "Miraflores",
               "phone": f"+51 1 000 {1000 + i}", "publisherName": f"DEMO Inmobiliaria {chr(65 + i % 5)}",
               "publicationDate": f"2026-09-{rng.randint(1, 23):02d}", "images": [img] * rng.randint(3, 14),
               "amenities": rng.sample(["Ascensor", "Vigilancia 24 horas", "Lavandería", "Balcón", "Gimnasio"], 2)}
    else:            # Navent-native nested shape, priced in soles
        pen = round(rent * 3.385 / 50) * 50
        rec = {"_source": src, "postingId": f"{lid}", "url": f"/demo/{src}/{lid}.html",
               "title": f"Departamento en alquiler — {beds} dorm. (DEMO {lid})", "description": desc,
               "priceOperationTypes": [{"operationType": {"name": "Alquiler"},
                                        "prices": [{"amount": pen, "currency": "S/"}]}],
               "expenses": {"amount": maint, "currency": "S/"} if maint else None,
               "mainFeatures": {"CFT100": {"label": "Área total", "value": str(area + 5), "measure": "m²"},
                                "CFT101": {"label": "Área techada", "value": str(area), "measure": "m²"},
                                "CFT2": {"label": "Dormitorios", "value": str(beds)},
                                "CFT3": {"label": "Baños", "value": str(rng.choice([1, 2]))},
                                "CFT7": {"label": "Estacionamientos", "value": str(rng.choice([0, 1]))}},
               "postingLocation": {"address": {"name": f"Av. Ejemplo {200 + i} (DEMO)"},
                                   "location": {"name": "Miraflores", "parent": {"name": "Lima"}},
                                   "postingGeolocation": {"geolocation": {"latitude": round(lat, 6),
                                                                          "longitude": round(lon, 6)},
                                                          "showExactLocation": rng.random() > 0.4}},
               "publisher": {"name": f"DEMO Agente {chr(70 + i % 4)}"},
               "publishedText": f"Publicado hace {rng.randint(1, 60)} días",
               "visiblePictures": {"pictures": [{"url730x532": img} for _ in range(rng.randint(4, 12))]}}
    records.append(rec)

# cross-posted duplicate of record 0 on the other portal (same posting id + same photo)
dup = json.loads(json.dumps(records[0]))
dup["_source"] = "adondevivir"
dup["url"] = f"https://example.com/demo/adondevivir/{dup['id']}"
dup["price"] = records[0]["price"] + 20      # small price conflict between portals
records.append(dup)
# edge cases
records.append({**records[3], "id": "9001", "url": "https://example.com/demo/urbania/9001", "bedrooms": 0,
                "title": "Monoambiente tipo estudio (DEMO 9001)", "images": ["https://example.com/img/9001x.jpg"]})
records.append({**records[3], "id": "9002", "url": "https://example.com/demo/urbania/9002", "bedrooms": 3,
                "title": "Departamento 3 dormitorios (DEMO 9002)", "images": ["https://example.com/img/9002x.jpg"]})
records.append({**records[6], "id": "9003", "url": "https://example.com/demo/urbania/9003", "status": "FINALIZADO",
                "title": "Aviso finalizado (DEMO 9003)", "images": ["https://example.com/img/9003x.jpg"],
                "latitude": -12.113, "longitude": -77.042, "address": "Calle Inactiva 903 (DEMO)",
                "phone": "+51 1 000 9003", "description": "Aviso finalizado de prueba."})
records.append({**records[9], "id": "9004", "url": "https://example.com/demo/urbania/9004", "price": 1060,
                "title": "Stretch 2 dormitorios amplio (DEMO 9004)", "bedrooms": 2, "coveredArea": 96, "totalArea": 104,
                "images": ["https://example.com/img/9004x.jpg"], "latitude": -12.131, "longitude": -77.040,
                "address": "Calle Amplia 904 (DEMO)", "phone": "+51 1 000 9004",
                "description": "Departamento amplio de 96 m2, amoblado, vista interior, dos baños, lavandería."})
records.append({**records[12], "id": "9005", "url": "https://example.com/demo/urbania/9005", "price": 880,
                "latitude": -12.118, "longitude": -77.0085, "district": "Surquillo", "bedrooms": 2,
                "coveredArea": 88, "title": "Límite Miraflores, 2 dormitorios (DEMO 9005)",
                "description": "Vista interior, ventanas antirruido, amoblado, lavandería, vigilancia 24 horas.",
                "images": ["https://example.com/img/9005x.jpg"] * 10, "address": "Calle Borde 905 (DEMO)",
                "phone": "+51 1 000 9005"})
records.append({**records[12], "id": "9006", "url": "https://example.com/demo/urbania/9006", "price": 700,
                "latitude": -12.118, "longitude": -76.995, "district": "Surquillo",
                "title": "Lejos del límite (DEMO 9006)", "images": ["https://example.com/img/9006x.jpg"],
                "address": "Calle Lejana 906 (DEMO)", "phone": "+51 1 000 9006", "description": "Otro distrito."})
(HERE / "synthetic_navent.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {len(records)} synthetic listings and {len(elements)} synthetic map elements")
