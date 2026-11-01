"""Calcula quais municipios fazem fronteira de verdade (geometria real).

Dois municipios sao vizinhos se compartilham um trecho de divisa (nao basta
tocar em um unico ponto). Gera data/adjacencia.json: {codigo: [codigos vizinhos]}.
Tambem confere se todos os clubes ficam no mesmo "continente" de municipios.
"""
import csv
import gzip
import json
import os
import re
import unicodedata

import shapely
from shapely import STRtree
from shapely.geometry import shape

ENTRADA_GEO = os.path.join("data", "municipios.geojson.gz")
ENTRADA_CLUBES = os.path.join("data", "clubes.csv")
SAIDA = os.path.join("data", "adjacencia.json")

TOLERANCIA = 0.001       # graus (~110 m): cobre pequenas folgas da simplificacao
COMPRIMENTO_MIN = 0.004  # graus (~440 m): divisa minima; ignora toque em ponto


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def corrigir(g):
    """Conserta geometrias invalidas e garante que so sobrem poligonos."""
    g = shapely.make_valid(g)
    if g.geom_type == "GeometryCollection":
        partes = [x for x in g.geoms if x.geom_type in ("Polygon", "MultiPolygon")]
        g = shapely.union_all(partes) if partes else g
    return g


def calcular_adjacencia(geoms, tol=TOLERANCIA, comp_min=COMPRIMENTO_MIN):
    """geoms: lista de geometrias. Devolve lista de pares (i, j) vizinhos."""
    geoms = [corrigir(g) for g in geoms]
    buffers = [g.buffer(tol, quad_segs=2) for g in geoms]
    arvore = STRtree(buffers)
    idx_a, idx_b = arvore.query(buffers, predicate="intersects")
    pares = []
    for i, j in zip(idx_a, idx_b):
        if i >= j:
            continue
        try:
            trecho = geoms[i].boundary.intersection(buffers[j])
        except Exception:
            continue
        if trecho.length >= comp_min:
            pares.append((int(i), int(j)))
    return pares


def componentes(n, pares):
    pai = list(range(n))

    def achar(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for a, b in pares:
        pai[achar(a)] = achar(b)
    grupos = {}
    for i in range(n):
        grupos.setdefault(achar(i), []).append(i)
    return sorted(grupos.values(), key=len, reverse=True)


def main():
    with gzip.open(ENTRADA_GEO, "rt", encoding="utf-8") as arq:
        dados = json.load(arq)
    feats = dados["features"]
    codigos = [f["properties"]["codigo"] for f in feats]
    nomes = [f'{f["properties"]["nome"]}/{f["properties"]["uf"]}' for f in feats]
    geoms = [shape(f["geometry"]) for f in feats]
    print(f"{len(geoms)} municipios carregados. Calculando fronteiras...")

    pares = calcular_adjacencia(geoms)
    vizinhos = {c: [] for c in codigos}
    for i, j in pares:
        vizinhos[codigos[i]].append(codigos[j])
        vizinhos[codigos[j]].append(codigos[i])
    for c in vizinhos:
        vizinhos[c].sort()

    with open(SAIDA, "w", encoding="utf-8") as arq:
        json.dump(vizinhos, arq, separators=(",", ":"))

    qtd = [len(v) for v in vizinhos.values()]
    print(f"Pares de vizinhos: {len(pares)}")
    print(f"Vizinhos por municipio: media {sum(qtd) / len(qtd):.1f}, "
          f"minimo {min(qtd)}, maximo {max(qtd)}")

    grupos = componentes(len(geoms), pares)
    print(f"Blocos de municipios conectados: {len(grupos)}")
    print(f"  maior bloco: {len(grupos[0])} municipios")
    for g in grupos[1:6]:
        print(f"  bloco menor ({len(g)}): " + ", ".join(nomes[i] for i in g[:4]))

    # Onde ficam os clubes?
    bloco_de = {}
    for k, g in enumerate(grupos):
        for i in g:
            bloco_de[codigos[i]] = k
    indice = {}
    for c, n in zip(codigos, nomes):
        nome, uf = n.rsplit("/", 1)
        indice[(normalizar(nome), uf)] = c
    fora = []
    with open(ENTRADA_CLUBES, encoding="utf-8") as arq:
        for linha in csv.DictReader(arq):
            c = indice.get((normalizar(linha["cidade"]), linha["uf"]))
            if c is not None and bloco_de[c] != 0:
                fora.append(f'{linha["clube"]} ({linha["cidade"]}/{linha["uf"]})')
    print("--- CLUBES FORA DO MAIOR BLOCO ---")
    if fora:
        for item in fora:
            print("  ", item)
    else:
        print("Todos os clubes estao no mesmo bloco conectado.")


if __name__ == "__main__":
    main()
