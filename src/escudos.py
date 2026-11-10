#!/usr/bin/env python3
# Baixa escudos dos clubes para a pasta escudos/.
# Prioridade: data/escudos_manuais.txt; depois TheSportsDB; por fim Wikipedia.
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

CLUBES = "data/clubes.csv"
MANUAIS = "data/escudos_manuais.txt"
APELIDOS = "data/escudos_apelidos.csv"
TITULOS = "data/escudos_titulos.csv"
PASTA = "escudos"
RELATORIO = "data/escudos_relatorio.json"
UA = "GuerraDosClubes/1.0 (projeto pessoal; contato: github.com/garridoph4-netizen/Guerra-dos-clubes)"
CHAVE_SDB = os.environ.get("THESPORTSDB_KEY", "3")
TIMEOUT = 25


def slug(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto or "clube"


def sha1(caminho):
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def requisitar(url, aceitar="*/*"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": aceitar,
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resposta:
        return resposta.read()


def ler_manuais():
    resultado = {}
    if not os.path.exists(MANUAIS):
        print(f"Aviso: arquivo manual não encontrado: {MANUAIS}")
        return resultado
    with open(MANUAIS, encoding="utf-8-sig") as arq:
        for linha in arq:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, fonte = linha.split("=", 1)
            nome, fonte = nome.strip(), fonte.strip()
            if nome and fonte:
                resultado[nome] = fonte
    return resultado


def carregar_csv(caminho, c1, c2):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8-sig", newline="") as arq:
        leitor = csv.DictReader(arq)
        if not leitor.fieldnames or c1 not in leitor.fieldnames or c2 not in leitor.fieldnames:
            return {}
        return {linha[c1]: linha[c2] for linha in leitor if linha.get(c1)}


def nome_arquivo_wiki(fonte):
    """Extrai o título de Ficheiro: de um link da Wikipedia."""
    p = urllib.parse.urlparse(fonte)
    if "/wiki/" in p.path:
        titulo = p.path.split("/wiki/", 1)[1]
        titulo = urllib.parse.unquote(titulo).replace("_", " ")
        if titulo.lower().startswith("ficheiro:"):
            return titulo.split(":", 1)[1]
        if titulo.lower().startswith("file:"):
            return titulo.split(":", 1)[1]
    return None


def resolver_fonte(nome, cidade, fonte):
    if fonte.startswith(("http://", "https://")):
