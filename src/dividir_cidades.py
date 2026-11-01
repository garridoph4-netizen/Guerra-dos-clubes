"""Monta o tabuleiro inicial da guerra.

1. Cidades com varios clubes sao fatiadas em partes de area igual (uma por clube).
2. Recalcula as fronteiras entre todas as unidades (municipios inteiros + fatias).
3. EXPANSAO INICIAL: cada clube cresce a partir da sua cidade pelo caminho mais
   curto ate cobrir o Brasil inteiro (cada unidade fica com o clube mais proximo).
   Cada unidade recebe um numero de "onda" (usado para animar a expansao).

Gera:
  data/unidades.geojson.gz  (geometrias das unidades, com dono e onda)
  data/territorios.json     (clubes, unidades, vizinhanca)
"""
import csv
import gzip
import heapq
import json
import math
import os

from shapely.affinity import affine_transform
from shapely.geometry import box, shape, mapping

from fronteiras import calcular_adjacencia, componentes, corrigir, normalizar

ENTRADA_GEO = os.path.join("data", "municipios.geojson.gz")
ENTRADA_CLUBES = os.path.join("data", "clubes.csv")
SAIDA_GEO = os.path.join("data", "unidades.geojson.gz")
SAIDA_JSON = os.path.join("data", "territorios.json")
NUM_ONDAS = 60


# ---------- fatiar cidades ----------

def so_poligonos(g):
    g = corrigir(g)
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    partes = [x for x in getattr(g, "geoms", []) if x.geom_type in ("Polygon", "MultiPolygon")]
    if not partes:
        return g
    from shapely import union_all
    return union_all(partes)


def fatiar(poly, k):
    """Divide poly em k faixas de area igual ao longo do eixo mais comprido."""
    poly = corrigir(poly)
    ret = poly.minimum_rotated_rectangle
    c = list(ret.exterior.coords)
    l1 = math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1])
    l2 = math.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1])
    if l1 >= l2:
        dx, dy = (c[1][0] - c[0][0]) / l1, (c[1][1] - c[0][1]) / l1
    else:
        dx, dy = (c[2][0] - c[1][0]) / l2, (c[2][1] - c[1][1]) / l2
    ida = [dx, dy, -dy, dx, 0, 0]
    volta = [dx, -dy, dy, dx, 0, 0]
    pr = affine_transform(poly, ida)
    tmin, tmax = pr.bounds[0], pr.bounds[2]
    total = pr.area

    def area_ate(t):
        return pr.intersection(box(tmin - 1, -1000, t, 1000)).area

    cortes = [tmin - 1]
    for i in range(1, k):
        alvo = total * i / k
        lo, hi = tmin, tmax
        for _ in range(40):
            meio = (lo + hi) / 2
            if area_ate(meio) < alvo:
                lo = meio
            else:
                hi = meio
        cortes.append((lo + hi) / 2)
    cortes.append(tmax + 1)

    partes = []
    for i in range(k):
        faixa = pr.intersection(box(cortes[i], -1000, cortes[i + 1], 1000))
        partes.append(so_poligonos(affine_transform(faixa, volta)))
    return partes


# ---------- expansao ----------

