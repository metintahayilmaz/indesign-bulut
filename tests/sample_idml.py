"""Testler ve demo için küçük ama gerçekçi bir IDML paketi üretir.

    python3 tests/sample_idml.py ornek.idml
"""
import sys

from idmlkit.package import MIMETYPE, to_bytes

NS = 'xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"'
HDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

DESIGNMAP = HDR + f'''<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="18.0(56)" ?>
<Document {NS} DOMVersion="18.0" Self="d">
  <idPkg:Spread src="Spreads/Spread_u100.xml"/>
  <idPkg:Story src="Stories/Story_u200.xml"/>
  <idPkg:Story src="Stories/Story_u300.xml"/>
</Document>
'''

SPREAD = HDR + f'''<idPkg:Spread {NS} DOMVersion="18.0">
  <Spread Self="u100"><Page Self="u101" Name="1"/>
    <TextFrame Self="u110" ParentStory="u200"/><TextFrame Self="u111" ParentStory="u300"/>
  </Spread>
</idPkg:Spread>
'''

STORY_1 = HDR + f'''<idPkg:Story {NS} DOMVersion="18.0">
  <Story Self="u200" AppliedTOCStyle="n">
    <StoryPreference OpticalMarginAlignment="false"/>
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Başlık">
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
        <Content>Bahar Kataloğu</Content>
        <Br/>
      </CharacterStyleRange>
    </ParagraphStyleRange>
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Gövde">
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
        <Content>Yeni sezon ürünleri </Content>
      </CharacterStyleRange>
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/Kalın">
        <Content>şimdi</Content>
      </CharacterStyleRange>
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
        <Content> mağazalarda.</Content>
        <Br/>
        <Content>Fiyatlar &amp; kampanyalar için tabloya bakın:</Content>
        <Table Self="u250" BodyRowCount="1" ColumnCount="2">
          <Row Self="u250r0" Name="0"/><Column Self="u250c0" Name="0"/><Column Self="u250c1" Name="1"/>
          <Cell Self="u250i0" Name="0:0">
            <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Tablo">
              <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content>Ürün</Content></CharacterStyleRange>
            </ParagraphStyleRange>
          </Cell>
          <Cell Self="u250i1" Name="1:0">
            <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Tablo">
              <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"><Content>Fiyat</Content></CharacterStyleRange>
            </ParagraphStyleRange>
          </Cell>
        </Table>
        <Br/>
      </CharacterStyleRange>
    </ParagraphStyleRange>
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Altbilgi">
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
        <Content>Sayfa </Content>
        <Content><?ACE 18?></Content>
        <Content> / katalog</Content>
      </CharacterStyleRange>
    </ParagraphStyleRange>
  </Story>
</idPkg:Story>
'''

STORY_2 = HDR + f'''<idPkg:Story {NS} DOMVersion="18.0">
  <Story Self="u300">
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Gövde">
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">
        <HyperlinkTextSource Self="u310" Name="web">
          <Content>www.ornek.com</Content>
        </HyperlinkTextSource>
        <Content> adresini ziyaret edin.</Content>
      </CharacterStyleRange>
    </ParagraphStyleRange>
  </Story>
</idPkg:Story>
'''


def sample_files() -> dict[str, bytes]:
    return {
        "mimetype": MIMETYPE,
        "designmap.xml": DESIGNMAP.encode(),
        "Spreads/Spread_u100.xml": SPREAD.encode(),
        "Stories/Story_u200.xml": STORY_1.encode(),
        "Stories/Story_u300.xml": STORY_2.encode(),
        "META-INF/container.xml": (HDR + '<container/>').encode(),
    }


def sample_bytes() -> bytes:
    return to_bytes(sample_files())


if __name__ == "__main__":
    open(sys.argv[1] if len(sys.argv) > 1 else "ornek.idml", "wb").write(sample_bytes())


# --- Dergi şablonu (tasarım testleri için) -----------------------------------
T_DESIGNMAP = HDR + f'''<Document {NS} DOMVersion="18.0" Self="d">
  <Layer Self="ul1" Name="Metin"/><Layer Self="ul2" Name="Görseller"/>
  <idPkg:Graphic src="Resources/Graphic.xml"/>
  <idPkg:Styles src="Resources/Styles.xml"/>
  <idPkg:Preferences src="Resources/Preferences.xml"/>
  <idPkg:MasterSpread src="MasterSpreads/MasterSpread_um1.xml"/>
  <idPkg:Spread src="Spreads/Spread_us1.xml"/>
  <idPkg:Story src="Stories/Story_uv1.xml"/>
  <idPkg:Story src="Stories/Story_uv2.xml"/>
</Document>
'''

T_PREFS = HDR + f'''<idPkg:Preferences {NS} DOMVersion="18.0">
  <DocumentPreference PageHeight="793.7007874015749" PageWidth="595.2755905511812" FacingPages="true"
    DocumentBleedTopOffset="14.173228346456693" DocumentBleedBottomOffset="14.173228346456693"
    DocumentBleedInsideOrLeftOffset="14.173228346456693" DocumentBleedOutsideOrRightOffset="14.173228346456693"/>
  <MarginPreference ColumnCount="3" ColumnGutter="14.173228346456693" Top="56.69291338582678" Bottom="70.86614173228347"
    Left="42.51968503937008" Right="42.51968503937008"/>
  <GridPreference BaselineDivision="12" BaselineStart="56.69291338582678"/>
</idPkg:Preferences>
'''

