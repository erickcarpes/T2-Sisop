# -*- coding: utf-8 -*-
"""
Sistema de arquivos simulado (camada 3).

Referência: Silberschatz, 9ª ed., cap. 11 — operações, FCB, tabelas de arquivos abertos,
métodos de acesso, estrutura de diretórios, links e proteção.

O que já vem pronto (FORNECIDO): a criação da raiz, as tabelas e os métodos auxiliares
(nome começando com _). Implementem os métodos marcados com TODO.

=====================================================================================
REGRAS DE CUSTO (iguais para todos os grupos — sigam à risca)
=====================================================================================
Um acesso = um bloco lido ou gravado (use _ler, _escrever e _aplicar; eles contam tudo).

Diretórios: cada diretório ocupa 1 bloco (o bloco 0 do diretório, obtido com
_bloco_do_diretorio). Ler um diretório = 1 leitura desse bloco.

resolver("/a/b/c")   lê os diretórios "/", "/a" e "/a/b" (3 leituras) e devolve o FCB de c.
                     resolver("/") devolve a raiz sem ler nada.
Operações que criam, removem ou alteram uma entrada leem os diretórios do caminho até o
pai (inclusive), exatamente como resolver, e depois:

mkdir(p)             + aloca 1 bloco para o novo diretório, grava o bloco do novo diretório
                       (1 escrita) e o bloco do pai (1 escrita)
create(p, tamanho)   + aloca ceil(tamanho / TAMANHO_BLOCO) blocos (conteúdo não é gravado)
                       e grava o bloco do pai (1 escrita)
open(p, modo, h)     lê os diretórios como resolver; nenhuma escrita
read(h, n)           lê os blocos que contêm os bytes [posição, posição + n), limitados ao
                     tamanho do arquivo; avança a posição; devolve os bytes lidos
write(h, n)          se precisar, estende o arquivo (alocador.estender); grava os blocos que
                     contêm [posição, posição + n); avança a posição; atualiza o tamanho e
                     marca o FCB como sujo. No modo 'a', a escrita começa no fim do arquivo.
seek(h, posicao)     muda a posição; nenhum acesso
close(h)             se o FCB está sujo, grava o bloco do diretório pai (1 escrita) e limpa
                     o "sujo"; atualiza as tabelas
unlink(p)            + grava o bloco do pai (1 escrita). Se o arquivo ficar sem links e
                     ninguém o tiver aberto, libera os blocos; se estiver aberto, a liberação
                     acontece no último close.

Tabelas de arquivos abertos:
- self.tabela_global: dict fcb_id -> EntradaGlobal. Uma entrada por arquivo aberto; o
  contador soma as aberturas de todos os processos. A entrada sai quando o contador zera.
- self.tabelas_processo: dict processo -> {handle: EntradaProcesso}. Uma entrada por
  abertura, com a posição e o modo.

Modos de abertura: 'r' (só leitura), 'w' (só escrita), 'rw' (ambos), 'a' (acréscimo, só
escrita). Ler com um handle sem 'r', ou escrever sem 'w'/'a': ErroSA('EBADF').
Erros: lancem ErroSA com o código adequado (veja estruturas.py).

Ganchos dos módulos (já chamados pelas operações do núcleo, que vocês implementam):
- _verificar_permissao(processo, fcb, modo): no núcleo não faz nada; o M5 implementa.
- _verificar_trava(processo, fcb):            no núcleo não faz nada; o M5 implementa.
  O núcleo deve chamar _verificar_permissao no open e _verificar_trava no read e no write.
"""
import math
from collections import Counter

from simes import parametros as P
from simes.arquivos.estruturas import FCB, EntradaGlobal, EntradaProcesso, ErroSA

MAX_LINKS_SIMBOLICOS = 8


