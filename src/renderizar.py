"""Renderiza um episodio da guerra em MP4 (1080x1920, 30 fps).

Uso:
  python src/renderizar.py 1            -> output/episodio_01.mp4
  python src/renderizar.py 1 --teste    -> output/teste_visual.mp4 (amostra curta)
"""
import gzip
import json
import math
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import episodios as EP
import visual as V

W, H, MAPA_H = V.LARGURA, V.ALTURA, V.MAPA_H
FPS = 30
GEO = os.path.join("data", "unidades.geojson.gz")
TERR = os.path.join("data", "territorios.json")
ROTEIRO = os.path.join("data", "roteiro.json")
EPIS = os.path.join("data", "episodios.json")

TITULO_S = 5.0
EXPANSAO_FIM_S = 31.0
COR_UNIDADE_ESCURA = (30, 36, 62)


def cor_representativa(c1, c2):
    def vivo(c):
        return max(c) - min(c)
    return c1 if vivo(c1) >= vivo(c2) else c2


class Mundo:
    def __init__(self):
        with gzip.open(GEO, "rt", encoding="utf-8") as arq:
            feats = json.load(arq)["features"]
        with open(TERR, encoding="utf-8") as arq:
            terr = json.load(arq)
        self.clubes = terr["clubes"]
        self.num_ondas = terr["num_ondas"]
        n = len(feats)
        self.n = n
        ids = [u["id"] for u in terr["unidades"]]
        pos = {i: k for k, i in enumerate(ids)}
        self.viz = [[pos[v] for v in u["vizinhos"]] for u in terr["unidades"]]
        self.donos0 = np.array([u["dono"] for u in terr["unidades"]], dtype=np.int32)
        self.onda = np.array([u["onda"] for u in terr["unidades"]], dtype=np.int32)
        self.inicial = np.array([bool(u["inicial"]) for u in terr["unidades"]])

        kx = math.cos(math.radians(-14.0))
        self.aneis = []
        minx = np.zeros(n); miny = np.zeros(n); maxx = np.zeros(n); maxy = np.zeros(n)
        area = np.zeros(n)
        for i, f in enumerate(feats):
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            lista = []
            for p in polys:
                a = np.array(p[0], dtype=np.float64)
                a = np.column_stack([a[:, 0] * kx, -a[:, 1]])
                lista.append(a)
            self.aneis.append(lista)
            todos = np.vstack(lista)
            minx[i], miny[i] = todos.min(axis=0)
            maxx[i], maxy[i] = todos.max(axis=0)
            for a in lista:
                x, y = a[:, 0], a[:, 1]
                area[i] += abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2
        self.minx, self.miny, self.maxx, self.maxy = minx, miny, maxx, maxy
        self.area = area
        self.rank = np.empty(n, dtype=np.int64)
        self.rank[np.argsort(-area)] = np.arange(n)
        self.centros = np.column_stack([(minx + maxx) / 2, (miny + maxy) / 2])
        self.l_minx = minx.tolist(); self.l_maxx = maxx.tolist()
        self.l_miny = miny.tolist(); self.l_maxy = maxy.tolist()

        def reduzir(a, k):
            if len(a) <= 3 * k:
                return a
            return np.vstack([a[::k], a[-1:]])
        self.lods = [self.aneis,
                     [[reduzir(a, 4) for a in l] for l in self.aneis],
                     [[reduzir(a, 16) for a in l] for l in self.aneis]]

        self.cor1 = [V.hex_rgb(c["cor1"]) for c in self.clubes]
        self.cor2 = [V.hex_rgb(c["cor2"]) for c in self.clubes]
        self.cor_rep = [cor_representativa(a, b) for a, b in zip(self.cor1, self.cor2)]
        self.area_total = float(area.sum())

    # ---------- camera ----------
    def cam_brasil(self):
        bw = self.maxx.max() - self.minx.min()
        bh = self.maxy.max() - self.miny.min()
        esc = min(W / (bw * 1.06), MAPA_H / (bh * 1.06))
        return ((self.maxx.max() + self.minx.min()) / 2,
                (self.maxy.max() + self.miny.min()) / 2, esc)

    def _caixa(self, idx):
        return (self.minx[idx].min(), self.miny[idx].min(),
                self.maxx[idx].max(), self.maxy[idx].max())

    def cam_confronto(self, donos, a, d):
        ua = np.nonzero(donos == a)[0]
        ud = np.nonzero(donos == d)[0]
        idx = np.concatenate([ua, ud])
        x0, y0, x1, y1 = self._caixa(idx)
        if max(x1 - x0, y1 - y0) > 14:
            borda = [u for u in ua if any(donos[v] == d for v in self.viz[u])]
            borda += [u for u in ud if any(donos[v] == a for v in self.viz[u])]
            x0, y0, x1, y1 = self._caixa(np.array(borda))
        bw, bh = max(x1 - x0, 2.0), max(y1 - y0, 1.7)
        esc = min(W / (bw * 1.45), MAPA_H / (bh * 1.45))
        esc = max(20.0, min(esc, 700.0))
        return ((x0 + x1) / 2, (y0 + y1) / 2, esc)

    @staticmethod
    def mistura_cam(c0, c1, u):
        u = V.suave(u)
        cx = c0[0] + (c1[0] - c0[0]) * u
        cy = c0[1] + (c1[1] - c0[1]) * u
        le = math.log(c0[2]) + (math.log(c1[2]) - math.log(c0[2])) * u
        return (cx, cy, math.exp(le))

    # ---------- desenho do mapa ----------
    def _poligono(self, d, u, cam, nivel, fill):
        cx, cy, esc = cam
        if ((self.l_maxx[u] - self.l_minx[u]) * esc < 1.5
                and (self.l_maxy[u] - self.l_miny[u]) * esc < 1.5):
            px = (self.centros[u][0] - cx) * esc + W / 2
            py = (self.centros[u][1] - cy) * esc + MAPA_H / 2
            d.rectangle([px - 0.6, py - 0.6, px + 0.6, py + 0.6], fill=fill)
            return
        for a in self.lods[nivel][u]:
            pts = np.column_stack([(a[:, 0] - cx) * esc + W / 2, (a[:, 1] - cy) * esc + MAPA_H / 2])
            d.polygon(pts.ravel().tolist(), fill=fill)

    def desenhar_mapa(self, cam, donos, destaque=(), revelado=None):
        cx, cy, esc = cam
        img = Image.new("RGB", (W, MAPA_H), V.FUNDO)
        d = ImageDraw.Draw(img)
        mx0, mx1 = cx - W / 2 / esc, cx + W / 2 / esc
        my0, my1 = cy - MAPA_H / 2 / esc, cy + MAPA_H / 2 / esc
        vis = np.nonzero((self.maxx >= mx0) & (self.minx <= mx1)
                         & (self.maxy >= my0) & (self.miny <= my1))[0]
        vis = vis[np.argsort(self.rank[vis])]
        nivel = 2 if esc < 35 else (1 if esc < 110 else 0)
        if revelado is not None:
            nao = vis[~revelado[vis]]
            for u in nao:
                self._poligono(d, int(u), cam, nivel, COR_UNIDADE_ESCURA)
            vis = vis[revelado[vis]]
        por_clube = {}
        for u in vis:
            por_clube.setdefault(int(donos[u]), []).append(int(u))
        solido = esc < 45
        for c, us in por_clube.items():
            em_destaque = (not destaque) or (c in destaque)
            brilho = 1.0 if em_destaque else 0.38
            m = Image.new("L", (W, MAPA_H), 0)
            md = ImageDraw.Draw(m)
            for u in us:
                self._poligono(md, u, cam, nivel, 255)
            bb = m.getbbox()
            if bb is None:
                continue
            x0, y0 = max(0, bb[0] - 6), max(0, bb[1] - 6)
            x1, y1 = min(W, bb[2] + 6), min(MAPA_H, bb[3] + 6)
            rec = m.crop((x0, y0, x1, y1))
            if solido:
                cor = V.escurecer(self.cor_rep[c], brilho)
                pad = Image.new("RGB", rec.size, cor)
            else:
                pad = V.listras(rec.size[0], rec.size[1], V.escurecer(self.cor1[c], brilho),
                                V.escurecer(self.cor2[c], brilho), largura=22,
                                deslocamento=x0 + y0)
            img.paste(pad, (x0, y0), rec)
            tam = 7 if (destaque and em_destaque) else 5
            borda = ImageChops.subtract(rec.filter(ImageFilter.MaxFilter(tam)),
                                        rec.filter(ImageFilter.MinFilter(tam)))
            cor_b = (255, 205, 70) if (destaque and em_destaque) else V.escurecer((225, 230, 240), brilho)
            img.paste(cor_b, (x0, y0, x1, y1), borda)
        if esc >= 150:
            for u in vis:
                for a in self.lods[nivel][int(u)]:
                    pts = np.column_stack([(a[:, 0] - cx) * esc + W / 2,
                                           (a[:, 1] - cy) * esc + MAPA_H / 2])
                    d.line(pts.ravel().tolist() + pts[0].tolist(), fill=(12, 14, 30), width=1)
        return img

    def compartilhamento(self, donos):
        s = np.bincount(donos, weights=self.area, minlength=len(self.clubes))
        return s / self.area_total * 100.0


