import os
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
from typing import Dict, List, Any

# Configuração da página Streamlit
st.set_page_config(page_title="Auditor Fiscal de XMLs", layout="wide")

class AuditarXMLFiscal:
    """Engine de Auditoria Fiscal de NFe em lote."""
    NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

    def __init__(self, matriz_tributaria: Dict[str, Dict[str, Any]]):
        self.matriz_tributaria = matriz_tributaria

    def extrair_dados_xml_conteudo(self, conteudo_bytes: bytes, nome_arquivo: str) -> List[Dict[str, Any]]:
        itens = []
        try:
            root = ET.fromstring(conteudo_bytes)
            
            if root.tag.endswith('nfeProc'):
                infNfe = root.find('.//nfe:infNFe', self.NS)
            elif root.tag.endswith('NFe'):
                infNfe = root.find('.//nfe:infNFe', self.NS)
            else:
                infNfe = root
                
            if infNfe is None:
                return [{'arquivo': nome_arquivo, 'erro_xml': 'Estrutura de XML NFe inválida'}]

            ide = infNfe.find('nfe:ide', self.NS)
            uf_emit = infNfe.find('.//nfe:emit/nfe:enderEmit/nfe:UF', self.NS)
            uf_dest = infNfe.find('.//nfe:dest/nfe:enderDest/nfe:UF', self.NS)
            
            uf_origem = uf_emit.text if uf_emit is not None else ''
            uf_destino = uf_dest.text if uf_dest is not None else ''
            num_nota = ide.find('nfe:nNF', self.NS).text if ide is not None and ide.find('nfe:nNF', self.NS) is not None else 'N/A'

            for det in infNfe.findall('nfe:det', self.NS):
                num_item = det.attrib.get('nItem', '1')
                prod = det.find('nfe:prod', self.NS)
                imposto = det.find('nfe:imposto', self.NS)
                
                ncm = prod.find('nfe:NCM', self.NS).text if prod.find('nfe:NCM', self.NS) is not None else ''
                descricao = prod.find('nfe:xProd', self.NS).text if prod.find('nfe:xProd', self.NS) is not None else ''
                
                cst_pis, cst_cofins, cst_icms = '', '', ''
                
                if imposto is not None:
                    pis = imposto.find('.//nfe:PIS', self.NS)
                    if pis is not None and len(pis) > 0:
                        cst_pis_el = pis[0].find('nfe:CST', self.NS)
                        cst_pis = cst_pis_el.text if cst_pis_el is not None else ''
                    
                    cofins = imposto.find('.//nfe:COFINS', self.NS)
                    if cofins is not None and len(cofins) > 0:
                        cst_cofins_el = cofins[0].find('nfe:CST', self.NS)
                        cst_cofins = cst_cofins_el.text if cst_cofins_el is not None else ''
                        
                    icms = imposto.find('.//nfe:ICMS', self.NS)
                    if icms is not None and len(icms) > 0:
                        cst_icms_el = icms[0].find('nfe:CST', self.NS)
                        if cst_icms_el is None:
                            cst_icms_el = icms[0].find('nfe:CSOSN', self.NS)
                        cst_icms = cst_icms_el.text if cst_icms_el is not None else ''

                itens.append({
                    'arquivo': nome_arquivo,
                    'numero_nota': num_nota,
                    'uf_origem': uf_origem,
                    'uf_destino': uf_destino,
                    'item': num_item,
                    'descricao': descricao,
                    'ncm': ncm,
                    'cst_pis_informado': cst_pis,
                    'cst_cofins_informado': cst_cofins,
                    'cst_icms_informado': cst_icms,
                    'erro_xml': ''
                })

        except ET.ParseError:
            return [{'arquivo': nome_arquivo, 'erro_xml': 'Arquivo XML corrompido ou malformado'}]
        except Exception as e:
            return [{'arquivo': nome_arquivo, 'erro_xml': f'Erro ao processar: {str(e)}'}]
            
        return itens

    def auditar_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if item.get('erro_xml'):
            item['status_auditoria'] = 'ERRO_XML'
            item['inconsistencias'] = item['erro_xml']
            return item

        ncm = item['ncm']
        inconsistencias = []
        regra_fiscal = self.matriz_tributaria.get(ncm)

        if not regra_fiscal:
            item['status_auditoria'] = 'NCM_NAO_MAPEADA'
            item['inconsistencias'] = 'NCM não localizado na base legal de referência.'
            item['legislacao_aplicavel'] = 'N/A'
            item['tributacao_correta'] = 'N/A'
            return item

        if regra_fiscal.get('is_monofasico'):
            cst_pis_esperado = regra_fiscal.get('cst_pis_correto', '04')
            if item['cst_pis_informado'] != cst_pis_esperado:
                inconsistencias.append(
                    f"PIS Incorreto: Informado CST {item['cst_pis_informado']}, esperado CST {cst_pis_esperado} (Monofásico)."
                )

        if regra_fiscal.get('tem_st'):
            cst_icms_esperado = regra_fiscal.get('cst_icms_correto', '60')
            if item['cst_icms_informado'] != cst_icms_esperado:
                inconsistencias.append(
                    f"ICMS ST Incorreto: Informado CST {item['cst_icms_informado']}, esperado CST {cst_icms_esperado} (ST)."
                )

        if inconsistencias:
            item['status_auditoria'] = 'INCONSISTENTE'
            item['inconsistencias'] = ' | '.join(inconsistencias)
            item['legislacao_aplicavel'] = regra_fiscal.get('base_legal', 'Não especificada')
            item['tributacao_correta'] = (
                f"PIS/COFINS CST {regra_fiscal.get('cst_pis_correto')}, "
                f"ICMS CST {regra_fiscal.get('cst_icms_correto')} ({regra_fiscal.get('descricao_regra')})"
            )
        else:
            item['status_auditoria'] = 'CONFORME'
            item['inconsistencias'] = 'Nenhuma'
            item['legislacao_aplicavel'] = regra_fiscal.get('base_legal', 'Em conformidade')
            item['tributacao_correta'] = 'Tributação declarada corretamente'

        return item


