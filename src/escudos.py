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
                # fundo metade claro, metade escuro: escudos escuros ou brancos aparecem de qualquer jeito
                bx, by = x + (cel_w - 150) // 2, y + 10
                d.rectangle([bx, by, bx + 74, by + 149], fill=(226, 229, 237))
                d.rectangle([bx + 75, by, bx + 149, by + 149], fill=(36, 41, 66))
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
    manuais = ler_manuais()
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
        fonte = manuais.get(nome)
        if fonte:
            if ant and ant.get("fonte") == fonte and os.path.exists(caminho) and not refazer:
                # link ja aplicado antes: mantem (e respeita arquivo trocado por voce depois)
                if sha1(caminho) == ant.get("sha1"):
                    relatorio[nome] = ant
                else:
                    relatorio[nome] = {"status": "manual", "origem": "manual-arquivo", "fonte": fonte,
                                       "arquivo": caminho, "sha1": sha1(caminho), "versao": 2}
                continue
            print(f"[{k}/{len(clubes)}] {nome}: link manual", flush=True)
            try:
                url = resolver_fonte(nome, c["cidade"], fonte)
                dados = baixar_bytes(url)
                if not dados:
                    raise ValueError("o link nao pode ser baixado (confira se abre no navegador)")
                salvar_png(dados, caminho)
                relatorio[nome] = {"status": "manual", "origem": "manual-link", "fonte": fonte,
                                   "arquivo": caminho, "sha1": sha1(caminho), "versao": 2}
                print("   -> manual (ok)", flush=True)
            except Exception as erro:
                relatorio[nome] = {"status": "faltando", "fonte": fonte, "versao": 2,
                                   "motivo": f"link manual falhou: {erro}"}
                print(f"   -> LINK MANUAL FALHOU: {erro}", flush=True)
            continue
        if os.path.exists(caminho):
            if ant is None or "arquivo" not in ant:
                relatorio[nome] = {"status": "manual", "origem": "manual", "arquivo": caminho}
                continue
            if "sha1" in ant and sha1(caminho) != ant["sha1"]:   # voce trocou o arquivo
                relatorio[nome] = {"status": "manual", "origem": "manual", "arquivo": caminho}
                continue
            if not refazer and ant.get("versao") == 2 and ant.get("status") in ("ok", "manual"):
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
