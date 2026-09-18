# Regras de Licitações e Contratos

Documento extraído do código atual do **Cr2-Automation** (`automacoes/download-licitacoes/` e `gestor_regras/`).  
Serve para conferir extração, pastas e planilhas de upload no portal CR2.

Fontes principais:

- `gestor_regras/config_front.py` — vocabulário oficial do Front
- `gestor_regras/front.py` — formatação da linha de licitação (regras 5, 8, 12)
- `gestor_regras/contratos.py` — o que vai para Contratos/ e Aditivos/
- `gestor_regras/campos_contrato.py` — campos da planilha de contratos
- `ia_local/regras_titulo.py` — número com sigla
- `ia_local/regras_valores.py` — valor estimado e homologado
- `ia_local/classificar_docs.py` — tipo e prioridade dos anexos
- `script.py` — modalidade, situação, datas, pastas, OCR e paralelismo

---

## 1. Fluxo geral

1. Coleta as licitações (site da entidade ou planilha/Drive).
2. Ordena **alfabeticamente** pelo título.
3. Cria pastas `001 - Nome`, `002 - Nome`… (mesma ordem da planilha).
4. Baixa anexos; lê texto nativo e, se ligado, OCR em pasta `_ocr/`.
5. Extrai campos por regras; a IA (Ollama) só confirma, se estiver ligada.
6. Gera `Licitacoes_preenchida.xlsx` (com aba Auditoria).
7. Gera `subirLicitacoes.xlsx` + `subirDocumentosLicitacoes.xlsx`.
8. Separa PDFs: contratos → `Contratos/`; aditivos → `Aditivos/`.
9. Gera `subirContratos.xlsx` só com contratos (aditivo não entra nessa planilha).
10. Apaga artefatos de OCR (`_ocr/`, `*.ocr.pdf`, `*.ocr.txt`).

Pendentes **entram** nas planilhas `subir*` com o que houver; a pasta física vai para `PENDENTES/`.

---

## 2. Organização de pastas (Drive e planilha)

A ordem da planilha e das pastas é a mesma: **alfabética pelo título**, depois prefixo numérico.

| Onde | Nome |
|------|------|
| Pasta da licitação | `001 - Pregão Eletrônico Nº 009-2023 …` |
| Contratos | `Contratos/001 - Pregão Eletrônico Nº 009-2023 …/` |
| Aditivos | `Aditivos/001 - Pregão Eletrônico Nº 009-2023 …/` |
| Incompletas | `PENDENTES/` (mesmo nome da pasta) |

Assim, ao subir as pastas no Drive e colar os links em `subirDocumentosLicitacoes.xlsx`, a ordem bate com `subirLicitacoes.xlsx`.

Nomes de arquivo: título em português (conectivos minúsculos, siglas conhecidas em MAIÚSCULO). Duplicata vira `Nome (2).pdf`.

---

## 3. Licitação — campos do Front

Planilha: `subirLicitacoes.xlsx` (aba `Modelo_Licitacoes - Planilha`).

| Campo | Obrigatório | Formato |
|-------|-------------|---------|
| Modalidade | sim | nome oficial da lista |
| Número | sim | dígitos do portal + sigla (`009/2023-RPPP`) |
| Ano | sim | `AAAA` (do número, se faltar) |
| Objeto | sim | texto entre parênteses do título, ou do documento |
| Data de Publicação | sim (pelo menos uma data) | `dd/mm/aaaa` |
| Data de Abertura | não | se faltar, **repete a publicação** |
| Valor Estimado | não | `1720000.00`; se faltar, **0.00** |
| Situação da Licitação | sim | vocabulário Front |
| Valor Homologado | não | se Finalizado e vazio, **repete o estimado** |

“Não informado” e vazio contam como campo em branco.

**Falta (vai para PENDENTES, mas ainda entra na planilha):**

- Modalidade, Número, Ano, Objeto ou Situação vazios
- Número sem hífen (faltou a sigla)
- Nenhuma data (publicação e abertura)
- Modalidade “Não houve Processos Licitatórios” (não é certame)