def expandir(centros, vizinhos, dono_inicial, fator_lon=1.0):
    """Dijkstra multi-origem. Devolve (dono, distancia) por unidade.

    centros: lista de (lon, lat); vizinhos: lista de listas de indices;
    dono_inicial: lista com indice do clube ou None.
    """
    n = len(centros)
    inf = float("inf")
    dist = [inf] * n
    dono = [None] * n
    fila = []
    for u in range(n):
        if dono_inicial[u] is not None:
            dist[u] = 0.0
            dono[u] = dono_inicial[u]
            heapq.heappush(fila, (0.0, dono[u], u))
    while fila:
        d, c, u = heapq.heappop(fila)
        if d > dist[u] or (d == dist[u] and c != dono[u]):
            continue
        for v in vizinhos[u]:
            w = math.hypot((centros[u][0] - centros[v][0]) * fator_lon,
                           centros[u][1] - centros[v][1]) + 1e-9
            nd = d + w
            if nd < dist[v] - 1e-12 or (abs(nd - dist[v]) <= 1e-12 and dono[v] is not None and c < dono[v]):
                dist[v] = nd
                dono[v] = c
                heapq.heappush(fila, (nd, c, v))
    # ilhas (sem ligacao por terra): ficam com o clube da unidade dona mais proxima
    donas = [u for u in range(n) if dono[u] is not None]
    ilhas = [u for u in range(n) if dono[u] is None]
    for u in ilhas:
        melhor = min(donas, key=lambda x: math.hypot(
            (centros[u][0] - centros[x][0]) * fator_lon, centros[u][1] - centros[x][1]))
        dono[u] = dono[melhor]
        dist[u] = inf
    return dono, dist, ilhas


