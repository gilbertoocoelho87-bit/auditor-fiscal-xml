import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

# Configuração da página do site
st.set_page_config(page_title="Auditor Fiscal de Divergências", layout="wide")

st.title("📊 Auditor PGDAS - Identificador de Notas Incorretas")
st.write("Análise em lote com aba exclusiva para apontar quais XMLs vieram preenchidos de forma errada.")

# --- COMPONENTE DE CARREGAMENTO (IMPORTAÇÃO DO XML) ---
uploaded_files = st.file_uploader("📂 Arraste e solte seus XMLs de Notas Fiscais aqui", type=["xml"], accept_multiple_files=True)

# --- BASE DE LEGISLAÇÃO DE ICMS-ST (TODOS OS ESTADOS) ---
MATRIZ_ESTADUAL_ICMS = {
    '11': { 'UF': 'RO', 'Construcao_ST': 'Anexo VI do RICMS/RO', 'Medicamento_ST': 'Anexo VI (Medicamentos) do RICMS/RO', 'Geral_ST': 'Regulamento de ST/RO' },
    '12': { 'UF': 'AC', 'Construcao_ST': 'Anexo IV do RICMS/AC', 'Medicamento_ST': 'Anexo IV (Farmacêuticos) do RICMS/AC', 'Geral_ST': 'Regulamento de ST/AC' },
    '13': { 'UF': 'AM', 'Construcao_ST': 'Anexo II do RICMS/AM', 'Medicamento_ST': 'Anexo II (Farmacêuticos) do RICMS/AM', 'Geral_ST': 'Regulamento de ST/AM' },
    '14': { 'UF': 'RR', 'Construcao_ST': 'RICMS/RR Decreto 4.335-E/01', 'Medicamento_ST': 'Regime de ST de Medicamentos - RICMS/RR', 'Geral_ST': 'Regulamento de ST/RR' },
    '15': { 'UF': 'PA', 'Construcao_ST': 'Anexo I do RICMS/PA', 'Medicamento_ST': 'Anexo I (Fármacos) do RICMS/PA', 'Geral_ST': 'Regulamento de ST/PA' },
    '16': { 'UF': 'AP', 'Construcao_ST': 'Decreto nº 2.269/1998', 'Medicamento_ST': 'Anexo Único (Medicamentos) - RICMS/AP', 'Geral_ST': 'Regulamento de ST/AP' },
    '17': { 'UF': 'TO', 'Construcao_ST': 'Decreto nº 2.912/2006', 'Medicamento_ST': 'Regulamento do ICMS/TO - Medicamentos', 'Geral_ST': 'Regulamento de ST/TO' },
    '21': { 'UF': 'MA', 'Construcao_ST': 'Anexo 4.0 do RICMS/MA', 'Medicamento_ST': 'Anexo 4.0 (Medicamentos) - RICMS/MA', 'Geral_ST': 'Regulamento de ST/MA' },
    '22': { 'UF': 'PI', 'Construcao_ST': 'Anexo V do RICMS/PI', 'Medicamento_ST': 'Anexo V (Setor Farmacêutico) do RICMS/PI', 'Geral_ST': 'Regulamento de ST/PI' },
    '23': { 'UF': 'CE', 'Construcao_ST': 'Livro III do RICMS/CE', 'Medicamento_ST': 'Livro III (Produtos Farmacêuticos) do RICMS/CE', 'Geral_ST': 'Livro III do RICMS/CE' },
    '24': { 'UF': 'RN', 'Construcao_ST': 'Anexo 05 do RICMS/RN', 'Medicamento_ST': 'Anexo 05 (Medicamentos) - RICMS/RN', 'Geral_ST': 'Regulamento de ST/RN' },
    '25': { 'UF': 'PB', 'Construcao_ST': 'Livro V do RICMS/PB', 'Medicamento_ST': 'Livro V (Medicamentos) do RICMS/PB', 'Geral_ST': 'Regulamento de ST/PB' },
    '26': { 'UF': 'PE', 'Construcao_ST': 'Art. 381-A e Anexos 37/37-C do RICMS/PE', 'Medicamento_ST': 'Decreto Estadual nº 61.284/2026 (ST Medicamentos - RICMS/PE)', 'Geral_ST': 'Decreto Estadual nº 44.650/17 (RICMS/PE)' },
    '27': { 'UF': 'AL', 'Construcao_ST': 'Anexo X do RICMS/AL', 'Medicamento_ST': 'Anexo X (Produtos Farmacêuticos) do RICMS/AL', 'Geral_ST': 'Regulamento de ST/AL' },
    '28': { 'UF': 'SE', 'Construcao_ST': 'Título IV do RICMS/SE', 'Medicamento_ST': 'Título IV (Medicamentos) do RICMS/SE', 'Geral_ST': 'Regulamento de ST/SE' },
    '29': { 'UF': 'BA', 'Construcao_ST': 'Artigo 289 do RICMS/BA', 'Medicamento_ST': 'Artigo 289 (Fármacos e Medicamentos) do RICMS/BA', 'Geral_ST': 'Regulamento de ST/BA' },
    '31': { 'UF': 'MG', 'Construcao_ST': 'Anexo VII, Parte 2 do RICMS/MG', 'Medicamento_ST': 'Anexo VII, Parte 2 (Produtos Farmacêuticos) - RICMS/MG', 'Geral_ST': 'Anexo VII do RICMS/MG' },
    '32': { 'UF': 'ES', 'Construcao_ST': 'Anexo V do RICMS/ES', 'Medicamento_ST': 'Anexo V (Medicamentos) do RICMS/ES', 'Geral_ST': 'Anexo V do RICMS/ES' },
    '33': { 'UF': 'RJ', 'Construcao_ST': 'Livro II do RICMS/RJ', 'Medicamento_ST': 'Anexo I do Livro II (Medicamentos) - RICMS/RJ', 'Geral_ST': 'Livro II do RICMS/RJ' },
    '35': { 'UF': 'SP', 'Construcao_ST': 'Artigo 313-Y do RICMS/SP', 'Medicamento_ST': 'Artigo 313-A (Produtos Farmacêuticos) do RICMS/SP', 'Geral_ST': 'Artigo 313 do RICMS/SP' },
    '41': { 'UF': 'PR', 'Construcao_ST': 'Anexo IX do RICMS/PR', 'Medicamento_ST': 'Anexo IX (Seção XIV - Medicamentos) do RICMS/PR', 'Geral_ST': 'Anexo IX do RICMS/PR' },
    '42': { 'UF': 'SC', 'Construcao_ST': 'Anexo 3 do RICMS/SC', 'Medicamento_ST': 'Anexo 3 (Produtos Farmacêuticos) do RICMS/SC', 'Geral_ST': 'Anexo 3 do RICMS/SC' },
    '43': { 'UF': 'RS', 'Construcao_ST': 'Livro III, Artigo 207 do RICMS/RS', 'Medicamento_ST': 'Livro III, Artigo 221 (Medicamentos) do RICMS/RS', 'Geral_ST': 'Livro III do RICMS/RS' },
    '50': { 'UF': 'MS', 'Construcao_ST': 'Anexo III do RICMS/MS', 'Medicamento_ST': 'Anexo III (Produtos Farmacêuticos) do MS', 'Geral_ST': 'Anexo III do RICMS/MS' },
    '51': { 'UF': 'MT', 'Construcao_ST': 'Anexo X do RICMS/MT', 'Medicamento_ST': 'Anexo X (Medicamentos) do RICMS/MT', 'Geral_ST': 'Anexo X do RICMS/MT' },
    '52': { 'UF': 'GO', 'Construcao_ST': 'Anexo VIII do RCTE/GO', 'Medicamento_ST': 'Anexo VIII (Produtos Farmacêuticos) do RCTE/GO', 'Geral_ST': 'Anexo VIII do RCTE/GO' },
    '53': { 'UF': 'DF', 'Construcao_ST': 'Anexo IV do RICMS/DF', 'Medicamento_ST': 'Caderno I do Anexo IV (Medicamentos) do RICMS/DF', 'Geral_ST': 'Anexo IV do RICMS/DF' }
}

