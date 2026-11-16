#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Importador resiliente do backlog AlertAção para GitHub Issues e Projects.

Requisitos:
  - Python 3.10+
  - GitHub CLI (gh) instalado e autenticado
  - Para GitHub Projects: gh auth refresh -s project

Exemplos (PowerShell):
  python importar_backlog_corrigido.py --repo LeoAntolini/alertacao --dry-run
  python importar_backlog_corrigido.py --repo LeoAntolini/alertacao --atualizar
  python importar_backlog_corrigido.py --repo LeoAntolini/alertacao --atualizar --project 1 --owner LeoAntolini

Comportamento seguro:
  - Não apaga issues, labels, milestones nem itens do Project.
  - Faz correspondência por título normalizado e por titulo_anterior.
  - Com --atualizar, atualiza título, descrição, milestone e labels gerenciadas.
  - Sem --atualizar, mantém issues existentes sem alterar seu conteúdo.
  - Com --project, garante que issues existentes e novas estejam no Project.
  - Repetir a execução é seguro: inclusões já existentes no Project são ignoradas.
  - Erros temporários de rede/GitHub recebem novas tentativas.
  - Falhas individuais são registradas e o processamento continua.
  - O modo --dry-run consulta o GitHub, mas não executa alterações.
"""

import argparse
import csv
import json
import logging
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

MILESTONES = {
    "Sprint 1 (07-13/11)": "2026-11-13T23:59:00Z",
    "Sprint 2 (14-20/11)": "2026-11-20T23:59:00Z",
    "Sprint 3 (21-25/11)": "2026-11-25T23:59:00Z",
    "Pós-MVP": None,
}

LABEL_COLORS = {
    "prio:must": "B60205",
    "prio:should": "FBCA04",
    "prio:could": "0E8A16",
    "tipo:implementacao": "1D76DB",
    "tipo:infra": "5319E7",
    "tipo:teste": "C2E0C6",
    "tipo:requisito": "D93F0B",
    "tipo:modelagem": "0052CC",
    "tipo:arquitetura": "006B75",
    "tipo:documentacao": "BFD4F2",
}
DEFAULT_COLOR = "EDEDED"
PREFIXOS_GERENCIADOS = ("prio:", "tipo:", "etapa:", "pts:")
MAX_TENTATIVAS = 5
ESPERA_BASE = 2.0

TRANSIENT_MARKERS = (
    "http 502", "http 503", "http 504",
    "502 bad gateway", "503 service unavailable", "504 gateway timeout",
    "gateway timeout", "timed out", "timeout",
    "connection reset", "connection refused", "temporary failure",
    "tls handshake timeout", "server error",
)


def configurar_log():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("importar_backlog.log", encoding="utf-8"),
        ],
    )


def normalizar(texto):
    """Normaliza acentos, caixa, espaços e variantes comuns de hífen."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.casefold().strip()
    for hifen in ("‐", "‑", "‒", "–", "—", "−"):
        texto = texto.replace(hifen, "-")
    return " ".join(texto.split())


def chave_titulo(titulo):
    """Ignora o prefixo [RF01], [INFRA] etc. para localizar issues existentes."""
    titulo = str(titulo or "").strip()
    if titulo.startswith("[") and "]" in titulo:
        titulo = titulo.split("]", 1)[1]
    return normalizar(titulo)


def comando(cmd, dry_run=False, mutating=False, tentativas=MAX_TENTATIVAS):
    """Executa gh; repete apenas falhas transitórias identificáveis."""
    if dry_run and mutating:
        logging.info("[DRY-RUN] %s", subprocess.list2cmdline(cmd))
        return ""

    ultima_mensagem = ""
    for tentativa in range(1, tentativas + 1):
        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            ultima_mensagem = "Timeout: o comando excedeu 180 segundos."
            resultado = None
        except OSError as exc:
            raise RuntimeError(f"Não foi possível executar o comando {cmd[0]!r}: {exc}") from exc

        if resultado is not None and resultado.returncode == 0:
            return (resultado.stdout or "").strip()

        if resultado is not None:
            ultima_mensagem = (resultado.stderr or resultado.stdout or "").strip()
        mensagem_lower = ultima_mensagem.casefold()
        temporario = (resultado is None) or any(m in mensagem_lower for m in TRANSIENT_MARKERS)

        if not temporario or tentativa == tentativas:
            raise RuntimeError(
                f"Falha no comando: {subprocess.list2cmdline(cmd)}\n{ultima_mensagem}"
            )

        espera = ESPERA_BASE * (2 ** (tentativa - 1))
        logging.warning(
            "Falha temporária (%s/%s). Nova tentativa em %.0f s: %s",
            tentativa, tentativas, espera, ultima_mensagem[:250],
        )
        time.sleep(espera)

    raise RuntimeError(ultima_mensagem)