class SistemaArquivos:

    def __init__(self, camada, alocador, bloqueio="consultivo"):
        self.camada = camada
        self.alocador = alocador
        self.bloqueio = bloqueio            # 'consultivo' ou 'mandatorio' (M5)
        self.fcbs = {}
        self._proximo_id = 0
        self.agora_ms = 0.0                 # atualizado pelo simulador antes de cada operação
        self.tabela_global = {}             # fcb_id -> EntradaGlobal
        self.tabelas_processo = {}          # processo -> {handle: EntradaProcesso}
        self.usuarios = {}                  # processo -> nome do usuário (M5); padrão: 'root'
        self.contadores = Counter()         # indicadores extras dos módulos (vão para o CSV)
        self.raiz = self._novo_fcb("/", "diretorio", None)
        self.alocador.alocar(self.raiz, 1)  # a raiz já existe ao "formatar": sem custo

    # ================================================================ FORNECIDO
    def _novo_fcb(self, nome, tipo, pai, processo=None):
        """Cria um FCB (dono = usuário do processo) e o registra em self.fcbs. Não aloca blocos."""
        fcb = FCB(self._proximo_id, nome, tipo, pai, self.agora_ms, self.usuario_de(processo))
        self.fcbs[fcb.id] = fcb
        self._proximo_id += 1
        return fcb

    def usuario_de(self, processo):
        return self.usuarios.get(processo, "root")

    def _ler(self, blocos):
        self.camada.ler(blocos)

    def _escrever(self, blocos):
        self.camada.escrever(blocos)

    def _aplicar(self, extras):
        """Executa a lista de acessos extras devolvida pelo alocador."""
        for tipo, bloco in extras:
            if tipo == "L":
                self._ler([bloco])
            else:
                self._escrever([bloco])

    def _bloco_do_diretorio(self, diretorio):
        """Bloco físico onde está o conteúdo do diretório (já executa os extras do alocador)."""
        bloco, extras = self.alocador.bloco_fisico(diretorio, 0)
        self._aplicar(extras)
        return bloco

    def _ler_diretorio(self, diretorio):
        self._ler([self._bloco_do_diretorio(diretorio)])

    def _gravar_diretorio(self, diretorio):
        self._escrever([self._bloco_do_diretorio(diretorio)])

    def _blocos_do_intervalo(self, fcb, inicio, fim):
        """Blocos físicos que contêm os bytes [inicio, fim) do arquivo (executa os extras)."""
        if fim <= inicio:
            return []
        primeiro = inicio // P.TAMANHO_BLOCO
        ultimo = (fim - 1) // P.TAMANHO_BLOCO
        blocos = []
        for i in range(primeiro, ultimo + 1):
            bloco, extras = self.alocador.bloco_fisico(fcb, i)
            self._aplicar(extras)
            blocos.append(bloco)
        return blocos

    @staticmethod
    def _blocos_necessarios(tamanho):
        return int(math.ceil(tamanho / float(P.TAMANHO_BLOCO)))

    @staticmethod
    def _dividir(caminho):
        if not caminho.startswith("/"):
            raise ErroSA("EINVAL", "o caminho deve ser absoluto: %s" % caminho)
        return [p for p in caminho.split("/") if p]

    def _entrada(self, processo, handle):
        try:
            return self.tabelas_processo[processo][handle]
        except KeyError:
            raise ErroSA("EBADF", "%s não tem o handle %s" % (processo, handle))

    def _liberar_arquivo(self, fcb):
        self.alocador.liberar(fcb)
        del self.fcbs[fcb.id]

    def _verificar_permissao(self, processo, fcb, modo):
        """Gancho do M5. No núcleo, tudo é permitido."""
        return None

    def _verificar_trava(self, processo, fcb):
        """Gancho do M5. No núcleo, travas não existem."""
        return None

    # ============================================================ TODO — núcleo (N3)
    def _resolver(self, caminho, seguir_simbolico, restantes):
        partes = self._dividir(caminho)
        atual = self.raiz
        for i, nome in enumerate(partes):
            if atual.tipo != "diretorio":
                raise ErroSA("ENOTDIR", caminho)
            self._ler_diretorio(atual)
            fid = atual.entradas.get(nome)
            if fid is None:
                raise ErroSA("ENOENT", caminho)
            filho = self.fcbs[fid]
            ultimo = (i == len(partes) - 1)
            if filho.tipo == "simbolico" and (seguir_simbolico or not ultimo):
                if restantes <= 0:
                    raise ErroSA("ELOOP", caminho)
                alvo = filho.alvo or ""
                if not alvo.startswith("/"):
                    raise ErroSA("EINVAL", "link simbólico com alvo relativo: %s" % alvo)
                if not ultimo:
                    resto = "/".join(partes[i + 1:])
                    alvo = alvo.rstrip("/")
                    alvo = (alvo + "/" + resto) if alvo else "/" + resto
                return self._resolver(alvo, True, restantes - 1)
            atual = filho
        return atual

    def _pai_e_nome(self, caminho):
        """Resolve o diretório pai (lendo os diretórios do caminho) e devolve (pai, nome).
        Também lê o próprio diretório pai, como exigem as regras de custo."""
        partes = self._dividir(caminho)
        if not partes:
            raise ErroSA("EEXIST", caminho)
        pai = self._resolver("/" + "/".join(partes[:-1]), True, MAX_LINKS_SIMBOLICOS)
        if pai.tipo != "diretorio":
            raise ErroSA("ENOTDIR", caminho)
        self._ler_diretorio(pai)
        return pai, partes[-1]

    def resolver(self, caminho, seguir_simbolico=True):
        """Devolve o FCB do caminho absoluto, lendo os diretórios do caminho (ver regras).
        Erros: ENOENT, ENOTDIR. Com o M4: segue links simbólicos (inclusive no meio do
        caminho; o último componente só se seguir_simbolico=True); ELOOP depois de
        MAX_LINKS_SIMBOLICOS links."""
        return self._resolver(caminho, seguir_simbolico, MAX_LINKS_SIMBOLICOS)

    def mkdir(self, processo, caminho):
        pai, nome = self._pai_e_nome(caminho)
        if nome in pai.entradas:
            raise ErroSA("EEXIST", caminho)
        fcb = self._novo_fcb(nome, "diretorio", pai.id, processo)
        try:
            extras = self.alocador.alocar(fcb, 1)
        except ErroSA:
            del self.fcbs[fcb.id]
            raise
        self._aplicar(extras)
        pai.entradas[nome] = fcb.id
        self._gravar_diretorio(fcb)
        self._gravar_diretorio(pai)
        return fcb

    def create(self, processo, caminho, tamanho):
        if tamanho < 0:
            raise ErroSA("EINVAL", "tamanho negativo")
        pai, nome = self._pai_e_nome(caminho)
        if nome in pai.entradas:
            raise ErroSA("EEXIST", caminho)
        fcb = self._novo_fcb(nome, "arquivo", pai.id, processo)
        fcb.tamanho = tamanho
        try:
            extras = self.alocador.alocar(fcb, self._blocos_necessarios(tamanho))
        except ErroSA:
            del self.fcbs[fcb.id]
            raise
        self._aplicar(extras)
        pai.entradas[nome] = fcb.id
        self._gravar_diretorio(pai)
        return fcb

    def open(self, processo, caminho, modo, handle):
        if modo not in ("r", "w", "rw", "a"):
            raise ErroSA("EINVAL", "modo inválido: %s" % modo)
        fcb = self.resolver(caminho)
        if fcb.tipo == "diretorio":
            raise ErroSA("EISDIR", caminho)
        self._verificar_permissao(processo, fcb, modo)

        tabela = self.tabelas_processo.setdefault(processo, {})
        if handle in tabela:
            raise ErroSA("EBADF", "handle já aberto: %s" % handle)

        entrada = self.tabela_global.get(fcb.id)
        if entrada is None:
            entrada = EntradaGlobal(fcb.id)
            self.tabela_global[fcb.id] = entrada
        entrada.contador += 1

        posicao = fcb.tamanho if modo == "a" else 0
        tabela[handle] = EntradaProcesso(fcb.id, modo, posicao)
        return fcb

    def read(self, processo, handle, n):
        entrada = self._entrada(processo, handle)
        if "r" not in entrada.modo:
            raise ErroSA("EBADF", "handle %s não permite leitura" % handle)
        if n < 0:
            raise ErroSA("EINVAL", "n negativo")
        fcb = self.fcbs.get(entrada.fcb_id)
        if fcb is None:
            raise ErroSA("EBADF", "arquivo fechado")
        self._verificar_trava(processo, fcb)

        inicio = entrada.posicao
        fim = min(inicio + n, fcb.tamanho)
        if fim <= inicio:
            return 0
        self._ler(self._blocos_do_intervalo(fcb, inicio, fim))
        entrada.posicao = fim
        return fim - inicio

    def write(self, processo, handle, n):
        entrada = self._entrada(processo, handle)
        if "w" not in entrada.modo and "a" not in entrada.modo:
            raise ErroSA("EBADF", "handle %s não permite escrita" % handle)
        if n < 0:
            raise ErroSA("EINVAL", "n negativo")
        fcb = self.fcbs.get(entrada.fcb_id)
        if fcb is None:
            raise ErroSA("EBADF", "arquivo fechado")
        self._verificar_trava(processo, fcb)

        if "a" in entrada.modo:
            entrada.posicao = fcb.tamanho
        inicio = entrada.posicao
        if n == 0:
            return 0
        fim = inicio + n
        if fim > fcb.tamanho:
            faltam = self._blocos_necessarios(fim) - len(fcb.blocos)
            if faltam > 0:
                self._aplicar(self.alocador.estender(fcb, faltam))
            fcb.tamanho = fim

        self._escrever(self._blocos_do_intervalo(fcb, inicio, fim))
        fcb.modificado_ms = self.agora_ms
        fcb.sujo = True
        entrada.posicao = fim
        return n

    def seek(self, processo, handle, posicao):
        entrada = self._entrada(processo, handle)
        if posicao < 0:
            raise ErroSA("EINVAL", "posição negativa")
        entrada.posicao = posicao
        return posicao

    def close(self, processo, handle):
        entrada = self._entrada(processo, handle)
        tabela = self.tabelas_processo[processo]
        del tabela[handle]
        if not tabela:
            del self.tabelas_processo[processo]

        fcb = self.fcbs.get(entrada.fcb_id)
        if fcb is None:
            return

        if fcb.sujo:
            if fcb.pai is not None and fcb.pai in self.fcbs:
                self._gravar_diretorio(self.fcbs[fcb.pai])
            fcb.sujo = False

        global_ = self.tabela_global.get(fcb.id)
        if global_ is not None:
            global_.contador -= 1
            if global_.contador <= 0:
                del self.tabela_global[fcb.id]

        if fcb.links <= 0 and fcb.id not in self.tabela_global:
            self._liberar_arquivo(fcb)

    def unlink(self, processo, caminho):
        pai, nome = self._pai_e_nome(caminho)
        fid = pai.entradas.get(nome)
        if fid is None:
            raise ErroSA("ENOENT", caminho)
        fcb = self.fcbs[fid]
        if fcb.tipo == "diretorio":
            raise ErroSA("EISDIR", caminho)

        del pai.entradas[nome]
        self._gravar_diretorio(pai)

        fcb.links -= 1
        if fcb.links <= 0 and fcb.id not in self.tabela_global:
            self._liberar_arquivo(fcb)

    # ======================================================== TODO — módulo M4
    def link(self, processo, existente, novo):
        """Hard link: lê os diretórios até `existente` (como resolver) e até o pai de `novo`;
        cria a entrada; links += 1; grava o bloco do pai de `novo` (1 escrita).
        Hard link para diretório: ErroSA('EPERM')."""
        raise NotImplementedError("TODO (M4): link")

    def symlink(self, processo, alvo, caminho):
        """Link simbólico: lê os diretórios até o pai de `caminho`; cria um FCB do tipo
        'simbolico' com fcb.alvo = alvo (sem blocos de dados); grava o bloco do pai (1 escrita).
        O alvo não precisa existir."""
        raise NotImplementedError("TODO (M4): symlink")

    def percorrer(self, processo, caminho):
        """Percorre a árvore a partir de `caminho` (como um `find`), lendo cada diretório
        visitado (1 leitura) e seguindo links simbólicos para diretórios. Não pode entrar em
        laço: ao chegar de novo a um diretório já visitado nesta travessia, conte
        self.contadores['ciclos_detectados'] e não desça. Contem também
        'percorrer_diretorios', 'percorrer_arquivos' e 'links_pendentes' (links simbólicos
        cujo alvo não existe; contem também os encontrados pelo open)."""
        raise NotImplementedError("TODO (M4): percorrer")

    # ======================================================== TODO — módulo M5
    # Regras do M5 (implementem também os ganchos _verificar_permissao e _verificar_trava,
    # sobrescrevendo-os aqui ou numa subclasse):
    #
    # _verificar_permissao(processo, fcb, modo) — chamado no open. Permissão exigida:
    #   'r' para o modo 'r'; 'w' para 'w' e 'a'; 'r' e 'w' para 'rw'.
    #   - usuário root: sempre permitido (conte 1 em contadores['verificacoes']);
    #   - se a ACL do arquivo tem uma entrada para o usuário, vale a PRIMEIRA entrada dele
    #     (some em 'verificacoes' a posição da entrada na lista, começando em 1);
    #   - senão, valem os bits: os do dono, se o usuário for o dono; senão, os de "outros"
    #     (grupos não são simulados). Some len(acl) + 1 em 'verificacoes';
    #   - negado: some 1 em contadores['negados'] e lance ErroSA('EACCES').
    #
    # _verificar_trava(processo, fcb) — chamado no read e no write. Se outro processo
    #   detém a trava do arquivo:
    #   - bloqueio 'consultivo': a operação segue; some 1 em 'violacoes_consultivo';
    #   - bloqueio 'mandatorio': some 1 em 'bloqueados_mandatorio' e lance ErroSA('EBUSY').
    # O close libera a trava se o processo que fecha for o dono dela.
    def usuario(self, processo, nome):
        """Associa o processo a um usuário (nenhum acesso ao disco)."""
        raise NotImplementedError("TODO (M5): usuario")

    def chmod(self, processo, caminho, permissoes):
        """Lê os diretórios até o arquivo; só o dono ou root (senão EPERM); grava o bloco do
        pai (1 escrita). permissoes em octal, como texto (ex.: '640')."""
        raise NotImplementedError("TODO (M5): chmod")

    def setacl(self, processo, caminho, usuario, permissoes):
        """Como o chmod, mas acrescenta (ou substitui) a entrada (usuario, 'rwx') na ACL."""
        raise NotImplementedError("TODO (M5): setacl")

    def lock(self, processo, handle):
        """Trava exclusiva do arquivo inteiro. Se outro processo detém a trava: EBUSY
        (conte 'travas_negadas'); senão conte 'travas_concedidas'."""
        raise NotImplementedError("TODO (M5): lock")

    def unlock(self, processo, handle):
        raise NotImplementedError("TODO (M5): unlock")