**Alertas (aceita a linha mesmo assim):**

- Estimado não achado → grava `0.00`
- Abertura não achada → copia a publicação
- Finalizado sem homologado → copia o estimado

---

## 4. Modalidades oficiais e siglas

Ordem = tabela do Front.

| Sigla | Modalidade |
|-------|------------|
| AD | Adesão a Ata de Registro de Preço |
| CR | Credenciamento |
| CC | Concorrência |
| CON | Concurso |
| CA | Carona |
| CD | Contratação Direta |
| CV | Convite |
| CP | Chamada Pública |
| DC | Diálogo Competitivo |
| DL | Dispensa de Licitação |
| IN | Inexigibilidade de Licitação |
| LL | Leilão |
| PE | Pregão Eletrônico |
| PP | Pregão Presencial |
| RPCP | Registro de Preços Originário de Chamamento Público |
| RPPE | Registro de Preços Originário de Pregão Eletrônico |
| RPPP | Registro de Preços Originário de Pregão Presencial |
| TP | Tomada de Preços |

### Como o título vira modalidade

Regras **específicas primeiro** (SRP antes de pregão simples):

1. Pregão eletrônico + SRP / “registro de preços” → **RPPE**
2. Pregão presencial + SRP / “registro de preços” → **RPPP**
3. Chamamento/chamada pública + registro de preços → **RPCP**
4. Adesão → **AD**; Carona → **CA**
5. Dispensa → **DL**; Inexigibilidade → **IN**; Contratação direta → **CD**
6. Demais: diálogo, credenciamento, chamada, concorrência, concurso, convite, leilão, tomada, pregão eletrônico/presencial

Pregão **sem** “eletrônico/presencial”:

- prefixo `PP` / `PPRP` → Pregão Presencial
- prefixo `PE` / `PERP` → Pregão Eletrônico
- senão → Pregão Eletrônico (padrão desde 2020)

Aliases aceitos: “carta convite”, “chamamento público”, “concorrência eletrônica/presencial” (viram Concorrência), “dispensa”, “inexigibilidade”, etc.

### Regra 7 — Registro de preços no objeto

Se a modalidade já é Pregão Eletrônico, Pregão Presencial ou Chamada Pública **e** o objeto contém “registro de preços”, a modalidade sobe para **RPPE / RPPP / RPCP**.

---

## 5. Número da licitação

O número do **certame** (não o do contrato, lei, processo ou empenho).

- Aceita 1 a 10 dígitos + `/` + ano: `9/2023`, `001/2023`, `1123002/2023` (Altamira).
- **Preserva** códigos do portal (`007`, `CMVX`, etc.).
- **Só troca a categoria final** pela sigla Front:

| Entrada | Modalidade | Saída |
|---------|------------|--------|
| `9/2023-007-CMVX-SRP` | RPPP | `9/2023-007-CMVX-RPPP` |
| `2/2023-001` | Tomada de Preços | `2/2023-001-TP` |
| `009/2023` | Pregão Eletrônico | `009/2023-PE` |

Categorias que o sistema reconhece para trocar: siglas Front + `SRP`, `RP`, `RPE`, `RPP`, `DISP`, `INEX`, `TOMADA`, `CONVITE`, `PREGAO`, `CREDENCIAMENTO`.  
**Não** trata `CMVX`, `CPL` etc. como categoria.

Ano: prioridade `…/AAAA` no número; sufixos tipo `-200402` **não** viram ano 2004.

Objeto: texto entre parênteses no final do título da listagem.

---

## 6. Situação da licitação

### Vocabulário Front (o que sobe)

Aberto, Anulado, Cancelado, Deserto, Em andamento, Finalizado, Fracassado, Publicada, Revogado, Suspenso.

### Como infere (só título + **nomes** dos arquivos)

Não lê o corpo do PDF para situação: editais trazem frases do tipo “caso seja deserta…”, que geravam falso positivo.

Ordem:

1. “deserta” no título ou nome → Deserta → Front **Deserto**
2. “fracassada” → Fracassada → **Fracassado**
3. revogação/revogada no nome → **Revogado**
4. anulação/anulada no nome → **Anulado**
5. **Contratação direta** (dispensa, inexigibilidade, contratação direta, adesão, carona):
   - ratificação **ou** extrato **ou** contrato no nome → Ratificada → **Finalizado**
   - senão, fica vazia (não inventa homologação)
6. Certame concorrencial: homologação no nome → Homologada → **Finalizado**
7. Adjudicação no nome → Adjudicada → **Finalizado**
8. Senão → **Em andamento** (padrão da extração)

Mapa interno → Front: homologada/adjudicada/ratificada = Finalizado; deserta = Deserto; etc.

Contratação direta **não tem sessão pública** (Lei 8.666 arts. 24/25; Lei 14.133 arts. 74/75). O rito de conclusão é a **ratificação**, não a homologação.

---

## 7. Datas

- Formato Front: `dd/mm/aaaa` (ano entre 1990 e 2100).
- Publicação: data da listagem/aviso; também aceita ISO `aaaa-mm-dd`.
- Abertura: rótulos como “data de abertura”, “sessão pública”, “recebimento das propostas”, “abertura dos envelopes”, etc.
- Sem rótulo de abertura: não inventa; a regra Front **copia a publicação**.
- Datas inválidas de OCR (ex.: 31/02) são descartadas.
- Contratação direta: abertura costuma coincidir com publicação/ratificação.

---

## 8. Valores da licitação

Formato Front: `1720000.00` (ponto decimal, sem milhar).  
“Valor sigiloso” → `0.00`.

Valor mínimo plausível na extração antiga: **R$ 100,00** (abaixo disso costuma ser multa, taxa ou item).

### Estimado — de onde vem

Documentos: DFD, ETP, Termo de Referência, edital, aviso, orçamento/mapa de cotação, dispensa/inexigibilidade, autorização.

Rótulos típicos: valor estimado, valor de referência, preço máximo, orçado em, valor teto, total estimado, valor global, etc.

Mapa de cotação: soma as linhas “Valores médios : …”.

### Homologado — de onde vem

Documentos: termo de homologação, adjudicação, contrato, ata, aceite/adesão.

No **Termo de Homologação**, nesta ordem:

1. Total explícito no final que **confere** com a soma dos itens
2. Total com rótulo forte (“valor total homologado”, “total geral”) no terço final
3. Se o “total” for bem menor que a soma dos itens → usa a **soma** (evita pegar unitário)
4. Total que bate com a soma dos demais valores impressos
5. Sem total: **soma dos itens/lotes**
6. Fallback: valores `R$` em ata/contrato/homologação (≥ 100)

**Não** usar preço unitário como homologado.

### Coerência estimado × homologado

Se o homologado for **maior que 1,5 × o estimado**, tenta outro candidato de homologado que caiba nessa faixa.

Na extração antiga: homologado acima de **1,10 × estimado** em certame concorrencial é tratado como erro (proposta acima do teto).

Se só houver valor em ata/adesão e não houver estimado, o mesmo valor pode servir de estimado.

---

## 9. Classificação e leitura dos anexos

Prioridade de leitura (menor número = primeiro):

1. DFD / formalização de demanda  
2. ETP  
3. Termo de Referência / orçamento / pesquisa de preços  
4. Edital  
5. Aviso / dispensa-inexigibilidade  
6. Autorização / minuta de contrato  
7. Homologação / ratificação  
8. Adjudicação / parecer  
9. Ata  
10. Contrato firmado / aditivo  
11. Aceite / adesão  

**Não confundir:**

- Minuta de contrato (anexo do edital) ≠ contrato assinado
- Contrato social (habilitação) ≠ contrato administrativo
- Aditivo ≠ contrato

Leitura integral (todas as páginas, dentro do limite de caracteres): DFD, TR, edital, homologação.  
Contrato: até 12 páginas / 20 mil caracteres na extração de valores da licitação; na planilha de contratos o texto **nativo** é lido inteiro (cláusula de valor costuma ficar depois da página 6).

### Filtro “docs leves”

