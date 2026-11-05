"""Baixa os escudos dos clubes e gera um painel de conferencia (VERSAO 2).

Fontes, nesta ordem:
  1) TheSportsDB (escudos PNG com transparencia, so clubes do Brasil)
  2) Wikipedia (pt), apenas quando a fonte 1 nao achou

Uso:
  python src/escudos.py             -> baixa so o que ainda falta
  python src/escudos.py --refazer   -> refaz tudo (menos o que voce colocou a mao)

Saidas:
  escudos/<slug>.png          um por clube (PNG, no maximo 512 px)
  escudos/_contato.png        painel com todos os escudos para voce conferir
  data/escudos_relatorio.json relatorio (status, origem, motivo)

Arquivos que VOCE colocar a mao em escudos/<slug>.png nunca sao sobrescritos
(o programa reconhece pelo conteudo, mesmo que o nome seja igual ao de um baixado).
Apelidos alternativos de busca: data/escudos_apelidos.csv (colunas: clube,apelidos
separados por |). Pagina fixa da Wikipedia: data/escudos_titulos.csv (clube,titulo).
"""
import csv
import hashlib
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

UA = "GuerraDosClubes/1.0 (projeto pessoal de video; python-urllib)"
PASTA = "escudos"
CLUBES = os.path.join("data", "clubes.csv")
APELIDOS = os.path.join("data", "escudos_apelidos.csv")
TITULOS = os.path.join("data", "escudos_titulos.csv")
RELATORIO = os.path.join("data", "escudos_relatorio.json")
TAMANHO_MAX = 512
CHAVE_SDB = os.environ.get("THESPORTSDB_KEY", "3")
PAUSA_SDB = 2.3   # a chave gratuita aceita ~30 pedidos por minuto
WIKI_API = "https://pt.wikipedia.org/w/api.php"

# imagens que NAO sao escudos de clube (icones da Wikipedia, bandeiras, brasoes de cidade...)
PROIBIDO = re.compile(
    r"commons|wikimedia|wikipedia|wikiquote|wikidata|wikt|wikibooks|wikinews|wikisource|"
    r"projet|bandeira|flag|mapa|\bmap\b|est[aá]dio|stadium|camisa|camiseta|uniforme|\bkit\b|"
    r"torcida|jogador|player|trof[eé]u|soccerball|brasao de|bras[aã]o de|campeonato|s[eé]rie [abcd]|"
    r"copa|cup|league|liga|\.jpe?g|\.gif|\.webm|\.ogv|\.tif|rua |avenida|centro", re.I)
BOM = re.compile(r"escudo|logo|bras[aã]o|emblema|crest|badge|s[ií]mbolo|shield", re.I)
PAGINA_DE_CLUBE = re.compile(r"clube|equipe|time de futebol|associa[cç][aã]o|sociedade|agremia", re.I)
PAGINA_DE_CIDADE = re.compile(r"munic[ií]pio|cidade|capital d|localizad[ao] n[oa]|bairro", re.I)
PALAVRAS_FRACAS = {"de", "da", "do", "dos", "das", "futebol", "clube", "club", "football", "foot", "ball",
                   "esporte", "esportes", "sport", "associacao", "sociedade", "fc", "ec", "sc", "ac",
                   "e", "a", "o", "atletico", "athletic", "regatas", "desportos", "esportiva"}


def sem_acento(t):
    s = unicodedata.normalize("NFD", t)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normalizar(t):
    return re.sub(r"[^a-z0-9]", "", sem_acento(t).lower())


def slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(nome).lower()).strip("-")


def tokens(t):
    return [x for x in re.split(r"[^a-z0-9]+", sem_acento(t).lower()) if x]


def tokens_fortes(t):
    return [x for x in tokens(t) if x not in PALAVRAS_FRACAS and len(x) > 1]


def sha1(caminho):
    with open(caminho, "rb") as arq:
        return hashlib.sha1(arq.read()).hexdigest()


def _pedir(url, tentativas=3, espera_429=65):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as erro:
            print(f"   tentativa {i + 1}: HTTP {erro.code}")
            time.sleep(espera_429 if erro.code == 429 else 3 * (i + 1))
        except Exception as erro:
            print(f"   tentativa {i + 1} falhou: {erro}")
            time.sleep(3 * (i + 1))
    return None


def json_de(url, pausa):
    dados = _pedir(url)
    time.sleep(pausa)
    if not dados:
        return None
    try:
        return json.loads(dados.decode("utf-8"))
    except Exception:
        return None


def baixar_bytes(url):
    return _pedir(url)


# ---------------- fonte 1: TheSportsDB ----------------

def consultas_sdb(clube, apelidos):
    q = []
    q += apelidos
    base = clube
    m = re.match(r"^(.*)-([A-Z]{2})$", clube)
    if m:
        q += [f"{m.group(1)} {m.group(2)}", m.group(1)]
    q.append(base.replace("-", " "))
    vistos, saida = set(), []
    for x in q:
        k = normalizar(x)
        if k and k not in vistos:
            vistos.add(k)
            saida.append(sem_acento(x))
    return saida[:4]


