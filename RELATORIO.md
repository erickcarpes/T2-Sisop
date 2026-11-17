# Relatório — SimES: simulador de E/S e de sistema de arquivos

**Integrantes:** Augusto Ely Missiaggia, Erick Marcondes de Mattos Carpes

**Repositório:** https://github.com/erickcarpes/T2-Sisop

## 0. Resumo

O grupo implementou o núcleo do SimES — escalonadores SSTF e SCAN, custos de CPU em polling e
interrupção (N2) e o sistema de arquivos com resolução de caminhos, tabelas de arquivos abertos,
leitura, escrita, extensão, seek, close e unlink (N3) — e o módulo M1, com caches de blocos LRU e
FIFO e políticas write-through e write-back. O escopo é de dupla, portanto o trabalho cobre o
núcleo e um módulo; a integração X12 e o bônus de flash não fazem parte da entrega. Os
experimentos X1 a X6 foram executados e os resultados estão consolidados na seção 3. Os três
resultados mais relevantes são: (i) o SSTF reduziu o deslocamento total em até 93,7% e o tempo
médio de resposta em até 99,8% em relação ao FCFS; (ii) a interrupção baixou o uso de CPU de E/S
no HDD de 86,3–100,0% (polling) para 0,8–1,1%; (iii) a cache M1 elevou o acerto de 31,3% (FIFO,
64 blocos) para 67,1% (LRU/FIFO, 1024+ blocos), com write-back gravando 541–810 blocos contra
1045 do write-through, mas perdendo 22–55 blocos sujos na queda simulada.

## 1. Escopo realizado

| Parte | Situação | Observação |
|---|---|---|
| N1 · Dispositivo (fornecido) | usado | `DiscoHDD` fornecido, sem alterações |
| N2 · Subsistema de E/S (SSTF, SCAN, polling, interrupção) | completo | `simes/es/escalonadores.py` e `simes/es/cpu.py` |
| N3 · Sistema de arquivos | completo | `simes/arquivos/sistema.py` |
| N4 · Experimentos X1–X5 e relatório | completo | X1–X5 executados; resultados e gráficos gerados |
| M1 · Cache de blocos | completo | `simes/es/cache.py` (LRU/FIFO, write-through/write-back) |
| Integração (grupos de 4) | não se aplica | dupla |
| Bônus flash | não feito | fora do escopo da dupla |

Resultado dos testes automáticos (`python3 executar.py testes`): `Ran 26 tests in 0.007s — OK (skipped=7)`.

## 2. Implementação

### N2 — Subsistema de E/S

**Onde:** `simes/es/escalonadores.py` (`SSTF.escolher`, `SCAN.escolher`) e `simes/es/cpu.py`
(`custo_cpu`).

**Decisões:** o SSTF escolhe a requisição de menor distância até a cabeça, desempatando pela
ordem de chegada, e devolve como nova direção o sentido do movimento (mantendo a direção atual
quando o alvo está no mesmo cilindro). O SCAN considera "à frente" toda requisição no sentido
atual, incluindo a do mesmo cilindro; escolhe a mais próxima e, quando não há nenhuma à frente,
usa `passar_por` para levar o braço até a borda (cilindro 0 ou `max_cilindro`), inverte a direção
e atende a mais próxima na volta. O polling consome o tempo integral de atendimento; a
interrupção custa `n_blocos * (CUSTO_INTERRUPCAO_MS + CUSTO_COPIA_MS_POR_BLOCO)`.

**Dificuldades:** acertar a contabilidade do deslocamento do SCAN — a ida até a borda precisa
entrar em `passar_por` sem virar uma requisição atendida — e respeitar o desempate pela ordem de
chegada em todas as escolhas.

### N3 — Sistema de arquivos

**Onde:** `simes/arquivos/sistema.py` (`_resolver`, `_pai_e_nome`, `resolver`, `mkdir`, `create`,
`open`, `read`, `write`, `seek`, `close`, `unlink`).

**Decisões:** a resolução lê cada diretório do caminho, exatamente como as regras de custo, e
segue links simbólicos no meio do caminho (e no último componente quando solicitado), com limite
`MAX_LINKS_SIMBOLICOS` para detectar `ELOOP`. As operações de criação e remoção resolvem o pai,
leem o diretório pai e gravam seu bloco. `open` compartilha uma `EntradaGlobal` por FCB e cria uma
`EntradaProcesso` por abertura, com posição e modo independentes. `write` estende o arquivo pelo
alocador quando necessário, grava somente os blocos do intervalo e marca o FCB como sujo; `close`
grava o diretório pai se o FCB estiver sujo. `unlink` remove a entrada, decrementa `links` e só
libera os blocos quando não há mais links nem arquivos abertos; se o arquivo estiver aberto, a
liberação ocorre no último `close`.

