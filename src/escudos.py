"""Baixa os escudos dos clubes pela Wikipedia (pt) e gera um painel de conferencia.

Uso:
  python src/escudos.py             -> baixa so os que ainda nao existem
  python src/escudos.py --refazer   -> baixa todos de novo

Saidas:
  escudos/<slug>.png          (um por clube, PNG com transparencia, no maximo 512 px)
  escudos/_contato.png        (painel com todos os escudos para voce conferir)
  data/escudos_relatorio.json (o que foi achado, duvidoso ou faltou)

Escudos que voce colocar a mao em escudos/<slug>.png sao respeitados e nao sao
sobrescritos. Para forcar uma pagina especifica da Wikipedia, crie o arquivo
data/escudos_titulos.csv com as colunas: clube,titulo
"""
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

API = "https://pt.wikipedia.org/w/api.php"
UA = "GuerraDosClubes/1.0 (projeto pessoal de video; python-urllib)"
PASTA = "escudos"
CLUBES = os.path.join("data", "clubes.csv")
TITULOS = os.path.join("data", "escudos_titulos.csv")
RELATORIO = os.path.join("data", "escudos_relatorio.json")
TAMANHO_MAX = 512

BOM = re.compile(r"escudo|logo|bras[aã]o|emblema|crest|badge|s[ií]mbolo|shield", re.I)
RUIM = re.compile(r"bandeira|flag|mapa|map\b|est[aá]dio|stadium|camisa|camiseta|uniforme|kit\b|"
                  r"torcida|jogador|player|trof[eé]u|foto|\.jpe?g|\.gif|\.webm|\.ogv", re.I)


def slug(nome):
    s = unicodedata.normalize("NFD", nome)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def normalizar(texto):
    s = unicodedata.normalize("NFD", texto)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _pedir(url, tentativas=3):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as erro:
            print(f"   tentativa {i + 1} falhou: {erro}")
            time.sleep(2 * (i + 1))
    return None


def api(**params):
    params.update({"format": "json", "formatversion": "2"})
    dados = _pedir(API + "?" + urllib.parse.urlencode(params))
    time.sleep(0.15)
    return json.loads(dados.decode("utf-8")) if dados else {}


def baixar_bytes(url):
    return _pedir(url)


def nota_arquivo(titulo):
    """Quanto o nome do arquivo parece ser um escudo (maior = melhor)."""
    t = titulo.lower()
    if RUIM.search(t):
        return -1
    nota = 0
    if BOM.search(t):
        nota += 3
    if t.endswith(".svg"):
        nota += 2
    elif t.endswith(".png"):
        nota += 1
    return nota


def escolher_pagina(clube, cidade, titulo_forcado=None):
    """Devolve (titulo, confiavel)."""
    if titulo_forcado:
        return titulo_forcado, True
    consulta = f"{clube.replace('-', ' ')} {cidade} clube de futebol"
    r = api(action="query", list="search", srsearch=consulta, srlimit=4)
    achados = [x["title"] for x in r.get("query", {}).get("search", [])]
    melhor, melhor_nota = None, -1
    for t in achados:
        e = api(action="query", prop="extracts", exintro=1, explaintext=1,
                exchars=1500, titles=t)
        paginas = e.get("query", {}).get("pages", [])
        texto = (paginas[0].get("extract", "") if paginas else "")
        nota = 0
        if normalizar(cidade) in normalizar(texto):
            nota += 2
        if re.search(r"futebol|clube|esporte", texto, re.I):
            nota += 1
        if nota > melhor_nota:
            melhor, melhor_nota = t, nota
    return melhor, melhor_nota >= 3


def achar_arquivo(titulo_pagina):
    r = api(action="query", prop="images", imlimit=60, titles=titulo_pagina)
    paginas = r.get("query", {}).get("pages", [])
    imagens = [i["title"] for i in (paginas[0].get("images", []) if paginas else [])]
    ranque = sorted(((nota_arquivo(t), t) for t in imagens), reverse=True)
    if ranque and ranque[0][0] >= 3:
        return ranque[0][1], True
    # plano B: imagem principal da pagina
    r = api(action="query", prop="pageimages", piprop="name", titles=titulo_pagina)
    paginas = r.get("query", {}).get("pages", [])
    nome = paginas[0].get("pageimage") if paginas else None
    if nome:
        return "Ficheiro:" + nome, nota_arquivo(nome) >= 3
    if ranque and ranque[0][0] >= 0:
        return ranque[0][1], False
    return None, False


def url_da_imagem(arquivo):
    r = api(action="query", prop="imageinfo", iiprop="url|size|mime",
            iiurlwidth=TAMANHO_MAX, titles=arquivo)
    paginas = r.get("query", {}).get("pages", [])
    info = (paginas[0].get("imageinfo") or [None])[0] if paginas else None
    if not info:
        return None
    return info.get("thumburl") or info.get("url")