Pula processo que só tem contrato/aditivo puro.  
Vale a pena extrair se houver pelo menos: DFD, ETP, TR, edital, homologação, aviso, orçamento ou dispensa/inexig.

---

## 10. Planilhas de upload da licitação

| Arquivo | Conteúdo |
|---------|----------|
| `subirLicitacoes.xlsx` | 9 colunas Front, uma linha por licitação, ordem alfabética |
| `subirDocumentosLicitacoes.xlsx` | `LinkDaPasta`, Modalidade, Numero — **mesma ordem e mesmo número** |
| `Licitacoes_preenchida.xlsx` | conferência + aba Auditoria (origem de cada campo) |
| `Nao_migradas_links.xlsx` | puladas pelo filtro de docs / amostra mensal |

Número e modalidade são **iguais** nas três planilhas (`padronizar_linha_para_todas_planilhas`).

LinkDaPasta: caminho local da pasta, ou URL `base/nome-da-pasta` se houver link base do Drive.

Pendentes: entram na planilha com dados parciais; pasta vai para `PENDENTES/` e o link aponta para o destino. Relatório em `PENDENTES/_RELATORIO.txt`.

---

## 11. Contratos — o que entra e o que não entra

**Regra 13 (Gestor):** aditivo **não é contrato**.

| Arquivo (pelo nome) | Destino | Entra em `subirContratos.xlsx`? |
|---------------------|---------|----------------------------------|
| Contrato administrativo, termo de contrato, extrato de contrato, “contrato” | `Contratos/<pasta da licitação>/` | sim |
| Portaria / termo de fiscal / designação de fiscal | `Contratos/<pasta da licitação>/` | não (só empresta o nome do fiscal) |
| Termo aditivo, aditivo, apostilamento | `Aditivos/<pasta da licitação>/` | **não** |
| Minuta, contrato social, modelo de contrato | fica na pasta da licitação | não |
| `*.ocr`, `_ocr/`, `.part` | ignorados e apagados no fim | não |

Só cria `Contratos/…` ou `Aditivos/…` se houver pelo menos um arquivo a mover.

---

## 12. Planilha de contratos (`subirContratos.xlsx`)

Aba: `Contrato - Sheet`.

| Campo planilha | Interno | Obrigatório |
|----------------|---------|-------------|
| licitacaoOrigem | número da licitação Front | não (alerta se vazio) |
| ano | ano do contrato | **sim** |
| tipoContrato | `Contrato` ou `Aditivo 01` | **sim** |
| numero | `NNN/AAAA` do **contrato** | **sim** |
| objeto | cláusula de objeto | **sim** |
| nomeRazaoSocial | contratada | **sim** |
| cpfCnpj | CNPJ/CPF da contratada | não |
| dataVigenciaIN / FIM | vigência | não |
| valor | `0.00` | não |
| fiscalContrato | nome do fiscal | não |
| documento | caminho relativo ou URL | — |

Sem os obrigatórios a linha **não sobe**; vai para `_RELATORIO_CONTRATOS.txt`.

Alertas (sobe mesmo assim): CNPJ, vigência, valor, fiscal ou origem vazios.

### Tipo

- Nome/texto sem “aditivo” → `Contrato`
- Com aditivo: `Aditivo 01`, `Aditivo 02`… (`1º Termo Aditivo`, “segundo termo aditivo”, “aditivo nº 03”)
- Aditivo sem ordem → `Aditivo 01`

Na prática atual, aditivos **não** entram nesta planilha; o tipo Aditivo fica só se um PDF de contrato for classificado assim pelo texto.

### Número e ano do contrato

Não é o número da licitação.

Prioridade:

1. “CONTRATO Nº 003/2025” no texto
2. Mesmo padrão no nome do arquivo (`Contrato 003-2025.pdf`)
3. Primeiro `NNN/AAAA` válido no texto

Normaliza para 3 dígitos: `3/2025` → `003/2025`.  
Aditivo **herda** o número do contrato (não o número do aditivo).

Ano: do número; senão da 1ª data de vigência.

### Objeto