# ---------- planejamento ----------

def ordem_conquista(mundo, donos, vencedor, perdedor, conquistadas):
    ua = np.nonzero(donos == vencedor)[0]
    borda = [u for u in ua if any(donos[v] == perdedor for v in mundo.viz[u])]
    if not borda:
        borda = list(ua)
    ponto = mundo.centros[np.array(borda)].mean(axis=0)
    conq = np.array(conquistadas, dtype=np.int64)
    dist = np.hypot(*(mundo.centros[conq] - ponto).T)
    return conq[np.argsort(dist)]


def planejar(mundo, ep, partidas, donos):
    """Percorre o episodio e devolve a lista de cenas (com frames inicial/final)."""
    cenas = []
    f = 0
    n_ini = ep["partidas"][0]
    # estado antes do episodio: aplica conquistas das partidas anteriores
    donos = donos.copy()
    vitorias = {}
    for p in partidas[:n_ini - 1]:
        donos[p["conquistadas"]] = p["vencedor"]
        vitorias[p["vencedor"]] = vitorias.get(p["vencedor"], 0) + 1
    cam_atual = mundo.cam_brasil()
    restantes = len(mundo.clubes) - (n_ini - 1)

    if ep["abertura"]:
        t1 = int(TITULO_S * FPS)
        t2 = int(EXPANSAO_FIM_S * FPS)
        t3 = int(EP.ABERTURA_S * FPS)
        cenas.append({"tipo": "titulo", "f0": 0, "f1": t1})
        cenas.append({"tipo": "expansao", "f0": t1, "f1": t2})
        cenas.append({"tipo": "hold", "f0": t2, "f1": t3})
        f = t3

    for c in ep["cenas"]:
        p = partidas[c["partida"] - 1]
        frames = int(round(c["duracao"] * FPS))
        alvo = mundo.cam_confronto(donos, p["atacante"], p["defensor"])
        share = mundo.compartilhamento(donos)
        cenas.append({
            "tipo": "partida", "f0": f, "f1": f + frames, "p": p, "c": c,
            "donos": donos.copy(), "cam0": cam_atual, "cam1": alvo,
            "share": (share[p["atacante"]], share[p["defensor"]]),
            "ordem": ordem_conquista(mundo, donos, p["vencedor"], p["perdedor"], p["conquistadas"]),
            "restantes_antes": p["restantes"] + 1,
        })
        f += frames
        donos[p["conquistadas"]] = p["vencedor"]
        vitorias[p["vencedor"]] = vitorias.get(p["vencedor"], 0) + 1
        cam_atual = alvo
        restantes = p["restantes"]

    share = mundo.compartilhamento(donos)
    if ep["encerramento"] == "ranking":
        frames = int(EP.RANKING_S * FPS)
        cenas.append({"tipo": "ranking", "f0": f, "f1": f + frames, "donos": donos.copy(),
                      "cam0": cam_atual, "cam1": mundo.cam_brasil(), "share": share,
                      "vitorias": dict(vitorias), "restantes": restantes})
        f += frames
    else:
        frames = int(EP.CAMPEAO_S * FPS)
        campeao = int(donos[0])
        cenas.append({"tipo": "campeao", "f0": f, "f1": f + frames, "donos": donos.copy(),
                      "cam0": cam_atual, "cam1": mundo.cam_brasil(),
                      "campeao": campeao, "vitorias": dict(vitorias).get(campeao, 0)})
        f += frames
    return cenas, f


