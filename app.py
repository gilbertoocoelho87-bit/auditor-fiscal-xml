```python
import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import os
import re
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Auditor Fiscal de Divergências",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Auditor PGDAS - Identificador de Notas Incorretas")

st.write(
    "Sistema de auditoria de XMLs para identificação de possíveis "
    "divergências tributárias por NCM, CEST, CFOP, CST/CSOSN e UF."
)

# ============================================================
# CONSTANTES
# ============================================================

UF_CODIGOS = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

# ============================================================
# BASE
```
