"""Divide o roteiro da guerra em episodios e calcula a duracao de cada cena.

Le data/roteiro.json (uma unica simulacao continua) e grava data/episodios.json.
Nenhuma partida e cortada no meio: cada episodio e um bloco de partidas seguidas.

RITMO EM NIVEIS: no comeco (muitos clubes) as cobrancas sao rapidas, com cortes;
conforme sobram menos clubes, ficam mais longas e dramaticas ate a final.
Os episodios sao balanceados para terem duracao parecida.
"""
import json
import os

ENTRADA = os.path.join("data", "roteiro.json")
SAIDA = os.path.join("data", "episodios.json")

FPS = 30
NUM_EPISODIOS = 9
ABERTURA_S = 35            # titulo + expansao inicial (so no episodio 1)
RANKING_S = 8              # cartao de ranking no fim de cada episodio
CAMPEAO_S = 15             # cartao do campeao no ultimo episodio

# nivel: restantes_antes >= minimo. Tempos em segundos.
NIVEIS = [
    # nome,       minimo, apresentacao, por_chute, resultado, conquista, max_disputa
    ("rapido",       60,   1.5,          1.1,       1.5,       2.0,      16.0),
    ("medio",        16,   2.0,          2.0,       2.0,       3.0,      26.0),
    ("completo",      6,   3.0,          2.8,       3.0,       4.0,      38.0),
    ("final",         0,   4.0,          3.2,       4.0,       5.0,      50.0),
]

# nomes antigos, mantidos para o renderizador anterior continuar funcionando
APRESENTACAO_S = 2.0
RESULTADO_S = 1.0
CONQUISTA_S = 2.5


def nivel_da(restantes_antes):
    for nome, minimo, ap, pc, rs, cq, mx in NIVEIS:
        if restantes_antes >= minimo:
            return nome, ap, pc, rs, cq, mx
    return NIVEIS[-1][0], *NIVEIS[-1][2:]


def cena_da_partida(p):
    nome, ap, pc, rs, cq, mx = nivel_da(p["restantes"] + 1)
    n_chutes = len(p["chutes"])
    por_chute = min(pc, mx / n_chutes)
    fases = {"apresentacao": ap, "chutes": round(n_chutes * por_chute, 3),
             "resultado": rs, "conquista": cq}
    duracao = round(sum(fases.values()) * FPS) / FPS
    return {"partida": p["n"], "nivel": nome, "duracao": duracao, "fases": fases,
            "tempo_chute": round(por_chute, 3), "ritmo": 1.0}


def dividir(partidas, n_episodios=NUM_EPISODIOS):
    cenas = [cena_da_partida(p) for p in partidas]
    total_cenas = sum(c["duracao"] for c in cenas)
    extras = ABERTURA_S + RANKING_S * (n_episodios - 1) + CAMPEAO_S
    alvo = (total_cenas + extras) / n_episodios
    episodios = []
    atual = {"cenas": [], "duracao": ABERTURA_S}
    for c in cenas:
        restam = len(episodios) < n_episodios - 1
        if restam and atual["cenas"] and atual["duracao"] + c["duracao"] / 2 + RANKING_S > alvo:
            episodios.append(atual)
            atual = {"cenas": [], "duracao": 0.0}
        atual["cenas"].append(c)
        atual["duracao"] += c["duracao"]
    episodios.append(atual)
    saida = []
    inicio = 0.0
    for i, e in enumerate(episodios, start=1):
        ultimo = i == len(episodios)
        fim = CAMPEAO_S if ultimo else RANKING_S
        total = e["duracao"] + fim
        saida.append({
            "numero": i,
            "abertura": i == 1,
            "encerramento": "campeao" if ultimo else "ranking",
            "partidas": [c["partida"] for c in e["cenas"]],
            "cenas": e["cenas"],
            "duracao_s": round(total, 2),
            "quadros": int(round(total * FPS)),
            "inicio_global_s": round(inicio, 2),
        })
        inicio += total
    return saida


def formatar(seg):
    h, resto = divmod(int(round(seg)), 3600)
    m, s = divmod(resto, 60)
    return f"{h}h{m:02d}min{s:02d}s" if h else f"{m}min{s:02d}s"


def main():
    with open(ENTRADA, encoding="utf-8") as arq:
        roteiro = json.load(arq)
    partidas = roteiro["partidas"]
    eps = dividir(partidas)
    total = sum(e["duracao_s"] for e in eps)
    with open(SAIDA, "w", encoding="utf-8") as arq:
        json.dump({"fps": FPS, "abertura_s": ABERTURA_S, "ranking_s": RANKING_S,
                   "campeao_s": CAMPEAO_S, "episodios": eps, "total_s": round(total, 2)},
                  arq, separators=(",", ":"))
    print(f"{len(partidas)} partidas divididas em {len(eps)} episodios. "
          f"Duracao total: {formatar(total)} ({int(round(total * FPS))} quadros)")
    for e in eps:
        a, b = e["partidas"][0], e["partidas"][-1]
        niveis = sorted({c["nivel"] for c in e["cenas"]})
        print(f"  Ep {e['numero']:>2}: partidas {a:>3}-{b:>3} ({len(e['partidas'])} lutas), "
              f"{formatar(e['duracao_s'])}  [{', '.join(niveis)}]")
    print(f"Arquivo {SAIDA}")


if __name__ == "__main__":
    main()
