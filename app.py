import os
import glob
import xml.etree.ElementTree as ET
import pandas as pd
from typing import Dict, List, Any

class AuditarXMLFiscal:
    """
    Engine de Auditoria Fiscal de NFe em lote.
    Valida NCM, CST/CSOSN, PIS/COFINS Monofásico, ICMS ST e inconsistências tributárias.
    """
    
    # Namespace padrão da NF-e (Ajustar conforme versão)
    NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

    def __init__(self, matriz_tributaria: Dict[str, Dict[str, Any]]):
        """
        :param matriz_tributaria: Dicionário contendo as regras por NCM e Legislação.
        """
        self.matriz_tributaria = matriz_tributaria

    def extrair_dados_xml(self, caminho_xml: str) -> List[Dict[str, Any]]:
        """Abre o XML, trata erros de estrutura e extrai os itens para análise."""
        itens = []
        nome_arquivo = os.path.basename(caminho_xml)
        
        try:
            tree = ET.parse(caminho_xml)
            root = tree.getroot()
            
            # Trata se o XML possui nó NFe ou nfeProc
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

            # Iterar sobre os itens da nota (det)
            for det in infNfe.findall('nfe:det', self.NS):
                num_item = det.attrib.get('nItem', '1')
                prod = det.find('nfe:prod', self.NS)
                imposto = det.find('nfe:imposto', self.NS)
                
                ncm = prod.find('nfe:NCM', self.NS).text if prod.find('nfe:NCM', self.NS) is not None else ''
                descricao = prod.find('nfe:xProd', self.NS).text if prod.find('nfe:xProd', self.NS) is not None else ''
                
                # Extrair Tributos Informados na Nota
                cst_pis, cst_cofins, cst_icms = '', '', ''
                
                if imposto is not None:
                    # PIS
                    pis = imposto.find('.//nfe:PIS', self.NS)
                    if pis is not None and len(pis) > 0:
                        cst_pis_el = pis[0].find('nfe:CST', self.NS)
                        cst_pis = cst_pis_el.text if cst_pis_el is not None else ''
                    
                    # COFINS
                    cofins = imposto.find('.//nfe:COFINS', self.NS)
                    if cofins is not None and len(cofins) > 0:
                        cst_cofins_el = cofins[0].find('nfe:CST', self.NS)
                        cst_cofins = cst_cofins_el.text if cst_cofins_el is not None else ''
                        
                    # ICMS
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
        """Aplica regras fiscais comparando informado x esperado segundo a legislação."""
        if item.get('erro_xml'):
            item['status_auditoria'] = 'ERRO_XML'
            item['inconsistencias'] = item['erro_xml']
            return item

        ncm = item['ncm']
        inconsistencias = []
        
        # Consulta a base legal referente ao NCM do produto
        regra_fiscal = self.matriz_tributaria.get(ncm)

        if not regra_fiscal:
            item['status_auditoria'] = 'NCM_NAO_MAPEADA'
            item['inconsistencias'] = 'NCM não localizado na base legal de referência.'
            item['legislacao_aplicavel'] = 'N/A'
            item['tributacao_correta'] = 'N/A'
            return item

        # 1. Auditoria Monofásico (PIS/COFINS)
        if regra_fiscal.get('is_monofasico'):
            cst_pis_esperado = regra_fiscal.get('cst_pis_correto', '04')
            if item['cst_pis_informado'] != cst_pis_esperado:
                inconsistencias.append(
                    f"PIS Incorreto: Informado CST {item['cst_pis_informado']}, esperado CST {cst_pis_esperado} (Monofásico)."
                )

        # 2. Auditoria de ICMS Substituição Tributária (ST)
        if regra_fiscal.get('tem_st'):
            cst_icms_esperado = regra_fiscal.get('cst_icms_correto', '60')
            if item['cst_icms_informado'] != cst_icms_esperado:
                inconsistencias.append(
                    f"ICMS ST Incorreto: Informado CST {item['cst_icms_informado']}, esperado CST {cst_icms_esperado} (ST)."
                )

        # Resultado da Auditoria
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

    def processar_lote(self, pasta_xmls: str) -> pd.DataFrame:
        """Executa a importação em lote de todos os XMLs de um diretório."""
        arquivos_xml = glob.glob(os.path.join(pasta_xmls, "*.xml"))
        resultado_final = []

        print(f"Iniciando processamento de {len(arquivos_xml)} arquivos XML...")

        for caminho in arquivos_xml:
            itens_xml = self.extrair_dados_xml(caminho)
            for item in itens_xml:
                item_auditado = self.auditar_item(item)
                resultado_final.append(item_auditado)

        df_relatorio = pd.DataFrame(resultado_final)
        return df_relatorio


