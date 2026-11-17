# -*- coding: utf-8 -*-
"""
Módulo M1 — cache de blocos (buffer cache).

Referência: Silberschatz, 9ª ed., 13.4.3 (Caching) e 12.6 (Efficiency and Performance) — pesquisa.

Implementem CacheLRU e CacheFIFO com a interface abaixo. O simulador de E/S chama:

    ler(bloco) -> bool
        True se o bloco está na cache (acerto). Num acerto, a LRU atualiza a recência;
        a FIFO não muda nada.
    inserir(bloco) -> list[int]
        Chamado depois de uma falta de leitura, quando o bloco chega do disco. Se a cache
        estiver cheia, expulsa uma vítima (LRU: a usada há mais tempo; FIFO: a que entrou
        primeiro). Devolve os blocos SUJOS expulsos, que o simulador vai gravar no disco.
    escrever(bloco) -> list[int]
        Escrita do usuário. Coloca (ou atualiza) o bloco na cache e devolve a lista de blocos
        que precisam ser gravados no disco AGORA:
          write-through: o próprio bloco (+ sujos expulsos, que não existem nesta política);
          write-back:    só os blocos sujos expulsos; o bloco escrito fica marcado como sujo.
        Uma escrita conta como acesso para a LRU.
    sincronizar() -> list[int]
        Gravação periódica (a cada INTERVALO_SYNC_MS): devolve todos os blocos sujos e os
        marca como limpos.
    sujos() -> int
        Quantos blocos estão sujos agora (usado para medir a perda numa queda de energia).

Política de escrita: 'write-through' ou 'write-back'.
"""
from collections import OrderedDict


class Cache:
    nome = "?"

    def __init__(self, capacidade, escrita="write-back"):
        if escrita not in ("write-through", "write-back"):
            raise ValueError("escrita deve ser 'write-through' ou 'write-back'")
        if capacidade < 1:
            raise ValueError("a capacidade da cache deve ser positiva")
        self.capacidade = capacidade
        self.escrita = escrita
        self._ordem = OrderedDict()     # bloco -> None, do menos para o mais recente
        self._sujos = set()

    def _tocar(self, bloco):
        """Atualiza a recência. A FIFO não reordena; a LRU move para o fim."""
        return None

    def ler(self, bloco):
        if bloco in self._ordem:
            self._tocar(bloco)
            return True
        return False

    def inserir(self, bloco):
        if bloco in self._ordem:
            self._tocar(bloco)
            return []
        expulsos = []
        while len(self._ordem) >= self.capacidade:
            vitima, _ = self._ordem.popitem(last=False)
            if vitima in self._sujos:
                self._sujos.discard(vitima)
                expulsos.append(vitima)
        self._ordem[bloco] = None
        return expulsos

    def escrever(self, bloco):
        if self.escrita == "write-through":
            expulsos = self.inserir(bloco)
            self._sujos.discard(bloco)
            return [bloco] + expulsos
        expulsos = self.inserir(bloco)
        self._sujos.add(bloco)
        return expulsos

    def sincronizar(self):
        blocos = [b for b in self._ordem if b in self._sujos]
        self._sujos.clear()
        return blocos

    def sujos(self):
        return len(self._sujos)


class CacheLRU(Cache):
    nome = "LRU"

    def __init__(self, capacidade, escrita="write-back"):
        super().__init__(capacidade, escrita)

    def _tocar(self, bloco):
        self._ordem.move_to_end(bloco)


class CacheFIFO(Cache):
    nome = "FIFO"

    def __init__(self, capacidade, escrita="write-back"):
        super().__init__(capacidade, escrita)


CACHES = {"LRU": CacheLRU, "FIFO": CacheFIFO}


def criar_cache(nome, capacidade, escrita):
    try:
        return CACHES[nome](capacidade, escrita)
    except KeyError:
        raise ValueError("cache desconhecida: %s" % nome)