def pontuar_time_sdb(t, consulta, cidade):
    if (t.get("strCountry") or "").strip().lower() != "brazil":
        return -1
    if (t.get("strSport") or "Soccer").lower() != "soccer":
        return -1
    nomes = [t.get("strTeam") or "", t.get("strTeamShort") or ""]
    nomes += [x for x in (t.get("strAlternate") or "").split(",") if x.strip()]
    qn = normalizar(consulta)
    qt = set(tokens_fortes(consulta)) or set(tokens(consulta))
    melhor = 0
    for n in nomes:
        nn = normalizar(n)
        if nn and nn == qn:
            melhor = max(melhor, 5)
        else:
            nt = set(tokens_fortes(n)) or set(tokens(n))
            if qt and nt and (qt <= nt or nt <= qt):
                melhor = max(melhor, 4)
            elif qt & nt:
                melhor = max(melhor, 2)
    if melhor == 0:
        return -1
    local = normalizar((t.get("strStadiumLocation") or "") + (t.get("strLocation") or ""))
    if normalizar(cidade) and normalizar(cidade) in local:
        melhor += 3
    return melhor + 3  # +3 por ser do Brasil


def buscar_sdb(clube, cidade, apelidos):
    melhor = (0, None, None)
    for q in consultas_sdb(clube, apelidos):
        url = (f"https://www.thesportsdb.com/api/v1/json/{CHAVE_SDB}/searchteams.php?t="
               + urllib.parse.quote(q))
        r = json_de(url, PAUSA_SDB)
        for t in (r or {}).get("teams") or []:
            nota = pontuar_time_sdb(t, q, cidade)
            badge = t.get("strTeamBadge") or t.get("strBadge")
            if nota > melhor[0] and badge:
                melhor = (nota, t, q)
        if melhor[0] >= 11:
            break
    nota, t, q = melhor
    if not t:
        return None
    badge = t.get("strTeamBadge") or t.get("strBadge")
    status = "ok" if nota >= 11 else "duvida"
    return {"status": status, "origem": "thesportsdb", "time": t.get("strTeam"),
            "consulta": q, "nota": nota, "url": badge}


# ---------------- fonte 2: Wikipedia ----------------

def wiki(**params):
    params.update({"format": "json", "formatversion": "2"})
    return json_de(WIKI_API + "?" + urllib.parse.urlencode(params), 0.3)


def pagina_parece_do_clube(clube, titulo, extrato):
    forte = set(tokens_fortes(clube))
    if forte and not (forte & set(tokens(titulo))):
        return False
    inicio = extrato[:350]
    if PAGINA_DE_CIDADE.search(inicio) and not PAGINA_DE_CLUBE.search(inicio):
        return False
    return bool(PAGINA_DE_CLUBE.search(inicio))


def buscar_wikipedia(clube, cidade, titulo_forcado=None):
    titulos = [titulo_forcado] if titulo_forcado else []
    if not titulos:
        r = wiki(action="query", list="search", srlimit=4,
                 srsearch=f"{clube.replace('-', ' ')} {cidade} clube de futebol")
        titulos = [x["title"] for x in (r or {}).get("query", {}).get("search", [])]
    for t in titulos:
        e = wiki(action="query", prop="extracts", exintro=1, explaintext=1, exchars=600,
                 redirects=1, titles=t)
        pg = ((e or {}).get("query", {}).get("pages") or [{}])[0]
        if not titulo_forcado and not pagina_parece_do_clube(clube, pg.get("title", t),
                                                              pg.get("extract", "")):
            continue
        titulo = pg.get("title", t)
        # 1) imagem principal da pagina (a da caixa de informacoes)
        p = wiki(action="query", prop="pageimages", piprop="thumbnail|name",
                 pithumbsize=TAMANHO_MAX, redirects=1, titles=titulo)
        pp = ((p or {}).get("query", {}).get("pages") or [{}])[0]
        nome = pp.get("pageimage") or ""
        thumb = (pp.get("thumbnail") or {}).get("source")
        if thumb and nome and not PROIBIDO.search(nome):
            forte = set(tokens_fortes(clube)) & set(tokens(nome))
            status = "ok" if (forte and BOM.search(nome)) else "duvida"
            return {"status": status, "origem": "wikipedia", "pagina": titulo,
                    "arquivo_wiki": nome, "url": thumb}
        # 2) lista completa de imagens da pagina, filtrando as que nao sao escudo
        imagens, cont = [], {}
        for _ in range(4):
            q = wiki(action="query", prop="images", imlimit=500, redirects=1, titles=titulo, **cont)
            pg2 = ((q or {}).get("query", {}).get("pages") or [{}])[0]
            imagens += [i["title"] for i in pg2.get("images", [])]
            cont = (q or {}).get("continue") or {}
            if not cont:
                break
        candidatas = []
        for im in imagens:
            if PROIBIDO.search(im):
                continue
            nota = (3 if BOM.search(im) else 0) + 3 * len(set(tokens_fortes(clube)) & set(tokens(im)))
            if im.lower().endswith(".svg"):
                nota += 1
            if nota >= 4:
                candidatas.append((nota, im))
        if candidatas:
            candidatas.sort(reverse=True)
            arq = candidatas[0][1]
            info = wiki(action="query", prop="imageinfo", iiprop="url", iiurlwidth=TAMANHO_MAX, titles=arq)
            ii = (((info or {}).get("query", {}).get("pages") or [{}])[0].get("imageinfo") or [{}])[0]
            url = ii.get("thumburl") or ii.get("url")
            if url:
                return {"status": "duvida", "origem": "wikipedia", "pagina": titulo,
                        "arquivo_wiki": arq, "url": url}
    return None