Cláusulas “objeto”, “objeto da contratação”, “cláusula … objeto”, “tem por objeto”. Corta na cláusula seguinte. Mínimo ~20 caracteres; teto ~600.

### Contratada (nome + CNPJ)

- Bloco “CONTRATADA:” **ou** trecho antes de “doravante denominada CONTRATADA”
- Não usar o CNPJ do órgão (o que aparece **antes** do bloco da contratada)
- Em aditivo, se o órgão não repetir o CNPJ, não descarta o CNPJ da empresa
- Formato: `12.345.678/0001-99` ou CPF `000.000.000-00`
- Nome: corta em “inscrita”, “CNPJ”, “sede”, “doravante”

### Vigência

Aceita “vigência”, “vige ncia”, “vig�ncia” (sujeira de PDF).

1. Intervalo: de DATA a DATA  
2. Início + término  
3. Prazo (N meses/dias/anos) a contar de DATA  
4. “até DATA” + data de assinatura como início  

Formato `dd/mm/aaaa`; também “12 de janeiro de 2025”.

### Valor do contrato

Só com rótulo perto do `R$`: valor global, valor total, valor do contrato, valor contratado, importa em, valor da contratação, valor estimado, valor acrescido, valor mensal.

**Não adivinha** o primeiro `R$` do PDF (quase sempre é item de tabela). Melhor vazio + alerta do que valor errado no portal.

### Fiscal

Ordem: “como FISCAL TITULAR” (vence o substituto) → rótulo “Fiscal:” → “como fiscal do” → “designar/nomear o servidor …”.  
Se o contrato não tiver, usa a **portaria/termo de fiscal** da mesma pasta Contratos.

---

## 13. OCR

- Cache em `_ocr/<arquivo>.ocr.txt` (e às vezes `.ocr.pdf`).
- Isolado da pasta de documentos; **apagado no final**.
- Não sobe para Contratos/Aditivos nem entra como anexo.
- Motor padrão: Tesseract (+ PyMuPDF para renderizar). PyMuPDF travado em `< 1.28` no Windows.

---

## 14. Paralelismo

| Fonte | Licitações ao mesmo tempo | Downloads por licitação |
|-------|---------------------------|-------------------------|
| Portal da entidade | até 12 (env `OPTO_LICITACAO_WORKERS`) | até 6 |
| Planilha / Google Drive | **2** | **1** (Drive devolve 500 em rajada) |

Pastas e planilhas **não** seguem a ordem em que as threads terminam: reordenam pelo índice alfabético (`001`, `002`…).

A barra de progresso sobe ao **iniciar** cada licitação e não regride.

---

## 15. Papel da IA (Ollama)

Opcional. Se estiver offline, segue **só com regras**.

Confirma, não inventa: número, ano, objeto, situação, datas, valores.  
Se a leitura local estiver certa, **mantém**.  
Situação e valores no vocabulário/formato Front.  
Número do certame: `000/AAAA` + códigos do portal; não usar lei, decreto, processo, contrato, empenho, CNPJ.

---

## 16. Resumo rápido para conferência

**Licitação**

- Ordem: alfabética → pastas `001 - …`
- Número: preserva códigos, só troca sigla
- PE/PP/CP + “registro de preços” no objeto → RPPE/RPPP/RPCP
- Situação: só pelos **nomes** dos arquivos
- Direta: ratificação, não homologação
- Sem abertura → copia publicação
- Sem estimado → `0.00`
- Finalizado sem homologado → copia estimado
- Homologado = total final ou soma dos itens, nunca unitário

**Contrato**

- Assinado/extrato/portaria de fiscal → `Contratos/`
- Aditivo → `Aditivos/` (não vai para `subirContratos.xlsx`)
- Minuta e contrato social ficam na licitação
- Número `NNN/AAAA` do contrato, não da licitação
- Valor só com rótulo “global/total/contrato”
- Fiscal: titular; senão, portaria da pasta

---

*Gerado a partir do código do Cr2-Automation. Se a regra no código mudar, este arquivo precisa ser atualizado.*