def salvar_png(dados, caminho):
    img = Image.open(io.BytesIO(dados)).convert("RGBA")
    img.thumbnail((TAMANHO_MAX, TAMANHO_MAX))
    img.save(caminho, "PNG")
    return img.size


def baixar_escudo(clube, cidade, titulo_forcado=None):
    titulo, pagina_ok = escolher_pagina(clube, cidade, titulo_forcado)
    if not titulo:
        return {"status": "faltando", "motivo": "pagina nao encontrada"}, None
    arquivo, arquivo_ok = achar_arquivo(titulo)
    if not arquivo:
        return {"status": "faltando", "pagina": titulo, "motivo": "sem imagem de escudo"}, None
    url = url_da_imagem(arquivo)
    if not url:
        return {"status": "faltando", "pagina": titulo, "arquivo_wiki": arquivo,
                "motivo": "sem url da imagem"}, None
    dados = baixar_bytes(url)
    if not dados:
        return {"status": "faltando", "pagina": titulo, "arquivo_wiki": arquivo,
                "motivo": "falha no download"}, None
    status = "ok" if (pagina_ok and arquivo_ok) else "duvida"
    return {"status": status, "pagina": titulo, "arquivo_wiki": arquivo}, dados


def painel_contato(clubes, relatorio, saida, colunas=10):
    cel_w, cel_h = 190, 210
    linhas = (len(clubes) + colunas - 1) // colunas
    img = Image.new("RGB", (colunas * cel_w, linhas * cel_h), (18, 22, 40))
    d = ImageDraw.Draw(img)
    try:
        fonte = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except Exception:
        fonte = ImageFont.load_default()
    cores = {"ok": (60, 200, 120), "manual": (80, 160, 255), "duvida": (245, 190, 60),
             "faltando": (230, 70, 70)}
    for k, c in enumerate(clubes):
        x, y = (k % colunas) * cel_w, (k // colunas) * cel_h
        st = relatorio[c["clube"]]["status"]
        d.rectangle([x + 4, y + 4, x + cel_w - 5, y + cel_h - 5], outline=cores.get(st), width=3)
        arq = os.path.join(PASTA, slug(c["clube"]) + ".png")
        if os.path.exists(arq):
            e = Image.open(arq).convert("RGBA")
            e.thumbnail((140, 140))
            img.paste(e, (x + (cel_w - e.size[0]) // 2, y + 14 + (140 - e.size[1]) // 2), e)
        nome = c["clube"] if len(c["clube"]) < 22 else c["clube"][:21] + "."
        d.text((x + cel_w / 2, y + 178), nome, font=fonte, fill=(255, 255, 255), anchor="mm")
        d.text((x + cel_w / 2, y + 196), st.upper(), font=fonte, fill=cores.get(st), anchor="mm")
    img.save(saida)


def main():
    refazer = "--refazer" in sys.argv
    os.makedirs(PASTA, exist_ok=True)
    with open(CLUBES, encoding="utf-8") as arq:
        clubes = list(csv.DictReader(arq))
    forcados = {}
    if os.path.exists(TITULOS):
        with open(TITULOS, encoding="utf-8") as arq:
            forcados = {l["clube"]: l["titulo"] for l in csv.DictReader(arq)}

    relatorio = {}
    for k, c in enumerate(clubes, start=1):
        nome = c["clube"]
        caminho = os.path.join(PASTA, slug(nome) + ".png")
        if os.path.exists(caminho) and not refazer:
            relatorio[nome] = {"status": "manual", "arquivo": caminho}
            continue
        print(f"[{k}/{len(clubes)}] {nome} ({c['cidade']}/{c['uf']})", flush=True)
        info, dados = baixar_escudo(nome, c["cidade"], forcados.get(nome))
        if dados:
            try:
                salvar_png(dados, caminho)
                info["arquivo"] = caminho
            except Exception as erro:
                info = {"status": "faltando", "motivo": f"imagem invalida: {erro}"}
        relatorio[nome] = info
        print(f"   -> {info['status']}  {info.get('pagina', '')}  {info.get('arquivo_wiki', '')}")

    with open(RELATORIO, "w", encoding="utf-8") as arq:
        json.dump(relatorio, arq, ensure_ascii=False, indent=1)
    painel_contato(clubes, relatorio, os.path.join(PASTA, "_contato.png"))

    cont = {}
    for v in relatorio.values():
        cont[v["status"]] = cont.get(v["status"], 0) + 1
    print("--- RESUMO ---")
    for st in ("ok", "manual", "duvida", "faltando"):
        print(f"  {st}: {cont.get(st, 0)}")
    for st, rotulo in (("faltando", "FALTANDO"), ("duvida", "CONFERIR")):
        lista = [n for n, v in relatorio.items() if v["status"] == st]
        if lista:
            print(f"{rotulo}: " + ", ".join(lista))
    print("Painel de conferencia: escudos/_contato.png")


if __name__ == "__main__":
    main()