T_STYLES = HDR + f'''<idPkg:Styles {NS} DOMVersion="18.0">
  <RootCharacterStyleGroup Self="u7a">
    <CharacterStyle Self="CharacterStyle/$ID/[No character style]" Name="$ID/[No character style]"/>
    <CharacterStyle Self="CharacterStyle/Vurgu" Name="Vurgu" FontStyle="Bold Italic"/>
  </RootCharacterStyleGroup>
  <RootParagraphStyleGroup Self="u79">
    <ParagraphStyle Self="ParagraphStyle/$ID/[No paragraph style]" Name="$ID/[No paragraph style]"/>
    <ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle"/>
    <ParagraphStyleGroup Self="ug1" Name="Başlıklar">
      <ParagraphStyle Self="ParagraphStyle/Başlıklar%3aManşet" Name="Başlıklar:Manşet" PointSize="42" FontStyle="Bold">
        <Properties><Leading type="unit">44</Leading><AppliedFont type="string">Playfair Display</AppliedFont></Properties>
      </ParagraphStyle>
      <ParagraphStyle Self="ParagraphStyle/Başlıklar%3aSpot" Name="Başlıklar:Spot" PointSize="14" FontStyle="Italic"/>
    </ParagraphStyleGroup>
    <ParagraphStyle Self="ParagraphStyle/Gövde" Name="Gövde" PointSize="9.5" Justification="LeftJustified" NextStyle="ParagraphStyle/Gövde">
      <Properties><Leading type="unit">12</Leading><AppliedFont type="string">Minion Pro</AppliedFont>
      <BasedOn type="object">ParagraphStyle/$ID/NormalParagraphStyle</BasedOn></Properties>
    </ParagraphStyle>
    <ParagraphStyle Self="ParagraphStyle/Gövde İlk" Name="Gövde İlk" PointSize="9.5" NextStyle="ParagraphStyle/Gövde"/>
    <ParagraphStyle Self="ParagraphStyle/Görsel Altı" Name="Görsel Altı" PointSize="7.5"/>
    <ParagraphStyle Self="ParagraphStyle/Ara Başlık" Name="Ara Başlık" PointSize="11" FontStyle="Bold"/>
  </RootParagraphStyleGroup>
  <RootObjectStyleGroup Self="u8a">
    <ObjectStyle Self="ObjectStyle/$ID/[None]" Name="$ID/[None]"/>
    <ObjectStyle Self="ObjectStyle/Alıntı Kutusu" Name="Alıntı Kutusu"/>
  </RootObjectStyleGroup>
</idPkg:Styles>
'''

T_GRAPHIC = HDR + f'''<idPkg:Graphic {NS} DOMVersion="18.0">
  <Color Self="Color/Black" Model="Process" Space="CMYK" ColorValue="0 0 0 100" Name="Black"/>
  <Color Self="Color/Paper" Model="Process" Space="CMYK" ColorValue="0 0 0 0" Name="Paper"/>
  <Color Self="Color/Registration" Model="Registration" Space="CMYK" ColorValue="100 100 100 100" Name="Registration"/>
  <Color Self="Color/Dergi Kırmızı" Model="Process" Space="CMYK" ColorValue="0 95 85 0" Name="Dergi Kırmızı"/>
  <Swatch Self="Swatch/None" Name="None"/>
</idPkg:Graphic>
'''

T_MASTER = HDR + f'''<idPkg:MasterSpread {NS} DOMVersion="18.0">
  <MasterSpread Self="um1" Name="A-Haber" NamePrefix="A" BaseName="Haber" PageCount="2">
    <Page Self="um1p1" Name="A"><MarginPreference ColumnCount="3" ColumnGutter="14.173228346456693" Top="56.69291338582678"
      Bottom="70.86614173228347" Left="42.51968503937008" Right="56.69291338582678"/></Page>
    <Page Self="um1p2" Name="A"><MarginPreference ColumnCount="3" ColumnGutter="14.173228346456693" Top="56.69291338582678"
      Bottom="70.86614173228347" Left="42.51968503937008" Right="56.69291338582678"/></Page>
    <TextFrame Self="umt1" ParentStory="uv1" Name="vinyet-bolum"/>
    <TextFrame Self="umt2" ParentStory="uv2" Name="$ID/"/>
  </MasterSpread>
</idPkg:MasterSpread>
'''

T_SPREAD = HDR + f'''<idPkg:Spread {NS} DOMVersion="18.0">
  <Spread Self="us1"><Page Self="us1p1" Name="1" AppliedMaster="um1"/></Spread>
</idPkg:Spread>
'''


def _story(sid, content):
    return (HDR + f'''<idPkg:Story {NS} DOMVersion="18.0"><Story Self="{sid}">
  <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">
  <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">{content}</CharacterStyleRange>
  </ParagraphStyleRange></Story></idPkg:Story>''').encode()


def template_files() -> dict[str, bytes]:
    return {
        "mimetype": MIMETYPE,
        "designmap.xml": T_DESIGNMAP.encode(),
        "Resources/Preferences.xml": T_PREFS.encode(),
        "Resources/Styles.xml": T_STYLES.encode(),
        "Resources/Graphic.xml": T_GRAPHIC.encode(),
        "MasterSpreads/MasterSpread_um1.xml": T_MASTER.encode(),
        "Spreads/Spread_us1.xml": T_SPREAD.encode(),
        "Stories/Story_uv1.xml": _story("uv1", "<Content>BÖLÜM ADI</Content>"),
        "Stories/Story_uv2.xml": _story("uv2", "<Content><?ACE 18?></Content><Content> | DERGİ</Content>"),
    }


def template_bytes() -> bytes:
    return to_bytes(template_files())
