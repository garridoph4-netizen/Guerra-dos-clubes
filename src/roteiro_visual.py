"""Gera o roteiro VISUAL das cobrancas de penalti (data/roteiro_visual.json).

O roteiro.json so diz se cada cobranca foi gol ou nao. Este programa acrescenta,
de forma deterministica (mesma semente = mesmo resultado), os detalhes que a
animacao precisa: canto e altura do chute, tipo de erro (defesa, para fora ou
trave), lado do mergulho do goleiro, camisa do batedor e estilo de comemoracao.

REGRA DE OURO: gol continua gol, erro continua erro, placar e vencedor nunca mudam.
O programa confere isso no final e para com erro se algo divergir.
"""
import json
import os
import random
from collections import Counter

SEMENTE_VISUAL = 7
ENTRADA = os.path.join("data", "roteiro.json")
SAIDA = os.path.join("data", "roteiro_visual.json")

# ordem dos batedores (numero da camisa), repetida em morte subita
ORDEM_BATEDORES = [9, 10, 7, 11, 8, 5, 4, 3, 2, 6, 20, 17]
COMEMORACOES = ["corrida_e_deslize", "salto_e_soco", "abraco_coletivo", "joelhos_no_chao"]
DERROTAS = ["cabeca_baixa", "maos_no_rosto", "de_joelhos"]


def rng_para(n, i):
    return random.Random(f"{SEMENTE_VISUAL}-{n}-{i}")


def chute_visual(gol, rng):
    """Devolve os detalhes visuais de uma cobranca. 'gol' ja esta decidido."""
    altura = rng.choices([0, 1, 2], [35, 25, 40])[0]   # 0 rasteiro, 1 meio, 2 alto
    efeito = round(rng.uniform(-0.15, 0.15), 3)
    forca = round(rng.uniform(0.8, 1.0), 3)
    if gol:
        canto = rng.choices([-1, 0, 1], [40, 20, 40])[0]   # -1 esquerda, 1 direita
        if canto == 0:
            mergulho = rng.choice([-1, 1])
        else:
            r = rng.random()
            if r < 0.55:
                mergulho = -canto           # goleiro foi para o lado errado
            elif r < 0.80:
                mergulho = canto            # foi certo, mas a bola entrou no angulo
                altura = 2
            else:
                mergulho = 0                # ficou parado
        return {"tipo": "gol", "canto": canto, "altura": altura, "mergulho": mergulho,
                "desvio": None, "efeito": efeito, "forca": forca}
    r = rng.random()
    if r < 0.70:
        canto = rng.choices([-1, 0, 1], [38, 24, 38])[0]
        return {"tipo": "defesa", "canto": canto, "altura": altura, "mergulho": canto,
                "desvio": None, "efeito": efeito, "forca": forca}
    if r < 0.92:
        canto = rng.choice([-1, 1])
        desvio = rng.choice(["lateral", "por_cima"])
        return {"tipo": "fora", "canto": canto, "altura": 2 if desvio == "por_cima" else altura,
                "mergulho": rng.choice([-1, 0, 1]), "desvio": desvio,
                "efeito": efeito, "forca": forca}
    canto = rng.choice([-1, 1])
    return {"tipo": "trave", "canto": canto, "altura": 2, "mergulho": canto,
            "desvio": rng.choice(["poste", "travessao"]), "efeito": efeito, "forca": forca}


def montar(roteiro):
    partidas = []
    for p in roteiro["partidas"]:
        n = p["n"]
        contagem = [0, 0]
        chutes = []
        for i, (lado, gol) in enumerate(p["chutes"]):
            v = chute_visual(bool(gol), rng_para(n, i))
            v.update({"i": i, "lado": lado, "gol": gol,
                      "camisa": ORDEM_BATEDORES[contagem[lado] % len(ORDEM_BATEDORES)]})
            contagem[lado] += 1
            chutes.append(v)
        r = rng_para(n, 999)
        partidas.append({"n": n, "chutes": chutes,
                         "comemoracao": r.choice(COMEMORACOES),
                         "derrota": r.choice(DERROTAS),
                         "camera": r.randrange(3)})
    return partidas


def conferir(roteiro, partidas):
    for p, v in zip(roteiro["partidas"], partidas):
        assert p["n"] == v["n"], "ordem de partidas diferente"
        assert len(p["chutes"]) == len(v["chutes"]), "numero de chutes diferente"
        gols = [0, 0]
        for (lado, gol), c in zip(p["chutes"], v["chutes"]):
            assert c["lado"] == lado and c["gol"] == gol, "resultado de chute alterado"
            assert (c["tipo"] == "gol") == bool(gol), "tipo incompativel com o resultado"
            gols[lado] += gol
        assert gols == p["placar"], "placar nao confere"


def main():
    with open(ENTRADA, encoding="utf-8") as arq:
        roteiro = json.load(arq)
    partidas = montar(roteiro)
    conferir(roteiro, partidas)
    with open(SAIDA, "w", encoding="utf-8") as arq:
        json.dump({"semente_visual": SEMENTE_VISUAL, "partidas": partidas}, arq,
                  ensure_ascii=False, separators=(",", ":"))
    tipos = Counter(c["tipo"] for p in partidas for c in p["chutes"])
    total = sum(tipos.values())
    print(f"{len(partidas)} partidas, {total} cobrancas. Conferencia: placares e vencedores intactos.")
    for t in ("gol", "defesa", "fora", "trave"):
        print(f"  {t}: {tipos[t]} ({100 * tipos[t] / total:.1f}%)")
    print(f"Arquivo {SAIDA} ({os.path.getsize(SAIDA) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
