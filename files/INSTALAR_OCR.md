# Instalação do OCR (Windows)

O script lê os PDFs baixados para achar o **número da licitação**. Se o PDF
já tem camada de texto, ele lê direto (rápido). Se for escaneado, aplica OCR.

## 1. Bibliotecas Python

```bash
pip install pymupdf pytesseract pillow
```

## 2. Tesseract OCR + idioma português

1. Baixe o instalador em:
   https://github.com/UB-Mannheim/tesseract/wiki
2. Durante a instalação, marque **Additional language data → Portuguese**
3. Instale em `C:\Program Files\Tesseract-OCR`

## 3. Se o Python não encontrar o Tesseract

Adicione no topo do script, logo após os `import`:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## Testar a instalação

```bash
tesseract --version
tesseract --list-langs      # deve aparecer "por"
```

---

## Rodar sem OCR

Se não quiser instalar nada, desligue no script:

```python
OCR_ATIVO = False
```

O download e a planilha continuam funcionando — só as colunas de OCR
ficam vazias.

---

## Ajustes de qualidade

| Config | Padrão | Quando mudar |
|---|---|---|
| `OCR_DPI` | 300 | Suba para 400 se as digitalizações forem ruins (fica mais lento) |
| `OCR_MAX_PAGINAS` | 3 | O número fica na capa; raramente precisa aumentar |
| `OCR_MAX_ARQUIVOS` | 6 | Quantos PDFs analisar por licitação antes de desistir |