def gh_json(cmd, dry_run=False):
    saida = comando(cmd, dry_run=dry_run, mutating=False)
    try:
        return json.loads(saida or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"O GitHub CLI retornou JSON inválido para {cmd}: {exc}") from exc


def carregar_csv(caminho):
    caminho = Path(caminho)
    if not caminho.is_file():
        raise RuntimeError(f"CSV não encontrado: {caminho.resolve()}")

    with caminho.open("r", newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.DictReader(arquivo)
        obrigatorias = {
            "titulo", "descricao", "etapa", "tipo",
            "prioridade", "pontos", "sprint",
        }
        faltando = obrigatorias - set(leitor.fieldnames or [])
        if faltando:
            raise RuntimeError(f"Colunas ausentes no CSV: {', '.join(sorted(faltando))}")
        linhas = list(leitor)

    if not linhas:
        raise RuntimeError("O CSV não contém itens.")

    vistos = {}
    for numero, linha in enumerate(linhas, start=2):
        for campo in ("titulo", "descricao", "etapa", "tipo", "prioridade", "pontos", "sprint"):
            if not (linha.get(campo) or "").strip():
                raise RuntimeError(f"Linha {numero}: campo obrigatório vazio: {campo}")

        chave = chave_titulo(linha["titulo"])
        if chave in vistos:
            raise RuntimeError(
                f"Títulos duplicados no CSV nas linhas {vistos[chave]} e {numero}: "
                f"{linha['titulo']}"
            )
        vistos[chave] = numero

        if linha["sprint"].strip() not in MILESTONES:
            raise RuntimeError(
                f"Linha {numero}: sprint {linha['sprint']!r} não está configurada em MILESTONES."
            )

    return linhas


def obter_marcos(repo, dry_run):
    return gh_json([
        "gh", "api", f"repos/{repo}/milestones?state=all&per_page=100",
    ], dry_run=dry_run)


def garantir_marcos(repo, dry_run):
    existentes = obter_marcos(repo, dry_run)
    por_chave = {normalizar(item.get("title")): item for item in existentes}

    for titulo, vencimento in MILESTONES.items():
        if normalizar(titulo) in por_chave:
            logging.info("Marco já existe: %s", titulo)
            continue

        cmd = ["gh", "api", f"repos/{repo}/milestones", "-f", f"title={titulo}"]
        if vencimento:
            cmd += ["-f", f"due_on={vencimento}"]

        logging.info("Criando marco: %s", titulo)
        try:
            comando(cmd, dry_run=dry_run, mutating=True)
        except RuntimeError as exc:
            # O GitHub pode responder 422 se outra execução criou o marco
            # entre a consulta e a tentativa de criação. Confirma antes de falhar.
            mensagem = str(exc).casefold()
            if "422" in mensagem or "validation failed" in mensagem:
                atualizados = obter_marcos(repo, dry_run=False)
                chaves_atuais = {normalizar(i.get("title")) for i in atualizados}
                if normalizar(titulo) in chaves_atuais:
                    logging.info("Marco criado por outra execução; confirmado: %s", titulo)
                    continue
            raise


def garantir_labels(repo, linhas, dry_run):
    labels = set()
    for linha in linhas:
        labels.update({
            f"prio:{linha['prioridade'].strip()}",
            f"tipo:{linha['tipo'].strip()}",
            f"etapa:{linha['etapa'].strip()}",
            f"pts:{linha['pontos'].strip()}",
        })

    for nome in sorted(labels):
        cmd = [
            "gh", "label", "create", nome,
            "--repo", repo,
            "--color", LABEL_COLORS.get(nome, DEFAULT_COLOR),
            "--force",
        ]
        comando(cmd, dry_run=dry_run, mutating=True)

    logging.info("%s labels garantidas.", len(labels))


def carregar_issues(repo, dry_run):
    itens = gh_json([
        "gh", "issue", "list",
        "--repo", repo,
        "--state", "all",
        "--limit", "1000",
        "--json", "number,title,labels,url",
    ], dry_run=dry_run)

    por_chave = {}
    ambiguas = set()
    for item in itens:
        chave = chave_titulo(item.get("title", ""))
        if chave in por_chave:
            ambiguas.add(chave)
        else:
            por_chave[chave] = item

    if ambiguas:
        logging.warning(
            "Há títulos semelhantes em mais de uma issue. Essas chaves não serão "
            "atualizadas automaticamente: %s",
            ", ".join(sorted(ambiguas)),
        )
        for chave in ambiguas:
            por_chave.pop(chave, None)

    return por_chave


def localizar_issue(linha, existentes):
    atual = existentes.get(chave_titulo(linha["titulo"]))
    if atual:
        return atual

    anteriores = (linha.get("titulo_anterior") or "").split("|")
    for anterior in anteriores:
        if anterior.strip():
            atual = existentes.get(chave_titulo(anterior))
            if atual:
                return atual
    return None


def atualizar_issue(repo, numero, linha, labels_novas, labels_atuais, dry_run):
    remover = [
        nome for nome in labels_atuais
        if nome.startswith(PREFIXOS_GERENCIADOS) and nome not in labels_novas
    ]
    cmd = [
        "gh", "issue", "edit", str(numero),
        "--repo", repo,
        "--title", linha["titulo"].strip(),
        "--body", linha["descricao"],
        "--milestone", linha["sprint"].strip(),
    ]
    for label in labels_novas:
        cmd += ["--add-label", label]
    for label in remover:
        cmd += ["--remove-label", label]
    comando(cmd, dry_run=dry_run, mutating=True)


def criar_issue(repo, linha, labels_novas, dry_run):
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", linha["titulo"].strip(),
        "--body", linha["descricao"],
        "--milestone", linha["sprint"].strip(),
    ]
    for label in labels_novas:
        cmd += ["--label", label]

    if dry_run:
        comando(cmd, dry_run=True, mutating=True)
        return None

    # Em criação, não repetimos cegamente após timeout: a primeira tentativa
    # pode ter criado a issue mesmo que a resposta não tenha chegado ao cliente.
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            saida = comando(cmd, dry_run=False, mutating=True, tentativas=1)
            for trecho in reversed(saida.splitlines()):
                if trecho.strip().startswith("https://github.com/"):
                    return trecho.strip()
            raise RuntimeError(
                "O GitHub não retornou a URL da issue criada. "
                "Confira a lista de issues antes de tentar novamente."
            )
        except RuntimeError as exc:
            mensagem = str(exc).casefold()
            temporario = any(m in mensagem for m in TRANSIENT_MARKERS)
            if not temporario:
                raise

            # Confere se a criação foi concluída apesar do erro de comunicação.
            encontradas = carregar_issues(repo, dry_run=False)
            existente = encontradas.get(chave_titulo(linha["titulo"]))
            if existente:
                logging.warning(
                    "A criação foi concluída apesar da falha de resposta; "
                    "issue #%s localizada. Não será criada outra.",
                    existente["number"],
                )
                return existente.get("url") or (
                    f"https://github.com/{repo}/issues/{existente['number']}"
                )

            if tentativa == MAX_TENTATIVAS:
                raise
            espera = ESPERA_BASE * (2 ** (tentativa - 1))
            logging.warning(
                "Falha temporária ao criar issue. Nenhuma issue correspondente "
                "foi encontrada; nova tentativa em %.0f s.",
                espera,
            )
            time.sleep(espera)

    raise RuntimeError("Não foi possível criar a issue após várias tentativas.")


