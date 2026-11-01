"""Divide o roteiro da guerra em episodios e calcula a duracao de cada cena.

Le data/roteiro.json (uma unica simulacao continua) e grava data/episodios.json.
Nenhuma partida e cortada no meio: cada episodio e um bloco de partidas seguidas.

Ritmo: no comeco (muitos clubes) as cenas sao rapidas; perto do fim ficam
mais lentas e dramaticas. Disputas muito longas sao aceleradas.
"""
import json
import os

ENTRADA = os.path.join("data", "roteiro.json")
SAIDA = os.path.join("data", "episodios.json")

FPS = 30
ALVO_EPISODIO_S = 210      # duracao desejada de cada episodio (3min30)
ABERTURA_S = 35            # titulo + expansao inicial (so no episodio 1)
RANKING_S = 6              # cartao de ranking no fim de cada episodio
CAMPEAO_S = 12             # cartao do campeao no ultimo episodio

APRESENTACAO_S = 2.0       # atacante x defensor aparecem
POR_CHUTE_S = 0.9          # cada cobranca
RESULTADO_S = 1.0          # mostra quem venceu
CONQUISTA_S = 2.5          # territorio muda de dono
MIN_POR_CHUTE_S = 0.35
MAX_DISPUTA_S = 14.0       # disputas enormes sao aceleradas


def fator_ritmo(restantes_antes):
    """Quanto menor, mais rapido."""
    if restantes_antes >= 100:
        return 0.5
    if restantes_antes >= 50:
        return 0.7
    if restantes_antes >= 16:
        return 0.9
    if restantes_antes >= 6:
        return 1.2
    if restantes_antes >= 3:
        return 1.5
    return 2.0


def cena_da_partida(p):
    f = fator_ritmo(p["restantes"] + 1)
    n_chutes = len(p["chutes"])
    por_chute = max(MIN_POR_CHUTE_S, min(POR_CHUTE_S * f, MAX_DISPUTA_S / n_chutes))
    duracao = (APRESENTACAO_S * f + n_chutes * por_chute
               + RESULTADO_S * f + CONQUISTA_S * f)
    # arredonda para quadros inteiros
    duracao = round(duracao * FPS) / FPS
    return {"partida": p["n"], "duracao": duracao, "tempo_chute": round(por_chute, 3),
            "ritmo": f}


def dividir(partidas, alvo=ALVO_EPISODIO_S):
    cenas = [cena_da_partida(p) for p in partidas]
    episodios = []
    atual = {"cenas": [], "duracao": ABERTURA_S}
    for c in cenas:
        reserva = RANKING_S
        if atual["cenas"] and atual["duracao"] + c["duracao"] + reserva > alvo:
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
    m, s = divmod(int(round(seg)), 60)
    return f"{m}min{s:02d}s"


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
        print(f"  Ep {e['numero']:>2}: partidas {a:>3}-{b:>3} ({len(e['partidas'])} lutas), "
              f"{formatar(e['duracao_s'])}")
    print(f"Arquivo {SAIDA}")


if __name__ == "__main__":
    main()