# ---------------- arquivos ----------------

def salvar_png(dados, caminho):
    img = Image.open(io.BytesIO(dados)).convert("RGBA")
    img.thumbnail((TAMANHO_MAX, TAMANHO_MAX))
    img.save(caminho, "PNG")


def painel_contato(clubes, relatorio, saida, colunas=10):
    cel_w, cel_h = 190, 220
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
        info = relatorio[c["clube"]]
        st = info["status"]
        d.rectangle([x + 4, y + 4, x + cel_w - 5, y + cel_h - 5], outline=cores.get(st), width=3)
        arq = os.path.join(PASTA, slug(c["clube"]) + ".png")
        if os.path.exists(arq):
            try:
                e = Image.open(arq).convert("RGBA")
                e.thumbnail((140, 140))
                img.paste(e, (x + (cel_w - e.size[0]) // 2, y + 14 + (140 - e.size[1]) // 2), e)
            except Exception:
                pass
        nome = c["clube"] if len(c["clube"]) < 22 else c["clube"][:21] + "."
        d.text((x + cel_w / 2, y + 178), nome, font=fonte, fill=(255, 255, 255), anchor="mm")
        rot = st.upper() + ("" if not info.get("origem") else " · " + info["origem"][:5])
        d.text((x + cel_w / 2, y + 198), rot, font=fonte, fill=cores.get(st), anchor="mm")
    img.save(saida)


def carregar_csv(caminho, c1, c2):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8") as arq:
        return {l[c1]: l[c2] for l in csv.DictReader(arq)}


def main():
    refazer = "--refazer" in sys.argv
    os.makedirs(PASTA, exist_ok=True)
    with open(CLUBES, encoding="utf-8") as arq:
        clubes = list(csv.DictReader(arq))
    apelidos = {k: [x for x in v.split("|") if x] for k, v in carregar_csv(APELIDOS, "clube", "apelidos").items()}
    forcados = carregar_csv(TITULOS, "clube", "titulo")
    antigo = {}
    if os.path.exists(RELATORIO):
        try:
            with open(RELATORIO, encoding="utf-8") as arq:
                antigo = json.load(arq)
        except Exception:
            antigo = {}

    relatorio = {}
    for k, c in enumerate(clubes, start=1):
        nome = c["clube"]
        caminho = os.path.join(PASTA, slug(nome) + ".png")
        ant = antigo.get(nome)
        if os.path.exists(caminho):
            if ant is None or "arquivo" not in ant:
                relatorio[nome] = {"status": "manual", "origem": "manual", "arquivo": caminho}
                continue
            if "sha1" in ant and sha1(caminho) != ant["sha1"]:   # voce trocou o arquivo
                relatorio[nome] = {"status": "manual", "origem": "manual", "arquivo": caminho}
                continue
            if not refazer and ant.get("versao") == 2 and ant.get("status") == "ok":
                relatorio[nome] = ant
                continue
        print(f"[{k}/{len(clubes)}] {nome} ({c['cidade']}/{c['uf']})", flush=True)
        achado = buscar_sdb(nome, c["cidade"], apelidos.get(nome, []))
        if (not achado or achado["status"] != "ok"):
            wk = buscar_wikipedia(nome, c["cidade"], forcados.get(nome))
            if wk and (not achado or wk["status"] == "ok"):
                achado = wk
        if not achado:
            relatorio[nome] = {"status": "faltando", "motivo": "nao encontrado em nenhuma fonte",
                               "versao": 2}
            if os.path.exists(caminho):
                os.remove(caminho)
            print("   -> faltando")
            continue
        dados = baixar_bytes(achado["url"])
        try:
            salvar_png(dados, caminho)
        except Exception as erro:
            relatorio[nome] = {"status": "faltando", "motivo": f"download/imagem invalida: {erro}",
                               "versao": 2}
            print("   -> faltando (download)")
            continue
        achado.pop("url", None)
        achado.update({"arquivo": caminho, "sha1": sha1(caminho), "versao": 2})
        relatorio[nome] = achado
        print(f"   -> {achado['status']} [{achado['origem']}] "
              f"{achado.get('time') or achado.get('pagina', '')}", flush=True)

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