def main():
    with gzip.open(ENTRADA_GEO, "rt", encoding="utf-8") as arq:
        feats = json.load(arq)["features"]
    with open(ENTRADA_CLUBES, encoding="utf-8") as arq:
        clubes = list(csv.DictReader(arq))

    indice = {}
    for f in feats:
        p = f["properties"]
        indice[(normalizar(p["nome"]), p["uf"])] = p["codigo"]
    clubes_do_mun = {}
    for i, c in enumerate(clubes):
        cod = indice[(normalizar(c["cidade"]), c["uf"])]
        c["codigo"] = cod
        clubes_do_mun.setdefault(cod, []).append(i)

    # 1. unidades (municipios inteiros ou fatias)
    unidades = []
    corrigidas = []
    for f in feats:
        p = f["properties"]
        bruta = shape(f["geometry"])
        geom = so_poligonos(bruta)
        if (not bruta.is_valid) or bruta.area <= 0:
            corrigidas.append(f'{p["nome"]}/{p["uf"]}')
        donos = clubes_do_mun.get(p["codigo"], [])
        if len(donos) <= 1:
            unidades.append({"id": p["codigo"], "nome": p["nome"], "uf": p["uf"],
                             "geom": geom, "clube": donos[0] if donos else None,
                             "inicial": bool(donos)})
        else:
            fatias = fatiar(geom, len(donos))
            for k, (idx, parte) in enumerate(zip(donos, fatias), start=1):
                unidades.append({"id": f'{p["codigo"]}-{k}', "nome": f'{p["nome"]} ({k})',
                                 "uf": p["uf"], "geom": parte, "clube": idx,
                                 "inicial": True})
    divididas = sum(1 for v in clubes_do_mun.values() if len(v) > 1)
    print(f"{len(unidades)} unidades ({divididas} cidades divididas entre varios clubes)")
    print(f"Geometrias invalidas corrigidas: {len(corrigidas)}"
          + (" (" + ", ".join(corrigidas[:12]) + ")" if corrigidas else ""))
    ruins = [u["nome"] for u in unidades if not (u["geom"].area > 0)]
    print(f"Unidades com area zero ou negativa apos correcao: {len(ruins)}"
          + (" (" + ", ".join(ruins[:12]) + ")" if ruins else ""))

    # 2. fronteiras entre unidades
    print("Calculando fronteiras entre unidades...")
    pares = calcular_adjacencia([u["geom"] for u in unidades])
    viz = [[] for _ in unidades]
    for a, b in pares:
        viz[a].append(b)
        viz[b].append(a)
    print(f"{len(pares)} pares de vizinhos")

    # 3. expansao inicial
    centros = []
    for u in unidades:
        pt = u["geom"].centroid
        centros.append((pt.x, pt.y))
    lat_media = sum(c[1] for c in centros) / len(centros)
    fator = math.cos(math.radians(lat_media))
    dono, dist, ilhas = expandir(centros, viz, [u["clube"] for u in unidades], fator)
    finitas = [d for d in dist if d != float("inf")]
    passo = max(finitas) / NUM_ONDAS if finitas else 1.0
    for i, u in enumerate(unidades):
        u["dono"] = dono[i]
        if u["inicial"]:
            u["onda"] = 0
        elif dist[i] == float("inf"):
            u["onda"] = NUM_ONDAS + 1
        else:
            u["onda"] = 1 + min(NUM_ONDAS - 1, int(dist[i] / passo))
    print(f"Expansao: {NUM_ONDAS} ondas, {len(ilhas)} unidade(s) de ilha: "
          + ", ".join(unidades[i]["nome"] for i in ilhas))

    # relatorio
    qtd = [0] * len(clubes)
    area = [0.0] * len(clubes)
    for u in unidades:
        qtd[u["dono"]] += 1
        area[u["dono"]] += u["geom"].area
    ordem = sorted(range(len(clubes)), key=lambda i: -area[i])
    total_area = sum(area)
    print("--- MAIORES TERRITORIOS (apos expansao) ---")
    for i in ordem[:5]:
        print(f'  {clubes[i]["clube"]}: {qtd[i]} unidades, {100 * area[i] / total_area:.1f}% da area')
    print("--- MENORES TERRITORIOS ---")
    for i in ordem[-5:]:
        print(f'  {clubes[i]["clube"]}: {qtd[i]} unidades, {100 * area[i] / total_area:.2f}% da area')

    viz_clube = [set() for _ in clubes]
    for a, b in pares:
        if dono[a] != dono[b]:
            viz_clube[dono[a]].add(dono[b])
            viz_clube[dono[b]].add(dono[a])
    sem = [clubes[i]["clube"] for i in range(len(clubes)) if not viz_clube[i]]
    pares_clubes = sum(len(s) for s in viz_clube) // 2
    grupos = componentes(len(clubes), [(a, b) for a in range(len(clubes)) for b in viz_clube[a] if a < b])
    print(f"Pares de clubes vizinhos: {pares_clubes}; blocos de clubes: {len(grupos)} "
          f"(maior: {len(grupos[0])})")
    print("Clubes sem nenhum vizinho:", ", ".join(sem) if sem else "nenhum")

    # saidas
    def arred(co):
        if isinstance(co[0], (int, float)):
            return [round(co[0], 5), round(co[1], 5)]
        return [arred(x) for x in co]

    out = []
    for i, u in enumerate(unidades):
        g = mapping(u["geom"])
        out.append({"type": "Feature",
                    "properties": {"id": u["id"], "nome": u["nome"], "uf": u["uf"],
                                   "dono": u["dono"], "onda": u["onda"]},
                    "geometry": {"type": g["type"], "coordinates": arred(g["coordinates"])}})
    with gzip.open(SAIDA_GEO, "wt", encoding="utf-8") as arq:
        json.dump({"type": "FeatureCollection", "features": out}, arq,
                  ensure_ascii=False, separators=(",", ":"))

    ids = [u["id"] for u in unidades]
    info = {
        "clubes": [{"id": i, "nome": c["clube"], "serie": c["serie"], "cidade": c["cidade"],
                    "uf": c["uf"], "cor1": c["cor1"], "cor2": c["cor2"],
                    "unidades": qtd[i]} for i, c in enumerate(clubes)],
        "unidades": [{"id": u["id"], "nome": u["nome"], "uf": u["uf"], "dono": u["dono"],
                      "onda": u["onda"], "inicial": u["inicial"],
                      "vizinhos": [ids[v] for v in sorted(viz[i])]}
                     for i, u in enumerate(unidades)],
        "num_ondas": NUM_ONDAS,
    }
    with open(SAIDA_JSON, "w", encoding="utf-8") as arq:
        json.dump(info, arq, ensure_ascii=False, separators=(",", ":"))
    print(f"Arquivos gerados: {SAIDA_GEO} ({os.path.getsize(SAIDA_GEO) / 1e6:.1f} MB), "
          f"{SAIDA_JSON} ({os.path.getsize(SAIDA_JSON) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
