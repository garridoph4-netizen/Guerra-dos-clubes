"""Baixa os limites oficiais dos municipios (IBGE) e confere as cidades dos clubes.

Gera:
  data/municipios.geojson.gz  (todos os municipios, coordenadas com 5 casas)
  data/municipios.csv         (codigo, nome, uf)
E imprime um relatorio dizendo se alguma cidade de data/clubes.csv nao foi achada.
"""
import csv
import gzip
import json
import os
import re
import time
import unicodedata
import urllib.request

URL_NOMES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{cod}"
             "?intrarregiao=municipio&qualidade=intermediaria"
             "&formato=application/vnd.geo+json")

UFS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

SAIDA_GEO = os.path.join("data", "municipios.geojson.gz")
SAIDA_CSV = os.path.join("data", "municipios.csv")
ENTRADA_CLUBES = os.path.join("data", "clubes.csv")


def baixar(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "guerra-dos-clubes"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as erro:
            print(f"  tentativa {i + 1} falhou: {erro}")
            time.sleep(5 * (i + 1))
    raise SystemExit(f"Nao consegui baixar: {url}")


def arredondar(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 5), round(coords[1], 5)]
    return [arredondar(c) for c in coords]


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def main():
    os.makedirs("data", exist_ok=True)

    print("Baixando nomes dos municipios...")
    nomes = {str(m["id"]): m["nome"] for m in baixar(URL_NOMES)}
    print(f"  {len(nomes)} nomes recebidos")

    features = []
    for cod, uf in UFS.items():
        print(f"Baixando malha de {uf}...")
        dados = baixar(URL_MALHA.format(cod=cod))
        for f in dados["features"]:
            codigo = str(f["properties"]["codarea"])
            geom = f["geometry"]
            features.append({
                "type": "Feature",
                "properties": {"codigo": codigo,
                               "nome": nomes.get(codigo, "?"),
                               "uf": UFS.get(codigo[:2], "?")},
                "geometry": {"type": geom["type"],
                             "coordinates": arredondar(geom["coordinates"])},
            })
        print(f"  {len(dados['features'])} municipios em {uf}")

    print(f"Total de municipios: {len(features)}")

    with gzip.open(SAIDA_GEO, "wt", encoding="utf-8") as arq:
        json.dump({"type": "FeatureCollection", "features": features},
                  arq, ensure_ascii=False, separators=(",", ":"))
    with open(SAIDA_CSV, "w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(["codigo", "nome", "uf"])
        for f in features:
            p = f["properties"]
            w.writerow([p["codigo"], p["nome"], p["uf"]])
    tamanho = os.path.getsize(SAIDA_GEO) / 1_000_000
    print(f"Arquivo {SAIDA_GEO}: {tamanho:.1f} MB")

    # Confere as cidades dos clubes
    indice = {}
    for f in features:
        p = f["properties"]
        indice[(normalizar(p["nome"]), p["uf"])] = p["codigo"]
    faltando = []
    with open(ENTRADA_CLUBES, encoding="utf-8") as arq:
        for linha in csv.DictReader(arq):
            chave = (normalizar(linha["cidade"]), linha["uf"])
            if chave not in indice:
                faltando.append(f'{linha["clube"]} -> {linha["cidade"]}/{linha["uf"]}')
    print("--- CONFERENCIA DAS CIDADES DOS CLUBES ---")
    if faltando:
        print("Cidades NAO encontradas no IBGE:")
        for item in faltando:
            print("  ", item)
    else:
        print("Todas as cidades dos 156 clubes foram encontradas.")

    if len(features) < 5000:
        raise SystemExit("Poucos municipios baixados: algo deu errado.")


if __name__ == "__main__":
    main()