**Dificuldades:** manter a contagem exata de acessos (leituras e escritas) exigida pelos testes e
tratar o caso de `unlink` com arquivo aberto sem apagar os blocos cedo demais.

### M1 — Cache de blocos

**Onde:** `simes/es/cache.py` (`Cache`, `CacheLRU`, `CacheFIFO`).

**Decisões:** a ordem dos blocos é mantida em um `OrderedDict`; a LRU move o bloco para o fim em
cada acesso (leitura ou escrita), enquanto a FIFO preserva a ordem de inserção. Na falta, a
vítima é a primeira da ordem e, se estiver suja, é devolvida para gravação. Em write-through, a
escrita devolve o próprio bloco para o disco; em write-back, o bloco fica sujo e só é gravado na
expulsão ou em `sincronizar()`, que devolve todos os sujos e os marca como limpos.

**Dificuldades:** garantir que a expulsão de um bloco sujo devolva exatamente a lista de blocos a
gravar e que `sujos()` reflita o estado no instante de uma queda de energia.

## 3. Experimentos

### X1 — Escalonadores sob quatro padrões de carga

**Hipótese:** SSTF e SCAN reduzem o deslocamento total e o tempo médio de resposta em relação ao
FCFS nas cargas aleatória, concentrada e em rajadas; na carga sequencial a diferença é pequena,
porque o FCFS já atende na ordem de chegada e o padrão é quase sequencial. O SCAN pode aumentar a
espera máxima de algumas requisições ao ir até a borda, trocando média por previsibilidade.

**Fundamentação:** Silberschatz, 9ª ed., seção 10.4 (Disk Scheduling): FCFS é justo, mas provoca
grandes deslocamentos; SSTF minimiza a busca por requisição e pode causar inanição; SCAN funciona
como elevador e limita a inanição, ao custo de visitar as bordas.

**Configuração:** cargas `es_sequencial`, `es_aleatoria`, `es_concentrada` e `es_rajadas`; para
cada uma, FCFS, SSTF e SCAN em `DiscoHDD`, modo interrupção. Mede-se deslocamento total, tempo
total, resposta média, resposta p95, espera máxima e vazão.

**Resultados:**

| Carga | Escalonador | Deslocamento total | Resposta média (ms) | Resposta p95 (ms) | Espera máxima (ms) | Vazão (req/s) |
|---|---:|---:|---:|---:|---:|---:|
| sequencial | FCFS | 7.184.093 | 10.241,05 | 19.565,45 | 20.598,06 | 61,48 |
| sequencial | SSTF | 2.336.365 | 17,39 | 32,79 | 37,44 | 167,49 |
| sequencial | SCAN | 2.469.069 | 23,21 | 43,65 | 48,59 | 167,41 |
| aleatória | FCFS | 3.316.472 | 50,10 | 145,09 | 193,52 | 82,45 |
| aleatória | SSTF | 2.631.714 | 20,99 | 48,61 | 116,65 | 82,45 |
| aleatória | SCAN | 3.372.680 | 31,53 | 65,06 | 116,73 | 82,36 |
| concentrada | FCFS | 1.864.164 | 19,80 | 48,57 | 96,02 | 83,81 |
| concentrada | SSTF | 1.613.030 | 15,02 | 37,20 | 130,52 | 83,81 |
| concentrada | SCAN | 3.338.708 | 33,20 | 68,33 | 118,75 | 83,70 |
| rajadas | FCFS | 3.341.490 | 266,97 | 505,32 | 597,29 | 83,46 |
| rajadas | SSTF | 209.811 | 147,49 | 277,72 | 296,99 | 84,42 |
| rajadas | SCAN | 199.955 | 148,62 | 278,70 | 285,44 | 84,43 |

**Evidências:** `resultados/es.csv` (experimento=X1); `graficos/X1_resposta_media_ms.png`; `graficos/X1_deslocamento_total.png`; `graficos/X1_espera_max_ms.png`.