# ==========================================
# EXEMPLO DE USO COM BASE LEGAL DE REFERÊNCIA
# ==========================================
if __name__ == "__main__":
    
    # Exemplo de Matriz Tributária (Regras por NCM com Fundamentação Legal)
    MATRIZ_LEGISLECAO_EXEMPLO = {
        # Bebidas / Refrigerantes (Monofásico de PIS/COFINS + ICMS ST)
        '22021000': {
            'is_monofasico': True,
            'cst_pis_correto': '04',
            'tem_st': True,
            'cst_icms_correto': '60',
            'base_legal': 'Lei 10.833/2003 Art. 1º / Convênio ICMS 142/2018',
            'descricao_regra': 'Sujeito à incidência Monofásica de PIS/COFINS e Substituição Tributária de ICMS'
        },
        # Medicamentos (Monofásico de PIS/COFINS)
        '30049099': {
            'is_monofasico': True,
            'cst_pis_correto': '04',
            'tem_st': False,
            'cst_icms_correto': '00',
            'base_legal': 'Lei 10.147/2000 Art. 1º',
            'descricao_regra': 'Produtos farmacêuticos sujeitos à alíquota zero/monofásica'
        },
        # Peças automotivas (ICMS ST)
        '87082990': {
            'is_monofasico': False,
            'cst_pis_correto': '01',
            'tem_st': True,
            'cst_icms_correto': '60',
            'base_legal': 'Convênio ICMS 109/08 e legislação estadual correlata',
            'descricao_regra': 'Autopeças sujeitas à Substituição Tributária'
        }
    }

    # Instancia o auditor com a base tributária
    auditor = AuditarXMLFiscal(matriz_tributaria=MATRIZ_LEGISLECAO_EXEMPLO)

    # Pasta onde os arquivos .xml se encontram
    PASTA_INPUT_XML = "./xmls_entrada"

    # Criar diretório de teste caso não exista
    if not os.path.exists(PASTA_INPUT_XML):
        os.makedirs(PASTA_INPUT_XML)
        print(f"Diretório '{PASTA_INPUT_XML}' criado. Coloque seus arquivos XML nele e execute novamente.")
    else:
        # Processar os arquivos
        df_resultado = auditor.processar_lote(PASTA_INPUT_XML)
        
        # Exibe no console
        print("\n--- RESUMO DA AUDITORIA FISCAL ---")
       # Colunas desejadas para exibição
colunas_desejadas = ['numero_nota', 'ncm', 'status_auditoria', 'inconsistencias', 'legislacao_aplicavel']

# Filtra apenas as colunas que realmente existem no DataFrame
colunas_existentes = [col for col in colunas_desejadas if col in df_resultado.columns]

if not df_resultado.empty and colunas_existentes:
    print(df_resultado[colunas_existentes])
else:
    print("Nenhum dado válido ou XML foi encontrado para auditoria.")

        # Salva o resultado detalhado em um arquivo Excel para análise profissional
        # Exibe no console se houver colunas válidas
        colunas_desejadas = ['numero_nota', 'ncm', 'status_auditoria', 'inconsistencias', 'legislacao_aplicavel']
        colunas_existentes = [col for col in colunas_desejadas if col in df_resultado.columns]
        
        if not df_resultado.empty and colunas_existentes:
            print(df_resultado[colunas_existentes])

        # Linha 238 corrigida (alinhada exatamente com o mesmo recuo do 'else')
        caminho_excel = "Relatorio_Auditoria_Fiscal_XML.xlsx"
        df_resultado.to_excel(caminho_excel, index=False)
        print(f"\nRelatório final gerado com sucesso em: {caminho_excel}")
        df_resultado.to_excel(caminho_excel, index=False)
        print(f"\nRelatório final gerado com sucesso em: {caminho_excel}")
