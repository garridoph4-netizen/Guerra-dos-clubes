"""Simula a guerra inteira e grava o roteiro (data/roteiro.json).

Regras:
- Sorteia um clube atacante entre os vivos e um defensor entre os clubes
  que fazem fronteira com ele naquele momento.
- Disputa de penaltis: 5 cobrancas alternadas (atacante comeca); a disputa
  acaba antes se um lado ja nao pode ser alcancado. Se empatar, vai para
  cobrancas alternadas (morte subita).
- O vencedor elimina o perdedor e fica com TODAS as unidades dele.
- Repete ate sobrar um unico clube.

Tudo e sorteado com uma "semente": mesma semente = mesma guerra.
Para mudar a guerra, troque o numero SEMENTE abaixo.
"""
import json
import os
import random

SEMENTE = 2026
CHANCE_DE_GOL = 0.75   # igual para todos os clubes

ENTRADA = os.path.join("data", "territorios.json")
SAIDA = os.path.join("data", "roteiro.json")


def disputa_penaltis(rng):
    """Devolve (chutes, gols_atacante, gols_defensor).

    chutes: lista de [lado, gol] com lado 0 = atacante, 1 = defensor.
    """
    chutes = []
    gols = [0, 0]
    feitos = [0, 0]
    # fase regular: 5 cobrancas para cada lado, alternadas
    for _ in range(5):
        for lado in (0, 1):
            gol = 1 if rng.random() < CHANCE_DE_GOL else 0
            chutes.append([lado, gol])
            gols[lado] += gol
            feitos[lado] += 1
            resta = [5 - feitos[0], 5 - feitos[1]]
            if gols[0] > gols[1] + resta[1] or gols[1] > gols[0] + resta[0]:
                return chutes, gols[0], gols[1]
    # morte subita: ambos cobram; decide quando a rodada termina desigual
    while gols[0] == gols[1]:
        rodada = []
        for lado in (0, 1):
            gol = 1 if rng.random() < CHANCE_DE_GOL else 0
            chutes.append([lado, gol])
            rodada.append(gol)
        gols[0] += rodada[0]
        gols[1] += rodada[1]
    return chutes, gols[0], gols[1]


def vizinhos_atuais(clube, donos, vizinhos_unidade, unidades_do_clube):
    """Recalcula (do zero) quais clubes fazem fronteira com 'clube'."""
    resultado = set()
    for u in unidades_do_clube[clube]:
        for v in vizinhos_unidade[u]:
            if donos[v] != clube:
                resultado.add(donos[v])
    return resultado


def simular(clubes, donos, vizinhos_unidade, semente=SEMENTE):
    rng = random.Random(semente)
    donos = list(donos)
    n_clubes = len(clubes)
    unidades_do_clube = {c: [] for c in range(n_clubes)}
    for u, d in enumerate(donos):
        unidades_do_clube[d].append(u)

    # vizinhanca entre clubes (mantida incrementalmente)
    vizinhos = {c: set() for c in range(n_clubes)}
    for c in range(n_clubes):
        vizinhos[c] = vizinhos_atuais(c, donos, vizinhos_unidade, unidades_do_clube)

    vivos = set(range(n_clubes))
    partidas = []
    while len(vivos) > 1:
        atacante = rng.choice(sorted(vivos))
        defensor = rng.choice(sorted(vizinhos[atacante]))
        # conferencia de seguranca: a fronteira existe de verdade agora?
        assert defensor in vizinhos_atuais(atacante, donos, vizinhos_unidade,
                                           unidades_do_clube), "fronteira inconsistente"

        chutes, ga, gd = disputa_penaltis(rng)
        vencedor, perdedor = (atacante, defensor) if ga > gd else (defensor, atacante)

        conquistadas = list(unidades_do_clube[perdedor])
        for u in conquistadas:
            donos[u] = vencedor
        unidades_do_clube[vencedor].extend(conquistadas)
        unidades_do_clube[perdedor] = []

        vizinhos[vencedor] = (vizinhos[vencedor] | vizinhos[perdedor]) - {vencedor, perdedor}
        for x in vizinhos[perdedor]:
            vizinhos[x].discard(perdedor)
            if x != vencedor:
                vizinhos[x].add(vencedor)
        vizinhos[perdedor] = set()
        vivos.discard(perdedor)

        partidas.append({
            "n": len(partidas) + 1,
            "atacante": atacante, "defensor": defensor,
            "chutes": chutes, "placar": [ga, gd],
            "vencedor": vencedor, "perdedor": perdedor,
            "conquistadas": conquistadas,
            "restantes": len(vivos),
        })
    campeao = next(iter(vivos))
    return partidas, campeao, donos


def main():
    with open(ENTRADA, encoding="utf-8") as arq:
        t = json.load(arq)
    clubes = t["clubes"]
    posicao = {u["id"]: i for i, u in enumerate(t["unidades"])}
    donos = [u["dono"] for u in t["unidades"]]
    vizinhos_unidade = [[posicao[v] for v in u["vizinhos"]] for u in t["unidades"]]

    partidas, campeao, donos_finais = simular(clubes, donos, vizinhos_unidade)

    assert len(partidas) == len(clubes) - 1, "numero de partidas inesperado"
    assert all(d == campeao for d in donos_finais), "campeao nao dominou tudo"

    roteiro = {"semente": SEMENTE, "chance_de_gol": CHANCE_DE_GOL,
               "campeao": campeao, "partidas": partidas}
    with open(SAIDA, "w", encoding="utf-8") as arq:
        json.dump(roteiro, arq, separators=(",", ":"))

    nome = lambda i: clubes[i]["nome"]
    print(f"Semente {SEMENTE}: {len(partidas)} partidas. CAMPEAO: {nome(campeao)} "
          f"({clubes[campeao]['serie']})")
    ult = partidas[-1]
    print(f"Final: {nome(ult['atacante'])} {ult['placar'][0]} x {ult['placar'][1]} "
          f"{nome(ult['defensor'])}")
    vitorias = {}
    for p in partidas:
        vitorias[p["vencedor"]] = vitorias.get(p["vencedor"], 0) + 1
    top = sorted(vitorias.items(), key=lambda x: -x[1])[:5]
    print("Mais vitorias: " + ", ".join(f"{nome(c)} ({v})" for c, v in top))
    por_serie = {}
    for p in partidas:
        s = clubes[p["perdedor"]]["serie"]
        por_serie[s] = por_serie.get(s, 0) + 1
    print("Eliminados por serie: " + ", ".join(f"{s}: {por_serie.get(s, 0)}" for s in "ABCD"))
    chutes = [len(p["chutes"]) for p in partidas]
    longa = max(partidas, key=lambda p: len(p["chutes"]))
    print(f"Cobrancas por disputa: media {sum(chutes) / len(chutes):.1f}, "
          f"maxima {len(longa['chutes'])} (partida {longa['n']})")
    print("Primeiras partidas:")
    for p in partidas[:4]:
        print(f"  #{p['n']}: {nome(p['atacante'])} {p['placar'][0]} x {p['placar'][1]} "
              f"{nome(p['defensor'])} -> vence {nome(p['vencedor'])}")
    print(f"Arquivo {SAIDA}: {os.path.getsize(SAIDA) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