# ---------- quadros ----------

def quadro(mundo, cena, g, ep_num, total_partidas):
    tipo = cena["tipo"]
    fl = g - cena["f0"]
    t = fl / FPS
    dur = (cena["f1"] - cena["f0"]) / FPS
    cam_br = mundo.cam_brasil()

    if tipo in ("titulo", "expansao", "hold"):
        if tipo == "titulo":
            rev = mundo.inicial
            painel = V.painel_titulo(t)
        elif tipo == "expansao":
            p = V.suave(t / dur)
            corrente = p * (mundo.num_ondas + 1)
            rev = mundo.inicial | (mundo.onda <= corrente)
            painel = V.painel_titulo(10.0, extra=f"EXPANSÃO INICIAL · {int(rev.sum())} municípios")
        else:
            rev = np.ones(mundo.n, dtype=bool)
            painel = V.painel_titulo(10.0, extra="SÓ UM SERÁ CAMPEÃO")
        mapa = mundo.desenhar_mapa(cam_br, mundo.donos0, revelado=rev)

    elif tipo == "partida":
        p, c = cena["p"], cena["c"]
        f_ritmo = c["ritmo"]
        n = len(p["chutes"])
        tpc = c["tempo_chute"]
        ap = EP.APRESENTACAO_S * f_ritmo
        ch = n * tpc
        rs = EP.RESULTADO_S * f_ritmo
        cq = EP.CONQUISTA_S * f_ritmo
        k = dur / (ap + ch + rs + cq)
        ap, ch, rs, cq, tpc = ap * k, ch * k, rs * k, cq * k, tpc * k
        if t < ap:
            fase = "apresentacao"
        elif t < ap + ch:
            fase = "chutes"
        elif t < ap + ch + rs:
            fase = "resultado"
        else:
            fase = "conquista"
        cam = mundo.mistura_cam(cena["cam0"], cena["cam1"], t / 1.3)
        donos = cena["donos"]
        flips = 0
        if fase == "conquista":
            pr = V.suave((t - ap - ch - rs) / cq)
            flips = int(pr * len(cena["ordem"]))
            donos = donos.copy()
            donos[cena["ordem"][:flips]] = p["vencedor"]
        mapa = mundo.desenhar_mapa(cam, donos, destaque=(p["atacante"], p["defensor"]))
        # estado do painel
        chutes = [[], []]
        for i, (lado, gol) in enumerate(p["chutes"]):
            chutes[lado].append((gol, ap + i * tpc))
        tc = t
        placar = [sum(g_ for g_, q in chutes[l] if q <= tc) for l in (0, 1)]
        venc_lado = 0 if p["vencedor"] == p["atacante"] else 1
        share = list(cena["share"])
        if fase == "conquista" and len(cena["ordem"]):
            frac = flips / len(cena["ordem"])
            share[venc_lado] += frac * share[1 - venc_lado]
        painel = V.painel_confronto({
            "atacante": mundo.clubes[p["atacante"]], "defensor": mundo.clubes[p["defensor"]],
            "t": t, "fase": fase, "chutes": chutes, "tempo_chutes": tc, "tempo_por_chute": tpc,
            "placar": placar, "vencedor_lado": venc_lado, "territorio": share,
            "conquistadas_mostrar": flips, "restantes": cena["restantes_antes"],
            "partida_n": p["n"], "total_partidas": total_partidas, "episodio": ep_num,
        })

    elif tipo == "ranking":
        cam = mundo.mistura_cam(cena["cam0"], cena["cam1"], t / 1.3)
        mapa = mundo.desenhar_mapa(cam, cena["donos"])
        vit = sorted(cena["vitorias"].items(), key=lambda x: -x[1])[:5]
        vit = [(mundo.clubes[c], f"{v} vit.") for c, v in vit]
        sh = cena["share"]
        top = np.argsort(-sh)[:5]
        ter = [(mundo.clubes[int(c)], f"{sh[c]:.1f}%".replace(".", ",")) for c in top]
        painel = V.painel_ranking(f"{cena['restantes']} CLUBES NA DISPUTA", ep_num,
                                  cena["restantes"], vit, ter)

    else:  # campeao
        cam = mundo.mistura_cam(cena["cam0"], cena["cam1"], t / 1.3)
        mapa = mundo.desenhar_mapa(cam, cena["donos"])
        painel = V.painel_campeao(mundo.clubes[cena["campeao"]], cena["vitorias"], ep_num)

    img = Image.new("RGB", (W, H), V.FUNDO)
    img.paste(mapa, (0, 0))
    img.paste(painel, (0, MAPA_H))
    return img


