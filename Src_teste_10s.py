"""Teste de 10 segundos: prova que o caminho GitHub -> MP4 funciona.

Gera um video vertical 1080x1920, 30 fps, no estilo do video de referencia:
mapa em cima (placeholder animado), painel de confronto embaixo.
"""
import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 1080, 1920
FPS = 30
DURACAO = 10
TOTAL_QUADROS = FPS * DURACAO
ALTURA_MAPA = 900  # ~47% da tela

FUNDO = (13, 17, 36)
DOURADO = (245, 190, 60)
BRANCO = (255, 255, 255)
CINZA = (120, 128, 150)
VERDE = (60, 200, 120)
VERMELHO = (220, 70, 70)

SAIDA = os.path.join("output", "teste_10s.mp4")


def carregar_fonte(tamanho):
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for c in caminhos:
        if os.path.exists(c):
            return ImageFont.truetype(c, tamanho)
    return ImageFont.load_default()


F_TITULO = carregar_fonte(44)
F_NOME = carregar_fonte(56)
F_PEQ = carregar_fonte(34)
F_GRANDE = carregar_fonte(90)


def texto_centro(d, x, y, txt, fonte, cor):
    d.text((x, y), txt, font=fonte, fill=cor, anchor="mm")


def desenhar_mapa(d, t):
    # Zoom suave simulando a camera (placeholder do mapa real)
    zoom = 1.0 + 0.5 * min(t / 4.0, 1.0)
    cx, cy = LARGURA // 2, ALTURA_MAPA // 2
    # Territorio do atacante (azul) e do defensor (amarelo)
    for i, cor in enumerate([(30, 90, 200), (240, 200, 30)]):
        deslocamento = -150 if i == 0 else 150
        pontos = []
        for k in range(10):
            ang = 2 * math.pi * k / 10
            raio = (230 + 40 * math.sin(k * 2.3 + i)) * zoom
            pontos.append((cx + deslocamento * zoom + raio * math.cos(ang),
                           cy + raio * 0.7 * math.sin(ang)))
        d.polygon(pontos, fill=cor)
    # Conquista: o defensor e pintado com a cor do vencedor apos 8 s
    if t >= 8:
        progresso = min((t - 8) / 1.5, 1.0)
        raio = 300 * progresso * zoom
        d.ellipse([cx + 150 * zoom - raio, cy - raio * 0.7,
                   cx + 150 * zoom + raio, cy + raio * 0.7],
                  fill=(30, 90, 200))


def desenhar_painel(d, t):
    y0 = ALTURA_MAPA
    d.line([(0, y0), (LARGURA, y0)], fill=DOURADO, width=4)
    d.text((270, y0 + 80), "ATACANTE", font=F_TITULO, fill=DOURADO, anchor="mm")
    d.text((810, y0 + 80), "DEFENSOR", font=F_TITULO, fill=DOURADO, anchor="mm")
    d.rectangle([180, y0 + 130, 360, y0 + 250], fill=(30, 90, 200))
    d.rectangle([720, y0 + 130, 900, y0 + 250], fill=(240, 200, 30))
    texto_centro(d, 270, y0 + 300, "CLUBE A", F_NOME, BRANCO)
    texto_centro(d, 810, y0 + 300, "CLUBE B", F_NOME, BRANCO)
    texto_centro(d, 540, y0 + 190, "VS", F_GRANDE, DOURADO)

    # Penaltis: 5 cobrancas para cada lado, uma a cada 1,2 s a partir de 2 s
    resultado_a = [1, 1, 0, 1, 0]
    resultado_b = [1, 0, 0, 1, 0]
    gols_a = gols_b = 0
    for i in range(5):
        x = 540 - 160 + i * 80 - 0
        quando = 2 + i * 1.2
        for lado, resultado, yb in ((0, resultado_a, y0 + 480),
                                    (1, resultado_b, y0 + 600)):
            if t >= quando:
                cor = VERDE if resultado[i] else VERMELHO
                if resultado[i] and lado == 0:
                    gols_a += 1
                if resultado[i] and lado == 1:
                    gols_b += 1
            else:
                cor = CINZA
            d.ellipse([x - 28, yb - 28, x + 28, yb + 28], fill=cor)
    d.text((140, y0 + 480), "A", font=F_NOME, fill=BRANCO, anchor="mm")
    d.text((140, y0 + 600), "B", font=F_NOME, fill=BRANCO, anchor="mm")
    texto_centro(d, 540, y0 + 760, f"{gols_a}  x  {gols_b}", F_GRANDE, BRANCO)
    if t >= 8:
        texto_centro(d, 540, y0 + 880, "VENCEDOR: CLUBE A", F_NOME, VERDE)
    texto_centro(d, 540, ALTURA - 60, "GUERRA DOS CLUBES - TESTE 10s", F_PEQ, CINZA)


def montar_quadro(n):
    t = n / FPS
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    d = ImageDraw.Draw(img)
    desenhar_mapa(d, t)
    desenhar_painel(d, t)
    return img


def main():
    os.makedirs("output", exist_ok=True)
    comando = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{LARGURA}x{ALTURA}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(DURACAO),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-crf", "20", "-c:a", "aac", "-shortest", SAIDA,
    ]
    processo = subprocess.Popen(comando, stdin=subprocess.PIPE)
    for n in range(TOTAL_QUADROS):
        processo.stdin.write(montar_quadro(n).tobytes())
    processo.stdin.close()
    codigo = processo.wait()
    if codigo != 0:
        raise SystemExit("ffmpeg falhou")
    print("Video gerado:", SAIDA)


if __name__ == "__main__":
    main()
