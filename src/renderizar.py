
import json
import os
import gzip
import math
import random
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LARGURA = 1080
ALTURA = 1920
FPS = 30

BASE = Path(__file__).resolve().parent.parent
DADOS = BASE / "data"
SAIDA = BASE / "videos"
SAIDA.mkdir(exist_ok=True)

FUNDO = (8, 14, 29)
BRANCO = (245, 245, 245)
DOURADO = (218, 177, 83)

def carregar_json(nome):
    with open(DADOS / nome, encoding="utf-8") as f:
        return json.load(f)

def fonte(tamanho, negrito=False):
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrito
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for caminho in caminhos:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default()

def texto_central(draw, xy, texto, tamanho, cor=BRANCO, negrito=True):
    f = fonte(tamanho, negrito)
    caixa = draw.textbbox((0, 0), str(texto), font=f)
    x = xy[0] - (caixa[2] - caixa[0]) / 2
    y = xy[1] - (caixa[3] - caixa[1]) / 2
    draw.text((x, y), str(texto), font=f, fill=cor)

def carregar_mapa():
    caminho = DADOS / "unidades.geojson.gz"
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        return json.load(f)

def projetar(coordenadas, limites, caixa):
    minx, miny, maxx, maxy = limites
    x0, y0, largura, altura = caixa
    escala = min(largura / (maxx-minx), altura / (maxy-miny))
    px = x0 + (coordenadas[0]-minx)*escala
    py = y0 + (maxy-coordenadas[1])*escala
    return int(px), int(py)

def desenhar_geometria(draw, geometria, limites, caixa, cor):
    tipo = geometria["type"]
    coords = geometria["coordinates"]

    def anel(pontos):
        return [projetar(p, limites, caixa) for p in pontos]

    if tipo == "Polygon":
        for anel_coords in coords:
            pontos = anel(anel_coords)
            if len(pontos) >= 3:
                draw.polygon(pontos, fill=cor, outline=(30, 38, 52))

    elif tipo == "MultiPolygon":
        for poligono in coords:
            for anel_coords in poligono:
                pontos = anel(anel_coords)
                if len(pontos) >= 3:
                    draw.polygon(pontos, fill=cor, outline=(30, 38, 52))

def cor_clube(clubes, dono):
    clube = clubes.get(str(dono), {})
    cor = clube.get("cor1", "#555555")
    try:
        return tuple(int(cor[i:i+2], 16) for i in (1, 3, 5))
    except Exception:
        return (85, 85, 85)

def criar_frame(partida, unidades, clubes, indice, total_frames):
    imagem = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    draw = ImageDraw.Draw(imagem)

    draw.rectangle((0, 0, LARGURA, 90), fill=(12, 22, 42))
    texto_central(draw, (LARGURA//2, 45), "GUERRA DOS CLUBES", 42, DOURADO)

    draw.rectangle((0, 900, LARGURA, 905), fill=DOURADO)

    draw.rectangle((0, 910, LARGURA, ALTURA), fill=(10, 17, 32))

    atacante = partida.get("atacante", "?")
    defensor = partida.get("defensor", "?")
    clubes_lista = list(clubes.values())

    nome_atacante = clubes.get(str(atacante), {}).get("clube", f"Clube {atacante}")
    nome_defensor = clubes.get(str(defensor), {}).get("clube", f"Clube {defensor}")

    texto_central(draw, (LARGURA//2, 1010), "DISPUTA TERRITORIAL", 34, DOURADO)
    texto_central(draw, (LARGURA//2, 1110), nome_atacante, 48)
    texto_central(draw, (LARGURA//2, 1190), "VS", 65, DOURADO)
    texto_central(draw, (LARGURA//2, 1270), nome_defensor, 48)

    chutes = partida.get("chutes", partida.get("penaltis", []))
    quantidade = min(len(chutes), max(0, int((indice / max(1, total_frames-1))*len(chutes))))

    texto_central(draw, (LARGURA//2, 1400), "PÊNALTIS", 38, DOURADO)

    for i, chute in enumerate(chutes[:quantidade]):
        x = 170 + (i % 10) * 75
        y = 1500 + (i // 10) * 85
        gol = chute.get("gol", chute.get("resultado") == "gol")
        cor = (35, 190, 105) if gol else (220, 65, 65)
        draw.ellipse((x-22, y-22, x+22, y+22), fill=cor)
        texto_central(draw, (x, y), "G" if gol else "X", 24)

    texto_central(draw, (LARGURA//2, 1740), f"PARTIDA {partida.get('numero', '?')}", 32)
    return imagem

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodio", type=int, default=1)
    parser.add_argument("--teste", action="store_true")
    args = parser.parse_args()

    roteiro = carregar_json("roteiro.json")
    episodios = carregar_json("episodios.json")
    mapa = carregar_mapa()
    clubes_dados = carregar_json("territorios.json")

    print("Dados carregados. Preparando renderização...")

    print("ATENÇÃO: renderização visual inicial.")
    print("Mapa e placar serão refinados após validar os dados.")

if __name__ == "__main__":
    main()
