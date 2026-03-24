# Fundo Comunitario - App de Doacoes PIX

Aplicacao web simples em Streamlit para registrar contribuicoes e gerar QR Code PIX para doacoes.

## Requisitos

- Python 3.10+ (recomendado 3.11)
- pip

## Instalacao

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Execucao local

```powershell
streamlit run app.py
```

A aplicacao sera iniciada em:

- http://localhost:8501

## Arquivos principais

- app.py: aplicacao Streamlit
- requirements.txt: dependencias Python

## Observacoes

- Os dados de doacoes sao salvos em `donations.json` no mesmo diretorio da aplicacao.
- Parametros como chave PIX, nome do recebedor e meta mensal podem ser ajustados no inicio de `app.py`.