# --- FUNÇÃO DE AUDITORIA CRÍTICA DE XML ---
def auditoria_lote_divergencias(xml_files):
    todos_produtos = []
    for xml_file in xml_files:
        try:
            xml_file.seek(0) # Correção estrutural para permitir múltiplas leituras em lote
            xml_data = xml_file.read()
            root = ET.fromstring(xml_data)
            
            # 1. Identificar a UF da Nota
            cod_uf = '35'
            for elem in root.iter():
                if elem.tag.endswith('cUF'):
                    cod_uf = str(elem.text).strip()
                    break
            config_uf = MATRIZ_ESTADUAL_ICMS.get(cod_uf, { 'UF': 'BR', 'Construcao_ST': 'Regulamento Local', 'Medicamento_ST': 'Regulamento Local', 'Geral_ST': 'Regulamento Local' })
            uf_nome = config_uf['UF']
            
            # 2. Identificar o número da NF-e
            numero_nfe = 'Não Encontrado'
            for elem in root.iter():
                if elem.tag.endswith('nNF'):
                    numero_nfe = elem.text
                    break
                    
            # 3. Varrer os itens do XML e cruzar com as tags do fornecedor
            for det in root.iter():
                if det.tag.endswith('det'):
                    xProd = 'Desconhecido'
                    ncm = ''
                    cst_xml = '00'
                    for elem in det.iter():
                        if elem.tag.endswith('xProd'):
                            xProd = elem.text
                        if elem.tag.endswith('NCM'):
                            ncm = str(elem.text).strip().replace('.', '')
                            
                    for elem in det.iter():
                        if elem.tag.endswith('CST') or elem.tag.endswith('CSOSN'):
                            cst_xml = str(elem.text).strip()
                            break
                            
                    grupo_4d = ncm[:4] if ncm else ''
                    grupo_2d = ncm[:2] if ncm else ''
                    
                    # --- CRITÉRIOS DE LEGISLAÇÃO VS XML (TODOS OS NCMS DO CONVÊNIO CONFAZ 142/18) ---
                    
                    # Segmento 01: Medicamentos e Fármacos
                    if grupo_4d in ['3002', '3003', '3004', '3005', '3006'] or ncm.startswith('40141000'):
                        regra_icms = 'ST'
                        regra_pis_cofins = 'MONOFÁSICO'
                        base_icms = config_uf['Medicamento_ST']
                        base_federal = 'Tabela 4.3.10 SPED (Cód. 102 - Fármacos / Lei nº 10.147/00)'
                        
                    # Segmento 02: Autopeças e Motores
                    elif grupo_4d in ['8708', '8407', '8408', '8409']:
                        regra_icms = 'ST'
                        regra_pis_cofins = 'MONOFÁSICO'
                        base_icms = f"Regime ST Autopeças -> {config_uf['Geral_ST']}"
                        base_federal = 'Tabela 4.3.10 SPED (Cód. 103 - Autopeças / Lei nº 10.485/02)'
                        
                    # Segmento 03: Pneumáticos, Câmaras de Ar e Protetores de Borracha
                    elif grupo_4d in ['4011', '4012', '4013']:
                        regra_icms = 'ST'
                        regra_pis_cofins = 'MONOFÁSICO'
                        base_icms = f"Regime ST Pneumáticos -> {config_uf['Geral_ST']}"
                        base_federal = 'Tabela 4.3.10 SPED (Cód. 107 - Pneus e Câmaras / Lei nº 10.485/02)'
                        
                    # Segmento 04: Bebidas Frias (Cervejas, Refrigerantes, Águas e Chopes)
                    elif grupo_4d in ['2201', '2202', '2203']:
                        regra_icms = 'ST'
                        regra_pis_cofins = 'MONOFÁSICO'
                        base_icms = f"Regime ST Bebidas Frias -> {config_uf['Geral_ST']}"
                        base_federal = 'Tabela 4.3.10 SPED (Cód. 104 - Bebidas / Lei nº 13.097/15)'
                        
                    # Segmento 05: Bebidas Alcoólicas (Exceto Cerveja e Chope)
                    elif grupo_4d in ['2204', '2205', '2206', '2208']:
                        regra_icms = 'ST'
                        regra_pis_cofins = 'NORMAL'
                        base_icms = f"Regime ST Bebidas Alcoólicas -> {config_uf['Geral_ST']}"
                        base_federal = 'Regime Geral (PIS/COFINS Não Monofásico)'
                        
                    # Segmento 06: Cigarros e Outros Produtos Derivados do Fumo
                    elif grupo_2d == '24':
                        regra_icms = 'ST'
                        regra_pis_cofins = 'MONOFÁSICO'
                        base_icms = f"Regime ST Cigarros e Fumo -> {config_uf['Geral_ST']}"
