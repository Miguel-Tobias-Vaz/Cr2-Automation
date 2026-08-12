# TCM-PA · Painel de Download de Licitações

## Arquivos

Mantenha os dois **na mesma pasta**:

| Arquivo | Função |
|---|---|
| `painel_tcm.py` | A janela onde você configura e acompanha |
| `tcmpa_licitacoes.py` | O motor que faz o download |

## Abrir

```bash
python painel_tcm.py
```

---

## Passo a passo

### 1. Link do mural

1. Abra https://www.tcm.pa.gov.br/mural-de-licitacoes/
2. Aplique os filtros da entidade (município e órgão)
3. Copie a URL da barra do navegador
4. No painel, clique em **Colar**

O painel confirma logo abaixo: `✓ Município 21 · Órgão 21001`

Não precisa se preocupar com o formato — ele corrige domínio antigo
(`tcmpa.tc.br`), ajusta a rota e remove o número de página automaticamente.

### 2. Período

| Opção | Uso |
|---|---|
| **Todos os anos** | Tudo que existir (pede confirmação: costuma ser pesado) |
| **Ano específico** | Só um ano |
| **Faixa de anos** | De 2023 até 2026, por exemplo |

### 3. Opções

- **Nome da pasta** — deixe vazio para detectar sozinho
  (`CÂMARA MUNICIPAL DE BELÉM` → `CM Belém`), ou escreva o que quiser
- **Salvar em** — pasta de destino
- **OCR** — lê os PDFs para achar o número real da licitação
- **Somente planilha** — gera o Excel sem baixar nenhum arquivo (bem mais rápido)

### 4. Iniciar

Acompanhe pelo log e pela barra de progresso. O botão **Parar** interrompe
de forma segura, ao terminar a licitação em andamento.

---

## O que é gerado

```
C:\Downloads\PM Cametá 2023-2026\
├── PREGÃO ELETRÔNICO – 024-2023\
│   ├── _dados.json
│   ├── Documentos\
│   │   ├── 01 - EDITAL.pdf
│   │   └── 02 - TERMO DE REFERÊNCIA.pdf
│   └── Contratos\
│       ├── 01 - TRANSFORMAT COMÉRCIO LTDA\
│       │   └── 01 - CONTRATO.PDF
│       └── 02 - AUTOCAR VEÍCULOS LTDA\
│           └── 01 - CONTRATO.PDF
└── licitacoes_PM Cametá_2023-2026_20260812_1430.xlsx
```

### Planilha

**Aba Licitações** — Nº, Nº por OCR, Confere?, Confiança, Modalidade
(padronizada e original), Tipo, Objeto, Datas, Situação, Município, Órgão,
Valores, Pasta e URL.

**Aba Contratos** — Nº do contrato, Contratado, CNPJ/CPF, Vigência
(início e fim), Valor.

---

## Perguntas comuns

**Faltou contrato.**
Cada licitação registra no log `Contratos processados: X/Y`, onde Y é o número
que o próprio site informa. Se X for menor, aparece um aviso. O script tem duas
camadas de recuperação para esses casos — mande o trecho do log se acontecer.

**O OCR não funciona.**
Precisa do Tesseract instalado (veja `INSTALAR_OCR.md`). Sem ele o download
funciona igual; só as colunas de OCR ficam vazias.

**Está muito lento.**
Há uma pausa de 1,5s entre requisições para não sobrecarregar o TCM. Para um
levantamento rápido, marque **Somente planilha**.

**Erro "tcmpa_licitacoes.py não encontrado".**
Os dois arquivos precisam estar na mesma pasta.