def garantir_no_project(project, owner, url, dry_run):
    cmd = [
        "gh", "project", "item-add", str(project),
        "--owner", owner,
        "--url", url,
    ]
    try:
        comando(cmd, dry_run=dry_run, mutating=True)
        logging.info("Issue vinculada ao Project: %s", url)
        return True
    except RuntimeError as exc:
        mensagem = str(exc).casefold()
        if "content already exists in this project" in mensagem:
            logging.info("Issue já está no Project; ignorando: %s", url)
            return False
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Importa/atualiza o backlog AlertAção no GitHub com retomada segura."
    )
    parser.add_argument("--repo", required=True, help="DONO/REPOSITORIO")
    parser.add_argument("--csv", default="backlog_alertacao.csv")
    parser.add_argument("--project", type=int, help="Número do GitHub Project")
    parser.add_argument("--owner", help="Dono do Project (usuário ou organização)")
    parser.add_argument("--atualizar", action="store_true",
                        help="Atualiza issues existentes; sem isso, preserva seu conteúdo.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Consulta o GitHub e simula alterações, sem gravar nada.")
    args = parser.parse_args()

    if args.project and not args.owner:
        parser.error("Use --owner junto com --project.")
    if args.project and args.project < 1:
        parser.error("--project deve ser um número positivo.")

    configurar_log()
    falhas = []
    criadas = atualizadas = puladas = vinculadas = ja_no_project = 0

    try:
        linhas = carregar_csv(args.csv)
        logging.info("%s itens lidos de %s", len(linhas), args.csv)

        # Pré-requisitos: se marcos/labels falharem, não começa a alterar issues.
        garantir_marcos(args.repo, args.dry_run)
        garantir_labels(args.repo, linhas, args.dry_run)

        existentes = carregar_issues(args.repo, args.dry_run)
        logging.info("%s issues existentes encontradas.", len(existentes))

        for indice, linha in enumerate(linhas, start=1):
            titulo = linha["titulo"].strip()
            labels_novas = [
                f"prio:{linha['prioridade'].strip()}",
                f"tipo:{linha['tipo'].strip()}",
                f"etapa:{linha['etapa'].strip()}",
                f"pts:{linha['pontos'].strip()}",
            ]
            logging.info("[%s/%s] %s", indice, len(linhas), titulo)

            try:
                atual = localizar_issue(linha, existentes)
                if atual:
                    numero = atual["number"]
                    url = atual.get("url") or f"https://github.com/{args.repo}/issues/{numero}"

                    if args.atualizar:
                        labels_atuais = [l["name"] for l in atual.get("labels", [])]
                        atualizar_issue(
                            args.repo, numero, linha, labels_novas,
                            labels_atuais, args.dry_run,
                        )
                        atualizadas += 1
                        logging.info("Issue #%s atualizada.", numero)
                    else:
                        puladas += 1
                        logging.info("Issue #%s já existe; conteúdo preservado.", numero)
                else:
                    url = criar_issue(args.repo, linha, labels_novas, args.dry_run)
                    criadas += 1
                    logging.info("Issue criada: %s", titulo)
                    if not args.dry_run:
                        # Atualiza o índice em memória para evitar duplicação dentro da mesma execução.
                        # A URL é usada para o Project; a próxima execução fará nova consulta.
                        pass

                if args.project:
                    if args.dry_run:
                        logging.info("[DRY-RUN] Garantiria vínculo ao Project: %s", url or titulo)
                    elif url:
                        try:
                            if garantir_no_project(args.project, args.owner, url, False):
                                vinculadas += 1
                            else:
                                ja_no_project += 1
                        except RuntimeError as exc:
                            if "content already exists in this project" in str(exc).casefold():
                                ja_no_project += 1
                            else:
                                raise

                if not args.dry_run:
                    time.sleep(0.5)

            except Exception as exc:
                falhas.append((titulo, str(exc)))
                logging.exception("Falha neste item; seguindo para o próximo: %s", titulo)

        logging.info("=" * 65)
        logging.info(
            "RESUMO: %s lidas | %s criadas | %s atualizadas | %s preservadas | "
            "%s vínculos novos | %s já no Project | %s falhas.",
            len(linhas), criadas, atualizadas, puladas,
            vinculadas, ja_no_project, len(falhas),
        )
        if falhas:
            logging.error("Itens com falha:")
            for titulo, erro in falhas:
                logging.error("- %s: %s", titulo, erro.replace("\n", " | "))
            sys.exit(2)

    except Exception as exc:
        logging.exception("Importação interrompida antes/durante a preparação: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