**Análise:** o SSTF foi o melhor em resposta média nas quatro cargas: reduziu o deslocamento em
67,5% (sequencial), 20,7% (aleatória), 13,5% (concentrada) e 93,7% (rajadas) em relação ao FCFS,
e cortou a resposta média em 99,8%, 58,1%, 24,1% e 44,8%, respectivamente. O SCAN também venceu o
FCFS em resposta média nas cargas sequencial (99,8%), aleatória (37,1%) e rajadas (44,3%), mas foi
pior na concentrada (+67,7%) e aumentou o deslocamento em 1,7% (aleatória) e 79,1% (concentrada),
porque vai até a borda mesmo quando a carga está concentrada em uma região quente. Na carga
sequencial, ao contrário do que a hipótese previa, a diferença foi enorme: os dois processos
varrem regiões distantes do disco alternadamente, e o FCFS paga um deslocamento de mais de 7
milhões de cilindros. A espera máxima do SCAN foi menor que a do FCFS em três cargas, mas ficou
23,7% maior na concentrada; o SSTF elevou a espera máxima em 35,9% nessa mesma carga, evidência
da inanição possível no SSTF. A hipótese é, portanto, parcialmente confirmada: o ganho médio do
SSTF é consistente, mas o SCAN não é universalmente melhor que o FCFS, e a carga sequencial não
foi o caso de diferença pequena.

**Veredito:** PARCIALMENTE CONFIRMADA

### X2 — Polling × interrupção conforme o dispositivo

**Hipótese:** no disco rígido, a interrupção reduz drasticamente o percentual de CPU de E/S em
relação ao polling, porque a CPU deixa de esperar o tempo mecânico de busca e rotação. No
dispositivo rápido, a diferença diminui e, para requisições pequenas, o polling pode ficar
próximo da interrupção, pois o custo fixo de tratar interrupções passa a pesar.

**Fundamentação:** Silberschatz, 9ª ed., seções 13.2.1 e 13.2.2: no polling a CPU fica em espera
ocupada; com interrupção, a controladora avisa a CPU a cada bloco, liberando-a durante a espera.

**Configuração:** cargas `es_aleatoria` e `es_sequencial` em `hdd` e `rapido`, com FCFS, nos modos
polling e interrupção. Mede-se `cpu_es_pct`, tempo total e resposta média.

**Resultados:**

| Dispositivo | Carga | Modo | CPU de E/S (%) | Tempo total (ms) | Resposta média (ms) |
|---|---|---|---:|---:|---:|
| HDD | aleatória | polling | 86,2832 | 24.256,65 | 50,1041 |
| HDD | aleatória | interrupção | 1,1213 | 24.256,65 | 50,1041 |
| HDD | sequencial | polling | 99,9977 | 32.533,04 | 10.241,0482 |
| HDD | sequencial | interrupção | 0,8361 | 32.533,04 | 10.241,0482 |
| rápido | aleatória | polling | 0,5280 | 24.244,38 | 0,0642 |
| rápido | aleatória | interrupção | 1,1219 | 24.244,38 | 0,0642 |
| rápido | sequencial | polling | 1,0739 | 11.918,78 | 0,0643 |
| rápido | sequencial | interrupção | 2,2821 | 11.918,78 | 0,0643 |

**Evidências:** `resultados/es.csv` (experimento=X2); `graficos/X2_cpu.png`.

**Análise:** no HDD, o polling manteve a CPU ocupada em 86,3% (aleatória) e 100,0% (sequencial)
do tempo, enquanto a interrupção reduziu esse uso para 1,12% e 0,84% — uma queda de 98,7% e
99,2%, exatamente porque a CPU deixa de girar durante a busca e a rotação. No dispositivo rápido,
o polling passou a ser mais econômico que a interrupção (0,53% contra 1,12% na aleatória; 1,07%
contra 2,28% na sequencial): como cada atendimento dura poucos microssegundos, o custo fixo de
0,017 ms por bloco para tratar a interrupção domina. Os tempos totais e as respostas médias são
idênticos entre os modos porque o simulador contabiliza a CPU separadamente e não a usa para
atrasar a fila do disco; essa é uma limitação do modelo, não um resultado de desempenho. A
hipótese é confirmada: a interrupção é essencial no HDD e o polling ainda é competitivo (aqui, até
melhor) no dispositivo rápido.

**Veredito:** CONFIRMADA

### X3 — Acesso sequencial × direto

