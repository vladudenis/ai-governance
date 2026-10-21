"""Small Formex and branch-notice documents for ingestion tests."""

import io
import zipfile

NOTICE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<NOTICE decoding="eng" type="branch">
  <WORK>
    <URI>
      <VALUE>http://publications.europa.eu/resource/cellar/work</VALUE>
      <IDENTIFIER>work</IDENTIFIER>
      <TYPE>cellar</TYPE>
    </URI>
    <ID_CELEX type="data"><VALUE>32024R1689</VALUE></ID_CELEX>
    <ELI type="data"><VALUE>http://data.europa.eu/eli/reg/2024/1689/oj</VALUE></ELI>
    <WORK_DATE_DOCUMENT type="date"><VALUE>2024-06-13</VALUE></WORK_DATE_DOCUMENT>
    <DATE_PUBLICATION type="date"><VALUE>2024-07-12</VALUE></DATE_PUBLICATION>
    <TITLE type="data"><VALUE>ARTIFICIAL INTELLIGENCE ACT</VALUE></TITLE>
    <WORK_HAS_RESOURCE-TYPE type="concept">
      <URI><IDENTIFIER>REG</IDENTIFIER><TYPE>resource-type</TYPE></URI>
    </WORK_HAS_RESOURCE-TYPE>
    <RESOURCE_LEGAL_AMENDS_RESOURCE_LEGAL type="link">
      <SAMEAS><URI><IDENTIFIER>32013R0167</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_AMENDS_RESOURCE_LEGAL>
    <RESOURCE_LEGAL_AMENDED_BY_RESOURCE_LEGAL type="link">
      <SAMEAS><URI><IDENTIFIER>32026R1744</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_AMENDED_BY_RESOURCE_LEGAL>
    <RESOURCE_LEGAL_AMENDMENT_PROPOSED_BY_RESOURCE_LEGAL type="link">
      <SAMEAS><URI><IDENTIFIER>52025PC0836</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_AMENDMENT_PROPOSED_BY_RESOURCE_LEGAL>
    <RESOURCE_LEGAL_CONSOLIDATED_BY_ACT_CONSOLIDATED type="link">
      <SAMEAS><URI><IDENTIFIER>02024R1689-20260727</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_CONSOLIDATED_BY_ACT_CONSOLIDATED>
    <RESOURCE_LEGAL_CONSOLIDATED_BY_ACT_CONSOLIDATED type="link">
      <SAMEAS><URI><IDENTIFIER>02013R0167-20260802</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_CONSOLIDATED_BY_ACT_CONSOLIDATED>
    <RESOURCE_LEGAL_BASIS_FOR_ACT_CONSOLIDATED type="link">
      <SAMEAS><URI><IDENTIFIER>2024R1689/20240712</IDENTIFIER><TYPE>consolidation</TYPE></URI></SAMEAS>
    </RESOURCE_LEGAL_BASIS_FOR_ACT_CONSOLIDATED>
  </WORK>
  <EXPRESSION>
    <URI>
      <VALUE>http://publications.europa.eu/resource/cellar/work.0006</VALUE>
      <IDENTIFIER>work.0006</IDENTIFIER>
      <TYPE>cellar</TYPE>
    </URI>
    <EXPRESSION_USES_LANGUAGE type="concept"><IDENTIFIER>ENG</IDENTIFIER></EXPRESSION_USES_LANGUAGE>
    <EXPRESSION_BELONGS_TO_WORK type="link">
      <SAMEAS><URI><IDENTIFIER>32024R1689</IDENTIFIER><TYPE>celex</TYPE></URI></SAMEAS>
    </EXPRESSION_BELONGS_TO_WORK>
  </EXPRESSION>
  <MANIFESTATION manifestation-type="fmx4">
    <URI>
      <VALUE>http://publications.europa.eu/resource/cellar/work.0006.02</VALUE>
      <IDENTIFIER>work.0006.02</IDENTIFIER>
      <TYPE>cellar</TYPE>
    </URI>
    <MANIFESTATION_MANIFESTS_EXPRESSION type="link">
      <URI><VALUE>http://publications.europa.eu/resource/cellar/work.0006</VALUE></URI>
    </MANIFESTATION_MANIFESTS_EXPRESSION>
  </MANIFESTATION>
