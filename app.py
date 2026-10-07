import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

# Importações para criação de PDF profissional
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração da página do site
st.set_page_config(page_title="Auditor Fiscal com Exportação PDF", layout="wide")

st.title("📊 Auditor PGDAS - Identificador de Notas Incorretas")
st.write("Análise em lote de XMLs com relatórios visuais e exportação oficial em PDF.")

# --- COMPONENTE DE CARREGAMENTO ---
uploaded_files = st.file_uploader("📂 Arraste e solte seus XMLs de Notas Fiscais aqui", type=["xml"], accept_multiple_files=True)

# --- BASE DE LEGISLAÇÃO DE ICMS-ST (TODOS OS ESTADOS) ---
MATRIZ_ESTADUAL_ICMS = {
    "11": {"UF": "RO", "Construcao_ST": "Anexo VI do RICMS/RO", "Medicamento_ST": "Anexo VI (Medicamentos) do RICMS/RO"},
    "12": {"UF": "AC", "Construcao_ST": "Anexo IV do RICMS/AC", "Medicamento_ST": "Anexo IV (Farmacêuticos) do RICMS/AC"},
    "13": {"UF": "AM", "Construcao_ST": "Anexo II do RICMS/AM", "Medicamento_ST": "Anexo II (Farmacêuticos) do RICMS/AM"},
    "14": {"UF": "RR", "Construcao_ST": "RICMS/RR Decreto 4.335-E/01", "Medicamento_ST": "Regime de ST de Medicamentos - RICMS/RR"},
    "15": {"UF": "PA", "Construcao_ST": "Anexo I do RICMS/PA", "Medicamento_ST": "Anexo I (Fármacos) do RICMS/PA"},
    "16": {"UF": "AP", "Construcao_ST": "Decreto nº 2.269/1998", "Medicamento_ST": "Anexo Único (Medicamentos) - RICMS/AP"},
    "17": {"UF": "TO", "Construcao_ST": "Decreto nº 2.912/2006", "Medicamento_ST": "Regulamento do ICMS/TO - Medicamentos"},
    "21": {"UF": "MA", "Construcao_ST": "Anexo 4.0 do RICMS/MA", "Medicamento_ST": "Anexo 4.0 (Medicamentos) - RICMS/MA"},
    "22": {"UF": "PI", "Construcao_ST": "Anexo V do RICMS/PI", "Medicamento_ST": "Anexo V (Setor Farmacêutico) do RICMS/PI"},
    "23": {"UF": "CE", "Construcao_ST": "Livro III do RICMS/CE", "Medicamento_ST": "Livro III (Produtos Farmacêuticos) do RICMS/CE"},
    "24": {"UF": "RN", "Construcao_ST": "Anexo 05 do RICMS/RN", "Medicamento_ST": "Anexo 05 (Medicamentos) - RICMS/RN"},
    "25": {"UF": "PB", "Construcao_ST": "Livro V do RICMS/PB", "Medicamento_ST": "Livro V (Medicamentos) do RICMS/PB"},
    "26": {"UF": "PE", "Construcao_ST": "Art. 381-A e Anexos 37/37-C do RICMS/PE", "Medicamento_ST": "Decreto Estadual nº 61.284/2026 (ST Medicamentos - RICMS/PE)"},
    "27": {"UF": "AL", "Construcao_ST": "Anexo X do RICMS/AL", "Medicamento_ST": "Anexo X (Produtos Farmacêuticos) do RICMS/AL"},
    "28": {"UF": "SE", "Construcao_ST": "Título IV do RICMS/SE", "Medicamento_ST": "Título IV (Medicamentos) do RICMS/SE"},
    "29": {"UF": "BA", "Construcao_ST": "Artigo 289 do RICMS/BA", "Medicamento_ST": "Artigo 289 (Fármacos e Medicamentos) do RICMS/BA"},
    "31": {"UF": "MG", "Construcao_ST": "Anexo VII, Parte 2 do RICMS/MG", "Medicamento_ST": "Anexo VII, Parte 2 (Produtos Farmacêuticos) - RICMS/MG"},
    "32": {"UF": "ES", "Construcao_ST": "Anexo V do RICMS/ES", "Medicamento_ST": "Anexo V (Medicamentos) do RICMS/ES"},
    "33": {"UF": "RJ", "Construcao_ST": "Livro II do RICMS/RJ", "Medicamento_ST": "Anexo I do Livro II (Medicamentos) - RICMS/RJ"},
    "35": {"UF": "SP", "Construcao_ST": "Artigo 313-Y do RICMS/SP", "Medicamento_ST": "Artigo 313-A (Produtos Farmacêuticos) do RICMS/SP"},
    "41": {"UF": "PR", "Construcao_ST": "Anexo IX do RICMS/PR", "Medicamento_ST": "Anexo IX (Seção XIV - Medicamentos) do RICMS/PR"},
    "42": {"UF": "SC", "Construcao_ST": "Anexo 3 do RICMS/SC", "Medicamento_ST": "Anexo 3 (Produtos Farmacêuticos) do RICMS/SC"},
    "43": {"UF": "RS", "Construcao_ST": "Livro III, Artigo 207 do RICMS/RS", "Medicamento_ST": "Livro III, Artigo 221 (Medicamentos) do RICMS/RS"},
    "50": {"UF": "MS", "Construcao_ST": "Anexo III do RICMS/MS", "Medicamento_ST": "Anexo III (Produtos Farmacêuticos) do MS"},
    "51": {"UF": "MT", "Construcao_ST": "Anexo X do RICMS/MT", "Medicamento_ST": "Anexo X (Medicamentos) do RICMS/MT"},
    "52": {"UF": "GO", "Construcao_ST": "Anexo VIII do RCTE/GO", "Medicamento_ST": "Anexo VIII (Produtos Farmacêuticos) do RCTE/GO"},
    "53": {"UF": "DF", "Construcao_ST": "Anexo IV do RICMS/DF", "Medicamento_ST": "Caderno I do Anexo IV (Medicamentos) do RICMS/DF"}
}

