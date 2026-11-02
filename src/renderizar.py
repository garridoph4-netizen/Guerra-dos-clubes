
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)

W, H = 720, 1280
FPS = 20
DURACAO = 15


def carregar(nome):
    with open(DATA / nome, encoding="utf-8") as f:
        return json.load(f)


def fonte(tamanho):
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    for caminho in caminhos:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, tamanho)

    return ImageFont.load_default()


def centralizar(draw, y, texto, tamanho, cor):
    f = fonte(tamanho)
    caixa = draw.textbbox((0, 0), str(texto), font=f)
    x = (W - (caixa[2] - caixa[0])) // 2
    draw.text((x, y), str(texto), font=f, fill=cor)


def criar_frame(partida, numero, total, progresso):
    img = Image.new("RGB", (W, H), (7, 13, 28))
    d = ImageDraw.Draw(img)

    dourado = (224, 183, 91)
    branco = (245, 245, 245)

    d.rectangle((0, 0, W, 100), fill=(13, 25, 47))
    centralizar(d, 25, "GUERRA DOS CLUBES", 30, dourado)

    centralizar(d, 145, "BATALHA TERRITORIAL", 25, branco)
    centralizar(d, 205, f"PARTIDA {numero}", 23, dourado)

    atacante = partida.get("atacante", "?")
    defensor = partida.get("defensor", "?")

    d.rounded_rectangle(
        (35, 330, 685, 510),
        radius=24,
        fill=(25, 35, 57),
        outline=(190, 50, 65),
        width=4
    )

    centralizar(d, 355, f"CLUBE {atacante}", 43, branco)
    centralizar(d, 535, "VS", 65, dourado)

    d.rounded_rectangle(
        (35, 620, 685, 800),
        radius=24,
        fill=(25, 35, 57),
        outline=(40, 110, 190),
        width=4
    )

    centralizar(d, 675, f"CLUBE {defensor}", 43, branco)

    chutes = partida.get("chutes", [])
    quantidade = int(progresso * len(chutes))

    centralizar(d, 855, "DISPUTA DE PÊNALTIS", 27, dourado)

    gols = [0, 0]

    for i, chute in enumerate(chutes[:quantidade]):
        x = 70 + (i % 8) * 82
        y = 940 + (i // 8) * 90

        if isinstance(chute, list) and len(chute) >= 2:
            lado = int(chute[0])
            gol = bool(chute[1])
        else:
            lado = 0
            gol = False

        if lado in (0, 1) and gol:
            gols[lado] += 1

        cor = (30, 180, 100) if gol else (205, 55, 65)

        d.ellipse(
            (x - 25, y - 25, x + 25, y + 25),
            fill=cor
        )

        d.text(
            (x - 9, y - 17),
            "G" if gol else "X",
            font=fonte(25),
            fill=branco
        )

    centralizar(
        d,
        1110,
        f"{gols[0]}  x  {gols[1]}",
        43,
        branco
    )

    centralizar(
        d,
        1200,
        "SIMULAÇÃO TERRITORIAL",
        18,
        dourado
    )

    return img


def main():
    roteiro = carregar("roteiro.json")
    partidas = roteiro["partidas"]

    if not partidas:
        raise RuntimeError("O roteiro não possui partidas.")

    partida = partidas[0]
    total_frames = FPS * DURACAO

    print("Renderizando primeira partida...")
    print("Atacante:", partida.get("atacante"))
    print("Defensor:", partida.get("defensor"))
    print("Cobranças:", len(partida.get("chutes", [])))

    with tempfile.TemporaryDirectory() as pasta:
        padrao = str(Path(pasta) / "frame_%05d.png")

        for i in range(total_frames):
            progresso = min(1, i / (total_frames - 1))

            frame = criar_frame(
                partida,
                1,
                len(partidas),
                progresso
            )

            frame.save(padrao % i)

        destino = OUT / "episodio_1_teste.mp4"

        comando = [
            "ffmpeg",
            "-y",
            "-framerate", str(FPS),
            "-i", padrao,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(destino)
        ]

        subprocess.run(comando, check=True)

    print("Vídeo criado:", destino)


if __name__ == "__main__":
    main()