</NOTICE>
"""

ACT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ACT xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:noNamespaceSchemaLocation="http://formex.publications.europa.eu/schema/formex-06.02.1-20231031.xd">
  <BIB.INSTANCE>
    <DOCUMENT.REF><COLL>L</COLL></DOCUMENT.REF>
    <LG.DOC>EN</LG.DOC>
    <DATE ISO="20240613">13 June 2024</DATE>
    <NO.DOC><YEAR>2024</YEAR><NO.CURRENT>1689</NO.CURRENT></NO.DOC>
  </BIB.INSTANCE>
  <TITLE><TI><P>Regulation (EU) 2024/1689</P></TI><STI><P>Sample title</P></STI></TITLE>
  <PREAMBLE>
    <PREAMBLE.INIT><P>THE EUROPEAN PARLIAMENT AND THE COUNCIL,</P></PREAMBLE.INIT>
    <GR.VISA>
      <VISA>Having regard to the Treaty<NOTE NOTE.ID="E0001"><P>OJ C 1.</P></NOTE>,</VISA>
    </GR.VISA>
    <GR.CONSID>
      <CONSID><NP><NO.P>(1)</NO.P><TXT>The purpose is sample text about the <QUOT.START/>Charter<QUOT.END/>.</TXT></NP></CONSID>
    </GR.CONSID>
  </PREAMBLE>
  <ENACTING.TERMS>
    <DIVISION>
      <TITLE><TI><P>CHAPTER I</P></TI><STI><P>GENERAL PROVISIONS</P></STI></TITLE>
      <ARTICLE>
        <TI.ART>Article 1</TI.ART>
        <STI.ART><P>Subject matter</P></STI.ART>
        <PARAG IDENTIFIER="001.001">
          <NO.PARAG>1.</NO.PARAG>
          <ALINEA>
            <P>This Regulation lays down:</P>
            <LIST>
              <ITEM><NP><NO.P>(a)</NO.P><TXT>harmonised rules;</TXT></NP></ITEM>
              <ITEM><NP><NO.P>(h)</NO.P><TXT>point h intro
                <LIST><ITEM><NP><NO.P>(iii)</NO.P><TXT>nested point iii.</TXT></NP></ITEM></LIST>
              </TXT></NP></ITEM>
            </LIST>
          </ALINEA>
          <ALINEA><P>Second subparagraph sample.</P></ALINEA>
        </PARAG>
      </ARTICLE>
    </DIVISION>
  </ENACTING.TERMS>
  <FINAL><P>Done at Brussels.</P></FINAL>
</ACT>
"""

ANNEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ANNEX>
  <BIB.INSTANCE>
    <LG.DOC>EN</LG.DOC>
    <NO.DOC><YEAR>2024</YEAR><NO.CURRENT>1689</NO.CURRENT></NO.DOC>
  </BIB.INSTANCE>
  <TITLE><TI><P>ANNEX III</P></TI><STI><P>High-risk sample</P></STI></TITLE>
  <CONTENTS>
    <P>Intro paragraph
      <LIST>
        <ITEM><NP><NO.P>(1)</NO.P><TXT>First annex point.</TXT></NP></ITEM>
      </LIST>
    </P>
  </CONTENTS>
</ANNEX>
"""


def formex_zip(*, act: str = ACT_XML, annex: str | None = ANNEX_XML) -> bytes:
    """Pack Formex XML the way CELLAR returns an fmx4 manifestation."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("L_sample.toc.fmx.xml", "<PUBLICATION><OJ/></PUBLICATION>")
        archive.writestr("L_sample.000101.fmx.xml", act)
        if annex is not None:
            archive.writestr("L_sample.annex.fmx.xml", annex)
    return buffer.getvalue()
