"""Pecas visuais do video: escudos, painel de confronto e cartoes.

Estilo inspirado no video de referencia: mapa em cima, painel escuro embaixo,
rotulos dourados, espadas cruzadas e (aqui) cobrancas de penalti no lugar dos dados.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 1080, 1920
MAPA_H = 900
PAINEL_H = ALTURA - MAPA_H

FUNDO = (13, 17, 36)
FUNDO_PAINEL = (16, 21, 45)
DOURADO = (245, 190, 60)
BRANCO = (255, 255, 255)
CINZA = (130, 138, 160)
CINZA_ESC = (58, 64, 88)
VERDE = (60, 205, 125)
VERMELHO = (230, 70, 70)

_FONTES = {}
_CAMINHOS = [
    "/usr/share/fonts/opentype/montserrat/Montserrat-Bold.otf",
    "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def fonte(tamanho):
    tamanho = int(tamanho)
    if tamanho not in _FONTES:
        for c in _CAMINHOS:
            if os.path.exists(c):
                _FONTES[tamanho] = ImageFont.truetype(c, tamanho)
                break
        else:
            _FONTES[tamanho] = ImageFont.load_default()
    return _FONTES[tamanho]


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def escurecer(cor, f):
    return tuple(int(c * f) for c in cor)


def suave(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def saida_elastica(t):
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def sigla(nome):
    ignorar = {"DE", "DO", "DA", "DOS", "DAS", "FC", "EC", "SC", "AC"}
    palavras = [p for p in nome.replace("-", " ").split() if p]
    uteis = [p for p in palavras
             if not (len(p) == 2 and p.isupper() and p not in ("AM",))
             and p.upper() not in ignorar]
    if not uteis:
        uteis = palavras
    if len(uteis) == 1:
        return uteis[0][:3].upper()
    return "".join(p[0] for p in uteis[:3]).upper()


def listras(w, h, c1, c2, largura=26, deslocamento=0):
    y, x = np.mgrid[0:h, 0:w]
    par = (((x + y + deslocamento) // largura) % 2) == 0
    arr = np.where(par[..., None], np.array(c1, dtype=np.uint8), np.array(c2, dtype=np.uint8))
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def escudo(clube, w=230, h=150, brilho=1.0, borda=None):
    c1, c2 = hex_rgb(clube["cor1"]), hex_rgb(clube["cor2"])
    if brilho != 1.0:
        c1, c2 = escurecer(c1, brilho), escurecer(c2, brilho)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    padrao = listras(w, h, c1, c2, largura=max(10, w // 8))
    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(8, h // 8), fill=255)
    img.paste(padrao, (0, 0), mascara)
    d = ImageDraw.Draw(img)
    if borda:
        d.rounded_rectangle([1, 1, w - 2, h - 2], radius=max(8, h // 8), outline=borda, width=4)
    f = fonte(h * 0.46)
    d.text((w / 2, h / 2), sigla(clube["nome"]), font=f, fill=BRANCO, anchor="mm",
           stroke_width=max(2, h // 40), stroke_fill=(10, 12, 28))
    return img


def texto_ajustado(d, centro, texto, tam_max, larg_max, cor, ancora="mm"):
    tam = tam_max
    while tam > 18:
        f = fonte(tam)
        if d.textlength(texto, font=f) <= larg_max:
            break
        tam -= 2
    d.text(centro, texto, font=fonte(tam), fill=cor, anchor=ancora)


def espadas(d, cx, cy, tam=48, cor_lamina=(225, 230, 240), cor_cabo=DOURADO):
    for sinal in (1, -1):
        x0, y0 = cx - sinal * tam, cy + tam
        x1, y1 = cx + sinal * tam, cy - tam
        d.line([(x0, y0), (x1, y1)], fill=cor_lamina, width=9)
        mx, my = cx - sinal * tam * 0.55, cy + tam * 0.55
        px, py = 0.7071 * 18, 0.7071 * 18 * sinal
        d.line([(mx - px, my - py), (mx + px, my + py)], fill=cor_cabo, width=8)
        d.ellipse([x0 - 9, y0 - 9, x0 + 9, y0 + 9], fill=cor_cabo)


def bola_resultado(d, cx, cy, raio, gol, escala=1.0):
    r = raio * escala
    cor = VERDE if gol else VERMELHO
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor)
    k = r * 0.42
    if gol:
        d.line([(cx - k, cy), (cx - k * 0.2, cy + k * 0.8), (cx + k, cy - k * 0.8)],
               fill=BRANCO, width=max(3, int(r * 0.2)), joint="curve")
    else:
        d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=BRANCO, width=max(3, int(r * 0.2)))
        d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=BRANCO, width=max(3, int(r * 0.2)))


def chutes_lado(d, centro_x, y0, chutes, tempo_atual, tempo_por_chute, raio=26, passo=66):
    """chutes: lista de (gol, instante_de_revelacao). Desenha 5 vagas + extras."""
    reveladas = sum(1 for _, quando in chutes if tempo_atual >= quando)
    total = max(5, reveladas)
    linhas = (total + 4) // 5
    for idx in range(total):
        lin, col = divmod(idx, 5)
        na_linha = min(5, total - lin * 5)
        x = centro_x + (col - (na_linha - 1) / 2) * passo
        y = y0 + lin * (raio * 2 + 14)
        if idx < len(chutes) and tempo_atual >= chutes[idx][1]:
            gol, quando = chutes[idx]
            idade = tempo_atual - quando
            esc = 0.3 + 0.7 * saida_elastica(idade / 0.28)
            if idade < 0.4:
                anel = raio * (1 + 0.9 * (idade / 0.4))
                d.ellipse([x - anel, y - anel, x + anel, y + anel],
                          outline=VERDE if gol else VERMELHO, width=3)
            bola_resultado(d, x, y, raio, gol, esc)
        else:
            d.ellipse([x - raio, y - raio, x + raio, y + raio], outline=CINZA_ESC, width=4)
    return linhas


def painel_base():
    img = Image.new("RGB", (LARGURA, PAINEL_H), FUNDO_PAINEL)
    d = ImageDraw.Draw(img)
    d.line([(0, 2), (LARGURA, 2)], fill=DOURADO, width=4)
    return img, d


def rodape(d, restantes, partida_n, total, episodio):
    y = PAINEL_H - 60
    d.text((60, y), f"{restantes} CLUBES NA DISPUTA", font=fonte(34), fill=CINZA, anchor="lm")
    direita = f"EP. {episodio:02d}"
    if partida_n:
        direita += f" · PARTIDA {partida_n}/{total}"
    d.text((LARGURA - 60, y), direita, font=fonte(34), fill=DOURADO, anchor="rm")


def painel_confronto(e):
    """e: dicionario de estado da cena. Devolve imagem do painel."""
    img, d = painel_base()
    a, df = e["atacante"], e["defensor"]
    t = e["t"]
    ap = suave(t / 0.7)           # entrada dos escudos
    centros = (270, 810)
    if e["fase"] not in ("resultado", "conquista"):
        d.text((centros[0], 62), "ATACANTE", font=fonte(38), fill=DOURADO, anchor="mm")
        d.text((centros[1], 62), "DEFENSOR", font=fonte(38), fill=DOURADO, anchor="mm")

    for lado, clube in enumerate((a, df)):
        cx = centros[lado]
        esc = 0.6 + 0.4 * saida_elastica(t / 0.8)
        w, h = int(250 * esc), int(160 * esc)
        borda = None
        if e["fase"] in ("resultado", "conquista") and e["vencedor_lado"] == lado:
            borda = VERDE
        im = escudo(clube, w, h, borda=borda)
        if ap < 1:
            alfa = im.getchannel("A").point(lambda v: int(v * ap))
            im.putalpha(alfa)
        img.paste(im, (int(cx - w / 2), int(190 - h / 2) + 20), im)
        texto_ajustado(d, (cx, 335), clube["nome"], 58, 440, BRANCO)
        d.text((cx, 392), f'SÉRIE {clube["serie"]} · {clube["cidade"]}/{clube["uf"]}',
               font=fonte(26), fill=CINZA, anchor="mm")
        d.text((cx, 436), f'TERRITÓRIO  {e["territorio"][lado]:.1f}%'.replace(".", ","),
               font=fonte(30), fill=DOURADO, anchor="mm")

    if ap > 0.2:
        espadas(d, 540, 205, 46)

    # cobrancas
    tc = e["tempo_chutes"]
    for lado in (0, 1):
        chutes_lado(d, centros[lado], 540, e["chutes"][lado], tc, e["tempo_por_chute"])
    gols = e["placar"]
    d.text((540, 585), f"{gols[0]}-{gols[1]}", font=fonte(104), fill=BRANCO, anchor="mm")
    d.text((540, 500), "PÊNALTIS", font=fonte(26), fill=CINZA, anchor="mm")

    if e["fase"] in ("resultado", "conquista"):
        vl = e["vencedor_lado"]
        pl = 1 - vl
        cxv, cxp = centros[vl], centros[pl]
        d.text((cxv, 62), "VENCEDOR", font=fonte(38), fill=VERDE, anchor="mm")
        # apaga o lado perdedor
        x0 = 0 if pl == 0 else LARGURA // 2
        regiao = img.crop((x0, 20, x0 + LARGURA // 2, 470))
        escuro = Image.new("RGB", regiao.size, FUNDO_PAINEL)
        img.paste(Image.blend(regiao, escuro, 0.62), (x0, 20))
        d.text((cxp, 62), "ELIMINADO", font=fonte(38), fill=VERMELHO, anchor="mm")
    if e["fase"] == "conquista":
        n = int(e["conquistadas_mostrar"])
        vencedor = (a, df)[e["vencedor_lado"]]
        texto_ajustado(d, (540, 800), f'{vencedor["nome"]} conquista {n} municípios', 44, 980, DOURADO)

    rodape(d, e["restantes"], e["partida_n"], e["total_partidas"], e["episodio"])
    return img


def _linha_ranking(d, img, x, y, pos, clube, valor):
    d.text((x, y), str(pos), font=fonte(40), fill=DOURADO, anchor="lm")
    mini = escudo(clube, 84, 56)
    img.paste(mini, (x + 50, y - 28), mini)
    texto_ajustado(d, (x + 156, y), clube["nome"], 34, 190, BRANCO, ancora="lm")
    d.text((x + 470, y), valor, font=fonte(32), fill=CINZA, anchor="rm")


def painel_ranking(titulo, episodio, restantes, vitorias, territorios):
    """vitorias/territorios: listas de (clube, texto_valor), ate 5 itens."""
    img, d = painel_base()
    d.text((60, 90), titulo, font=fonte(58), fill=BRANCO, anchor="lm")
    d.text((LARGURA - 60, 90), f"EP. {episodio:02d}", font=fonte(34), fill=DOURADO, anchor="rm")
    d.text((60, 190), "MAIS VITÓRIAS", font=fonte(32), fill=DOURADO, anchor="lm")
    d.text((570, 190), "MAIOR TERRITÓRIO", font=fonte(32), fill=DOURADO, anchor="lm")
    for i, (c, v) in enumerate(vitorias[:5]):
        _linha_ranking(d, img, 50, 290 + i * 120, i + 1, c, v)
    for i, (c, v) in enumerate(territorios[:5]):
        _linha_ranking(d, img, 560, 290 + i * 120, i + 1, c, v)
    d.text((LARGURA / 2, PAINEL_H - 60), f"{restantes} CLUBES RESTANTES", font=fonte(34),
           fill=CINZA, anchor="mm")
    return img


def painel_campeao(clube, vitorias, episodio):
    img, d = painel_base()
    d.text((540, 130), "CAMPEÃO", font=fonte(120), fill=DOURADO, anchor="mm")
    im = escudo(clube, 440, 290, borda=DOURADO)
    img.paste(im, (320 - 0 + 0, 230), im)
    texto_ajustado(d, (540, 600), clube["nome"], 96, 980, BRANCO)
    d.text((540, 690), f'SÉRIE {clube["serie"]} · {clube["cidade"]}/{clube["uf"]}',
           font=fonte(40), fill=CINZA, anchor="mm")
    d.text((540, 790), f"{vitorias} vitórias · 100% do Brasil", font=fonte(46),
           fill=DOURADO, anchor="mm")
    d.text((540, 900), "QUEM DOMINA O BRASIL?", font=fonte(36), fill=CINZA, anchor="mm")
    d.text((LARGURA - 60, PAINEL_H - 60), f"EP. {episodio:02d}", font=fonte(34),
           fill=DOURADO, anchor="rm")
    return img


def painel_titulo(t, subtitulo="156 clubes · Séries A, B, C e D · 2026", extra=""):
    img, d = painel_base()
    ap = suave(t / 1.2)
    deslocamento = int((1 - ap) * 60)
    cor = tuple(int(c * ap + FUNDO_PAINEL[i] * (1 - ap)) for i, c in enumerate(DOURADO))
    cor_b = tuple(int(c * ap + FUNDO_PAINEL[i] * (1 - ap)) for i, c in enumerate(BRANCO))
    d.text((540, 230 + deslocamento), "GUERRA", font=fonte(150), fill=cor_b, anchor="mm")
    d.text((540, 390 + deslocamento), "DOS CLUBES", font=fonte(130), fill=cor_b, anchor="mm")
    d.line([(240, 490), (840, 490)], fill=cor, width=5)
    d.text((540, 580 + deslocamento), "QUEM DOMINA O BRASIL?", font=fonte(52), fill=cor, anchor="mm")
    d.text((540, 700), subtitulo, font=fonte(34), fill=CINZA, anchor="mm")
    if extra:
        d.text((540, 820), extra, font=fonte(46), fill=BRANCO, anchor="mm")
    return img