# Matriz Tributária Exemplo
MATRIZ_LEGISLECAO = {
    '22021000': {
        'is_monofasico': True, 'cst_pis_correto': '04', 'tem_st': True, 'cst_icms_correto': '60',
        'base_legal': 'Lei 10.833/2003 Art. 1º / Convênio ICMS 142/2018',
        'descricao_regra': 'Monofásico PIS/COFINS e ICMS ST'
    },
    '30049099': {
        'is_monofasico': True, 'cst_pis_correto': '04', 'tem_st': False, 'cst_icms_correto': '00',
        'base_legal': 'Lei 10.147/2000 Art. 1º',
        'descricao_regra': 'Produtos farmacêuticos Monofásicos'
    },
    '87082990': {
        'is_monofasico': False, 'cst_pis_correto': '01', 'tem_st': True, 'cst_icms_correto': '60',
        'base_legal': 'Convênio ICMS 109/08',
        'descricao_regra': 'Autopeças com ICMS ST'
    }
}

# --- INTERFACE STREAMLIT ---
st.title("📊 Auditor Fiscal de XMLs NF-e em Lote")

st.markdown("Faça o upload dos arquivos **.XML** para auditar Monofásico, ST e tributações vigentes.")

arquivos_carregados = st.file_uploader("Selecione os arquivos XML", type=["xml"], accept_multiple_files=True)

if arquivos_carregados:
    auditor = AuditarXMLFiscal(matriz_tributaria=MATRIZ_LEGISLECAO)
    resultado_final = []

    for arq in arquivos_carregados:
        conteudo = arq.read()
        itens = auditor.extrair_dados_xml_conteudo(conteudo, arq.name)
        for item in itens:
            resultado_final.append(auditor.auditar_item(item))

    df_resultado = pd.DataFrame(resultado_final)

    st.subheader("Resultados da Auditoria")
    st.dataframe(df_resultado, use_container_width=True)

    # Botão para Baixar Excel
    excel_bytes = pd.ExcelWriter("relatorio.xlsx", engine="openpyxl")
    df_resultado.to_excel(excel_bytes, index=False)
    excel_bytes.close()

    with open("relatorio.xlsx", "rb") as f:
        st.download_button(
            label="📥 Baixar Relatório em Excel",
            data=f.read(),
            file_name="Relatorio_Auditoria_Fiscal.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
