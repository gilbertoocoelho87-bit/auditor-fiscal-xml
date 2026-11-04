import os
import xml.etree.ElementTree as ET
import pandas as pd

# ==============================================================================
# 1. BANCO DE DADOS TRIBUTÁRIO EXPANDIDO (BASEADO NO DIAGNÓSTICO DA IMAGEM)
# ==============================================================================

# Simulação da base de dados de Legislação por NCM e UF (Exemplo: PE)
base_legislacao = pd.DataFrame([
    {
        "NCM": "62046900",
        "UF": "PE",
        "Descricao_NCM": "Fatos de treino, macacões, calças, jardineiras, bermudas e shorts - De outras matérias têxteis",
        "Regime_ICMS": "NORMAL",
        "Aliquota_Interna": 20.5,
        "Aliquota_Inter_Nordeste": 7.0,
        "Aliquota_Inter_SulSudeste": 12.0,
        
        # Dados de Entrada
        "CFOP_Entrada_Int": "1102",
        "CFOP_Entrada_Inter": "2102",
        "CST_ICMS_Entrada": "000",
        "Texto_Entrada": "Direito ao crédito pelo valor destacado no documento fiscal. Sujeito a eventual antecipação sem substituição tributária (Decreto nº 44.650/2017).",
        
        # Dados de Saída
        "CFOP_Saida_Int": "5102",
        "CFOP_Saida_Inter": "6102",
        "CST_ICMS_Saida": "000",
        "Texto_Saida": "Produto não sujeito à Substituição Tributária em Pernambuco. Tributado pela sistemática normal de débito e crédito.",
        
        # PIS/COFINS (Regime Cumulativo conforme imagem)
        "PIS_Regime": "Cumulativo",
        "PIS_Aliquota": 0.65,
        "COFINS_Aliquota": 3.00,
        "PIS_CST": "01",
        "PIS_Lei": "Lei nº 9.718/1998",
        
        # IPI
        "IPI_Aliquota": 0.0,
        "IPI_Decreto": "Decreto Federal nº 11.158/2022 (TIPI)",
        
        # Alertas e Fundamentos
        "Alertas": (
            "1. Alíquota modal em PE é de 20,5% (Lei 18.305/2023).\n"
            "2. Verificar enquadramento no PRODEPE ou regime especial do Polo Têxtil.\n"
            "3. PIS/COFINS apurados pelo regime cumulativo para empresas no Lucro Presumido."
        ),
        "Fundamentos_Legais": (
            "- Majoração da Alíquota Básica do ICMS-PE: Lei nº 18.305/2023\n"
            "- Regulamento do ICMS de Pernambuco: Decreto nº 44.650/2017\n"
            "- Tabela de Incidência do IPI (TIPI): Decreto Federal nº 11.158/2022\n"
            "- Regime Cumulativo: Lei Federal nº 9.718/1998"
        )
    }
])

# ==============================================================================
# 2. LEITURA E PARSING DO XML
# ==============================================================================
def analisar_xml_nfe(caminho_xml):
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        ns = {'ns': 'http://portalfiscal.inf.br'}
        
        # Identificação da UF do Destinatário / Operação
        dest = root.find('.//ns:dest/ns:enderDest/ns:UF', ns)
        uf_destino = dest.text if dest is not None else "PE"
        
        emit = root.find('.//ns:emit/ns:enderEmit/ns:UF', ns)
        uf_origem = emit.text if emit is not None else "PE"
        
        itens_auditados = []
        
        for det in root.findall('.//ns:det', ns):
            n_item = det.attrib.get('nItem')
            prod = det.find('ns:prod', ns)
            
            c_prod = prod.find('ns:cProd', ns).text
            x_prod = prod.find('ns:xProd', ns).text
            ncm = prod.find('ns:NCM', ns).text
            cfop_emitido = prod.find('ns:CFOP', ns).text
            
            itens_auditados.append({
                "Item": n_item,
                "Codigo": c_prod,
                "Descricao_Emitida": x_prod,
                "NCM": ncm,
                "CFOP_Emitido": cfop_emitido,
                "UF_Origem": uf_origem,
                "UF_Destino": uf_destino,
                "Arquivo": os.path.basename(caminho_xml)
            })
        return itens_auditados
    except Exception as e:
        print(f"Erro ao processar {caminho_xml}: {e}")
        return []

# ==============================================================================
# 3. MOTOR DE AUDITORIA (CHECK DE CONFORMIDADE)
# ==============================================================================
def auditoria_fiscal(produtos_xml):
    df_xml = pd.DataFrame(produtos_xml)
    if df_xml.empty:
        return df_xml
        
    # Cruza o XML com a Base Regulatória usando NCM e UF de Destino
    df_resultado = pd.merge(
        df_xml, 
        base_legislacao, 
        left_on=["NCM", "UF_Destino"], 
        right_on=["NCM", "UF"], 
        how="left"
    )
    
    # Determina o CFOP correto esperado baseado no tipo de operação (Exemplo simplificado de Saída)
    def validar_cfop(row):
        if pd.isna(row['Regime_ICMS']):
            return "NCM/UF não mapeado na base regulatória."
            
        is_interstadual = row['UF_Origem'] != row['UF_Destino']
        cfop_correto = row['CFOP_Saida_Inter'] if is_interstadual else row['CFOP_Saida_Int']
        
        if row['CFOP_Emitido'] != cfop_correto:
            return f"ERRO: Emitido {row['CFOP_Emitido']}. O correto para esta operação é {cfop_correto}."
        return "CFOP CORRETO"

    df_resultado['Validacao_CFOP'] = df_resultado.apply(validar_cfop, axis=1)
    return df_resultado

# ==============================================================================
# 4. EXECUÇÃO DO PROCESSO EM LOTE
# ==============================================================================
def processar_pasta(pasta):
    todos_itens = []
    if not os.path.exists(pasta):
        os.makedirs(pasta)
        print(f"Pasta '{pasta}' criada. Adicione arquivos XML para análise.")
        return

    for arquivo in os.listdir(pasta):
        if arquivo.endswith('.xml'):
            itens = analisar_xml_nfe(os.path.join(pasta, arquivo))
            todos_itens.extend(itens)
            
    if todos_itens:
        relatorio = auditoria_fiscal(todos_itens)
        
        # Exibição estruturada dos diagnósticos encontrados
        for idx, row in relatorio.iterrows():
            print(f"\n{'='*60}")
            print(f"ARQUIVO: {row['Arquivo']} | ITEM: {row['Item']} | NCM: {row['NCM']}")
            print(f"Produto: {row['Descricao_Emitida']}")
            print(f"{'-'*60}")
            print(f"Status CFOP: {row['Validacao_CFOP']}")
            print(f"Regime ICMS na UF ({row['UF_Destino']}): {row['Regime_ICMS']} (Alíquota Interna: {row['Aliquota_Interna']}%)")
            print(f"\n[ALERTAS]:\n{row['Alertas']}")
            print(f"\n[FUNDAMENTOS LEGAIS]:\n{row['Fundamentos_Legais']}")
        
        relatorio.to_excel("diagnostico_fiscal_completo.xlsx", index=False)
        print(f"\n{'='*60}\n[Sucesso] Planilha gerada com todos os blocos informativos.")
    else:
        print("Nenhum XML encontrado.")

if __name__ == "__main__":
    processar_pasta("./notas_fiscais")
