import re, xml.etree.ElementTree as ET

tree = ET.parse('lanelet2_map_perfect.osm')
root = tree.getroot()

for way in root.findall('way'):
    nds = way.findall('nd')
    if len(nds) < 2:
        print(f"BROKEN way id={way.get('id')}: only {len(nds)} node(s)")