def selecionar(cenas, total, teste):
    if not teste:
        return list(range(total))
    sel = []
    c0 = cenas[0]
    sel += list(range(c0["f0"], min(c0["f1"], c0["f0"] + 45)))
    exp = [c for c in cenas if c["tipo"] == "expansao"]
    if exp:
        mid = (exp[0]["f0"] + exp[0]["f1"]) // 2
        sel += list(range(mid, mid + 60))
    part = [c for c in cenas if c["tipo"] == "partida"]
    if part:
        sel += list(range(part[0]["f0"], part[0]["f1"]))
    ult = cenas[-1]
    sel += list(range(ult["f0"] + 30, ult["f0"] + 90))
    return sorted(set(sel))


def renderizar(ep_num, teste=False):
    with open(ROTEIRO, encoding="utf-8") as arq:
        roteiro = json.load(arq)
    with open(EPIS, encoding="utf-8") as arq:
        episodios = json.load(arq)["episodios"]
    ep = episodios[ep_num - 1]
    partidas = roteiro["partidas"]

    print("Carregando mapa...")
    mundo = Mundo()
    print(f"{mundo.n} unidades carregadas.")
    cenas, total = planejar(mundo, ep, partidas, mundo.donos0)
    sel = selecionar(cenas, total, teste)
    os.makedirs("output", exist_ok=True)
    saida = os.path.join("output", "teste_visual.mp4" if teste else f"episodio_{ep_num:02d}.mp4")
    print(f"Episodio {ep_num}: {total} quadros ({total / FPS:.0f}s). Renderizando {len(sel)} quadros...")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-shortest", saida]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    ini = time.time()
    idx = 0
    for k, g in enumerate(sel):
        while g >= cenas[idx]["f1"]:
            idx += 1
        img = quadro(mundo, cenas[idx], g, ep_num, len(partidas))
        proc.stdin.write(img.tobytes())
        if (k + 1) % 300 == 0 or k + 1 == len(sel):
            dec = time.time() - ini
            print(f"  {k + 1}/{len(sel)} quadros ({dec / (k + 1):.2f}s por quadro)", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg falhou")
    print(f"Video gerado: {saida} ({os.path.getsize(saida) / 1e6:.1f} MB)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    renderizar(int(args[0]) if args else 1, teste="--teste" in sys.argv)