**Hipótese:** a carga do compilador, com leituras sequenciais de arquivos, produz menos
deslocamento por acesso e menor tempo médio por operação que a carga do banco de dados, que faz
buscas diretas em posições aleatórias de uma tabela grande. O ganho vem da rotação e da busca
economizadas quando os blocos são consecutivos.

**Fundamentação:** Silberschatz, 9ª ed., seções 11.2 e 12.2: acesso sequencial permite agrupar
blocos e evitar latência rotacional; acesso direto exige calcular e buscar cada bloco.

**Configuração:** cargas `fs_compilador` e `fs_banco_dados` com alocação contígua. Mede-se
acessos por operação, tempo médio por operação, tempo total e descontinuidades médias.

**Resultados:**

| Carga | Operações | Acessos | Acessos/op | Tempo total (ms) | Tempo médio/op (ms) | Leitura média (ms) | Escrita média (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| compilador | 3.904 | 5.400 | 1,3832 | 11.986,65 | 3,0704 | 1,4828 | 0,9068 |
| banco_dados | 6.602 | 3.610 | 0,5468 | 19.846,96 | 3,0062 | 5,4918 | 5,5425 |

Ambas as cargas terminaram com `descontinuidades_medias=0`, `realocacoes=0` e
`falhas_alocacao=0`; os 64 MiB da tabela do banco couberam em um único trecho contíguo.

**Evidências:** `resultados/arquivos.csv` (experimento=X3); `resultados/arquivos_por_operacao.csv`; `graficos/X3_tempo_por_operacao.png`.

**Análise:** a hipótese literal não se sustentou na média por operação: o compilador teve 1,3832
acesso por operação contra 0,5468 do banco, e tempo médio de 3,0704 ms contra 3,0062 ms. Isso
acontece porque as duas cargas têm misturas de operações muito diferentes: o compilador faz 600
`open`, 175 `create`, 80 `unlink` e 726 `write` (muitos acessos de metadados), enquanto o banco
executa 3.000 `seek` de custo zero e apenas 2 `open`/2 `create`, diluindo a média. Quando se
compara o custo de um acesso de dados, porém, a localidade sequencial aparece com clareza: a
leitura média do compilador custou 1,4828 ms contra 5,4918 ms do banco (3,7× mais caro), e a
escrita média 0,9068 ms contra 5,5425 ms (6,1×). O acesso direto do banco paga busca e latência
rotacional a cada posição aleatória; o compilador lê blocos consecutivos, que a camada agrupa.
Assim, a parte da hipótese sobre o custo por acesso é confirmada, mas a comparação por operação
é refutada pela diferença de composição das cargas.

**Veredito:** PARCIALMENTE CONFIRMADA

### X4 — Custo de resolver caminhos conforme a profundidade

**Hipótese:** o custo do `open` cresce linearmente com a profundidade do caminho: cada diretório
adicional exige uma leitura a mais para ser resolvido. O tempo médio do `open` deve acompanhar
essa contagem, com patamares claros a cada nível.

**Fundamentação:** Silberschatz, 9ª ed., seção 11.3: a resolução de nomes percorre os diretórios
do caminho; caches de diretório (dentry cache) existem justamente para evitar essas leituras.

**Configuração:** `fs_profundidade(d)` para `d` de 1 a 10, com alocação contígua; mede-se
acessos por `open` e tempo médio de `open` em função da profundidade.

**Resultados:**

| Profundidade | Acessos por `open` | Tempo médio do `open` (ms) | Acessos/op no experimento |
|---:|---:|---:|---:|
| 1 | 2 | 4,2500 | 1,0645 |
| 2 | 3 | 4,2900 | 1,4444 |
| 3 | 4 | 4,3300 | 1,8281 |
| 4 | 5 | 4,3700 | 2,2154 |
| 5 | 6 | 4,4100 | 2,6061 |
| 6 | 7 | 4,4500 | 3,0000 |
| 7 | 8 | 4,4900 | 3,3971 |
| 8 | 9 | 4,5300 | 3,7971 |
| 9 | 10 | 4,5700 | 4,2000 |
| 10 | 11 | 4,6100 | 4,6056 |

**Evidências:** `resultados/arquivos_por_operacao.csv` (experimento=X4); `graficos/X4_open_por_profundidade.png`.

**Análise:** a contagem cresce exatamente de 1 acesso por nível: profundidade 1 custa 2 leituras
(raiz e o diretório `/n1`) e profundidade 10 custa 11. O tempo médio do `open` acompanha a
contagem de forma praticamente linear, de 4,25 ms a 4,61 ms, com incremento de 0,04 ms por nível
— o custo de uma leitura de bloco de diretório no HDD. Não há desvios: o ajuste é linear e
confirma que, sem cache de diretórios, cada componente do caminho custa uma leitura. O aumento de
acessos por operação no experimento também inclui `mkdir` e `create`, que pagam a profundidade do
pai.

**Veredito:** CONFIRMADA

### X5 — Tabelas de arquivos abertos com vários processos

**Hipótese:** quando vários processos abrem os mesmos arquivos, a tabela global cresce com o
número de arquivos distintos, não com o número de aberturas; cada processo mantém sua própria
entrada e posição. O contador de aberturas da entrada global deve chegar ao número de aberturas
simultâneas, e a soma das tabelas dos processos deve ser maior que a tabela global.

**Fundamentação:** Silberschatz, 9ª ed., seção 11.3: a tabela global tem uma entrada por arquivo
aberto; a tabela por processo tem uma entrada por abertura, com o ponteiro de posição.

**Configuração:** carga `fs_servidor_web` (vários processos abrindo as mesmas páginas), alocação
contígua. Mede-se `max_tabela_global`, `max_tabela_processo`, `max_soma_tabelas_processo` e
`max_contador_aberturas`.

**Resultados:**

| Operações | Acessos | Acessos/op | Tempo total (ms) | Tempo médio/op (ms) | Máx. tabela global | Máx. tabela por processo | Máx. soma das tabelas | Máx. contador de aberturas |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 6.279 | 17.824 | 2,8387 | 9.354,08 | 1,4897 | 12 | 3 | 24 | 6 |

**Evidências:** `resultados/arquivos.csv` (experimento=X5); `graficos/X5_tabelas.png`.

**Análise:** a carga tem 8 trabalhadores e 12 páginas distintas; cada trabalhador abre 3 páginas
por rodada. O máximo de 24 entradas na soma das tabelas por processo corresponde exatamente a
8 × 3 aberturas simultâneas, enquanto a tabela global ficou em 12 — uma entrada por arquivo
distinto, não por abertura. O maior contador de aberturas observado foi 6: uma mesma página chegou
a ser aberta simultaneamente por 6 dos 8 processos, menos que 8 porque as escolhas de 3 páginas
por trabalhador são amostras aleatórias e nem todos coincidem na mesma página. A tabela global
ser menor que a soma das tabelas por processo confirma o compartilhamento previsto.

**Veredito:** CONFIRMADA

### X6 — Cache de blocos (M1)

**Hipótese:** na carga de reuso (distribuição de Zipf), a LRU supera a FIFO porque preserva os
blocos mais acessados; aumentar a capacidade eleva o acerto até saturar. Write-back reduz as
escritas físicas em relação a write-through, mas perde blocos sujos em uma queda de energia,
enquanto write-through perde menos dados ao custo de mais gravações.

**Fundamentação:** Silberschatz, 9ª ed., seções 13.4.3 e 12.6: a cache explora localidade; LRU
aproxima o comportamento ótimo de reuso; write-back adia gravações e write-through as faz
imediatamente.

**Configuração:** carga `es_reuso`, FCFS, HDD, interrupção; LRU e FIFO com capacidades de 64 a
2048 blocos, em write-through e write-back, com uma queda simulada no meio da carga. Mede-se
acerto, escritas físicas e blocos perdidos.

**Resultados:**

Sem cache, a carga teve 1.045 escritas físicas, nenhum bloco perdido, deslocamento total de
5.073.258 cilindros e resposta média de 3.499,95 ms. Com cache:

| Cache | Política | Cap. | Acerto (%) | Escritas físicas | Perdidos na queda | Resposta média (ms) | Espera máx. (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| LRU | write-through | 64 | 39,6419 | 1.045 | 0 | 74,6575 | 257,8140 |
| LRU | write-through | 128 | 48,8491 | 1.045 | 0 | 33,3670 | 157,9510 |
| LRU | write-through | 256 | 57,7494 | 1.045 | 0 | 22,0498 | 151,7850 |
| LRU | write-through | 512 | 64,1944 | 1.045 | 0 | 18,1710 | 151,7850 |
| LRU | write-through | 1024 | 67,0588 | 1.045 | 0 | 16,8856 | 151,7850 |
| LRU | write-through | 2048 | 67,0588 | 1.045 | 0 | 16,8856 | 151,7850 |
| LRU | write-back | 64 | 39,6419 | 715 | 28 | 23,3622 | 418,4060 |
| LRU | write-back | 128 | 49,1049 | 630 | 51 | 26,2435 | 690,2350 |
| LRU | write-back | 256 | 57,6982 | 543 | 55 | 47,6329 | 1.271,0760 |
| LRU | write-back | 512 | 64,2455 | 541 | 55 | 45,4100 | 1.416,8140 |
| LRU | write-back | 1024 | 67,0077 | 541 | 55 | 38,9341 | 1.416,8140 |
| LRU | write-back | 2048 | 67,0077 | 541 | 55 | 38,9341 | 1.416,8140 |
| FIFO | write-through | 64 | 31,3043 | 1.045 | 0 | 436,1072 | 885,4790 |
| FIFO | write-through | 128 | 42,5575 | 1.045 | 0 | 51,7309 | 247,6360 |
| FIFO | write-through | 256 | 53,1969 | 1.045 | 0 | 25,8611 | 151,7850 |
| FIFO | write-through | 512 | 60,5627 | 1.045 | 0 | 20,5442 | 151,7850 |
| FIFO | write-through | 1024 | 67,0588 | 1.045 | 0 | 16,8856 | 151,7850 |
| FIFO | write-through | 2048 | 67,0588 | 1.045 | 0 | 16,8856 | 151,7850 |
| FIFO | write-back | 64 | 33,0946 | 810 | 22 | 46,2735 | 465,1070 |
| FIFO | write-back | 128 | 43,8875 | 706 | 46 | 29,8998 | 588,1970 |
| FIFO | write-back | 256 | 53,2992 | 607 | 50 | 46,3488 | 1.144,4310 |
| FIFO | write-back | 512 | 60,1023 | 567 | 50 | 47,1745 | 1.357,3300 |
| FIFO | write-back | 1024 | 67,0077 | 541 | 55 | 39,7302 | 1.425,7030 |
| FIFO | write-back | 2048 | 67,0077 | 541 | 55 | 39,7302 | 1.425,7030 |

**Evidências:** `resultados/es.csv` (experimento=X6); `graficos/X6_acerto.png`; `graficos/X6_escrita.png`.

**Análise:** a LRU superou a FIFO em todas as capacidades abaixo da saturação — a 64 blocos, o
acerto foi 39,64% contra 31,30% (write-through) e 39,64% contra 33,09% (write-back); a 512 blocos,
64,19% contra 60,56% e 64,25% contra 60,10%. A partir de 1.024 blocos as duas convergem para
67,06%, porque o conjunto de trabalho quente já cabe na cache e a política de substituição deixa
de importar. Aumentar a capacidade eleva o acerto com retornos decrescentes (39,6% → 48,8% →
57,7% → 64,2% → 67,1%), saturando em 1.024 blocos. O write-through manteve exatamente 1.045
escritas físicas e zero perdas em todas as capacidades; o write-back reduziu para 541–810
escritas, mas perdeu de 22 a 55 blocos sujos na queda simulada, confirmando o trade-off. O
write-back também piorou a cauda: a espera máxima chegou a 1.416,8 ms (LRU) e 1.425,7 ms (FIFO),
contra 151,8 ms do write-through, por causa das rajadas de gravação de blocos sujos expulsos ou
sincronizados. Em capacidades pequenas (64 blocos), o write-back ainda melhorou a resposta média
(23,36 ms contra 74,66 ms na LRU), mas em 1.024 blocos ficou pior (38,93 ms contra 16,89 ms),
pois a evacuação de um conjunto grande de blocos sujos em um único instante atrasa as leituras.

**Veredito:** CONFIRMADA

## 4. Relação com sistemas reais

O escalonamento de E/S do Linux usa, entre outros, `mq-deadline`, `BFQ` e `none`; o primeiro
combina prazos para leituras e escritas com ordenação por setor, ideia próxima do DEADLINE
opcional. O Windows e o macOS mantêm caches de páginas e gravam dados sujos periodicamente, como
o write-back simulado; o `fsync` força a gravação, análoga a `sincronizar()`. Caches de
diretórios (dentry cache no Linux) evitam reler diretórios a cada resolução de caminho, o que
explica o custo linear observado em X4. FAT/exFAT usam tabela de alocação como a FAT; ext4, NTFS
e APFS usam estruturas indexadas e bitmaps/extents para o espaço livre. Quanto à proteção, o
Windows oferece travas mandatórias, enquanto o Linux usa travas consultivas (`flock`/`fcntl`), e
as ACLs POSIX generalizam os bits rwx. Por fim, SSDs usam FTL, coleta de lixo e amplificação de
escrita, o que motivaria o bônus de flash.

## 5. Limitações do simulador

O modelo usa um único disco, sem paralelismo entre requisições, e tempos determinísticos de busca,
rotação e transferência; não há fila de controladora, remapeamento de setores defeituosos nem
variação de latência. O sistema de arquivos é single-threaded: as operações são executadas em
ordem, sem concorrência real entre processos, e as tabelas servem para medir o compartilhamento,
não para simular corridas. A cache é totalmente associativa e com capacidade fixa em blocos, sem
prefetch nem políticas adaptativas. A alocação contígua usa first-fit e pode sofrer fragmentação
externa, enquanto os demais alocadores são opcionais. Essas simplificações tornam os números
comparáveis entre grupos, mas não devem ser lidos como desempenho absoluto de um sistema real.

## 6. Conclusões

1. O SSTF foi o escalonador de melhor resposta média nas quatro cargas, com redução de
deslocamento entre 13,5% (concentrada) e 93,7% (rajadas) sobre o FCFS; o SCAN só foi melhor que o
FCFS nas cargas sequencial, aleatória e em rajadas, e perdeu na concentrada, em que ir até a
borda anula o ganho de localidade.
2. O SSTF pode sacrificar justiça: na carga concentrada, sua espera máxima foi 35,9% maior que a
do FCFS, enquanto o SCAN manteve a espera máxima próxima à do FCFS; isso justifica mecanismos de
prazo ou envelhecimento em sistemas reais.
3. O polling só é razoável em dispositivos rápidos: no HDD ele ocupou 86,3–100,0% da CPU, contra
0,8–1,1% da interrupção; no dispositivo rápido, o polling usou 0,53–1,07%, menos que os
1,12–2,28% da interrupção, devido ao custo fixo por bloco.
4. A resolução de caminhos é linear no número de diretórios: cada nível acrescentou exatamente
uma leitura e cerca de 0,04 ms ao `open`; sem uma cache de diretórios, caminhos profundos são
caros, o que explica a existência de dentry caches nos sistemas reais.
5. As tabelas de arquivos abertos funcionam como previsto: a tabela global ficou com 12 entradas
(arquivos distintos), a soma das tabelas por processo chegou a 24 (8 processos × 3 aberturas) e o
contador máximo de aberturas simultâneas foi 6, confirmando o compartilhamento por FCB.
6. A cache M1 confirma o trade-off clássico: a LRU superou a FIFO abaixo da saturação (39,6%
contra 31,3% a 64 blocos), o acerto saturou em 67,1% a partir de 1.024 blocos, e o write-back
reduziu as escritas físicas de 1.045 para 541–810 ao custo de perder 22–55 blocos sujos na queda
e de elevar a espera máxima para até 1.425,7 ms.
7. As conclusões valem para o modelo, não para um sistema real: em particular, o custo de CPU não
atrasa a fila do disco no simulador, o sistema de arquivos é single-threaded e não há
concorrência real, de modo que os tempos absolutos e a cauda do write-back devem ser lidos como
tendências.

## 7. Referências

- SILBERSCHATZ, A.; GALVIN, P. B.; GAGNE, G. *Operating System Concepts*. 9. ed. Wiley, 2013.
- LOVE, R. *Linux Kernel Development*. 3. ed. Addison-Wesley, 2010.

## 8. Declaração de autoria e uso de IA

**Quem fez o quê:** a divisão de tarefas deve ser preenchida pelos integrantes antes da entrega.

**Uso de ferramentas de IA:**

| Ferramenta | Finalidade | Onde foi usada (arquivos ou seções) |
|---|---|---|
| Kilo (modelo deepseek-flash) | Apoio na implementação do núcleo N2/N3 e do módulo M1, revisão das regras de custo e redação do relatório | `simes/es/escalonadores.py`, `simes/es/cpu.py`, `simes/arquivos/sistema.py`, `simes/es/cache.py`, `RELATORIO.md` |