# --- FUNÇÃO PARA GERAR O ARQUIVO PDF ---
def gerar_pdf_relatorio(dataframe):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20, title="Relatorio_PGDAS")
    story = []
    
    styles = getSampleStyleSheet()
    style_titulo = ParagraphStyle('TituloStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#1C3D5A'), alignment=1)
    style_texto = ParagraphStyle('TextoStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10)
    style_header = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)

    story.append(Paragraph("RELATÓRIO CONSOLIDADO DE AUDITORIA DE LANÇAMENTOS - PGDAS-D", style_titulo))
    story.append(Spacer(1, 15))
    
    colunas_pdf = ["Nota No.", "UF", "Produto", "NCM", "ICMS PGDAS", "PIS/COFINS PGDAS", "Status XML"]
    
    dados_tabela = [[Paragraph(col, style_header) for col in colunas_pdf]]
    
    for idx, row in dataframe.iterrows():
        linha = [
            Paragraph(str(row["Nota No."]), style_texto),
            Paragraph(str(row["UF"]), style_texto),
            Paragraph(str(row["Produto"]), style_texto),
            Paragraph(str(row["NCM"]), style_texto),
            Paragraph(str(row["ICMS PGDAS (Correto)"]), style_texto),
            Paragraph(str(row["PIS/COFINS PGDAS (Correto)"]), style_texto),
            Paragraph(str(row["Status XML"]), style_texto)
        ]
        dados_tabela.append(linha)
    
    # Criando a tabela sem larguras estáticas - O ReportLab calcula automaticamente
    tabela_pdf = Table(dados_tabela)
    
    tabela_pdf.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1C3D5A')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')])
    ]))
    
    story.append(tabela_pdf)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# --- FUNÇÃO DE AUDITORIA CRÍTICA DE XML ---
def auditoria_lote_divergencias(xml_files):
    todos_produtos = []
    
    for xml_file in xml_files:
        try:
            xml_data = xml_file.read()
            root = ET.fromstring(xml_data)
            
            cod_uf = "35"
            for elem in root.iter():
                if elem.tag.endswith('cUF'):
                    cod_uf = elem.text
                    break
                    
            config_uf = MATRIZ_ESTADUAL_ICMS.get(cod_uf, {"UF": "BR", "Construcao_ST": "Regulamento Local", "Medicamento_ST": "Regulamento Local"})
            uf_nome = config_uf["UF"]
            
            numero_nfe = "Não Encontrado"
            for elem in root.iter():
                if elem.tag.endswith('nNF'):
                    numero_nfe = elem.text
                    break
            
            for det in root.iter():
                if det.tag.endswith('det'):
                    xProd = "Desconhecido"
                    ncm = ""
                    cst_xml = "00"
                    
                    for elem in det.iter():
                        if elem.tag.endswith('xProd'):
                            xProd = elem.text
                        if elem.tag.endswith('NCM'):
                            ncm = elem.text
                    
                    for elem in det.iter():
                        if elem.tag.endswith('CST') or elem.tag.endswith('CSOSN'):
                            cst_xml = elem.text
                            break
                    
                    grupo_4d = ncm[:4] if ncm else ""
                    
                    if grupo_4d in ["3002", "3003", "3004", "3005", "3006"] or ncm.startswith("40141000"):
                        regra_icms = "ST"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = config_uf["Medicamento_ST"]
                        base_federal = "Tabela 4.3.10 SPED (Cód. 102 / Lei 10.147)"
                        
                    elif grupo_4d in ["8708", "4011", "8407", "8408", "8409"]:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = f"Regime Regular / Alíquota Interna"
                        base_federal = "Tabela 4.3.10 SPED (Cód. 103 / Lei 10.485)"
                        
                    elif grupo_4d in ["2203", "2202"]:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "MONOFÁSICO"
                        base_icms = f"Regime Regular / Alíquota Interna"
                        base_federal = "Tabela 4.3.10 SPED (Cód. 104 / Lei 13.097)"
                        
                    elif grupo_4d in ["3917", "8481", "8536", "7307", "6910", "7412", "7308", "3214", "2523"]:
                        regra_icms = "ST"
                        regra_pis_cofins = "NORMAL"
                        base_icms = config_uf["Construcao_ST"]
                        base_federal = "Regime Geral (PIS/COFINS Não Monofásico)"
                        
                    else:
                        regra_icms = "NORMAL"
                        regra_pis_cofins = "NORMAL"
