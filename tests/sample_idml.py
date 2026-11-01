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
