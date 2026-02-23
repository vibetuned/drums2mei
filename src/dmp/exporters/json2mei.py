import json
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import xml.dom.minidom

# Sound codes map directly to the keys in the JSON ('BassDrum', etc.)
# Let's map these to MEI pitch/staff attributes for a percussion staff.
INSTRUMENT_MAP = {
    'BassDrum': {'pname': 'f', 'oct': '4'},
    'SnareDrum': {'pname': 'c', 'oct': '5'},
    'LowTom': {'pname': 'a', 'oct': '4'},
    'MediumTom': {'pname': 'd', 'oct': '5'},
    'HighTom': {'pname': 'e', 'oct': '5'},
    'ClosedHiHat': {'pname': 'g', 'oct': '5', 'head.shape': 'x'},
    'OpenHiHat': {'pname': 'g', 'oct': '5', 'head.shape': '+'},
    'Cymbal': {'pname': 'a', 'oct': '5', 'head.shape': 'x'},
    'RimShot': {'pname': 'c', 'oct': '5', 'head.shape': 'slash'}, # Using slash as an example alternative or keep 'x'
    'Clap': {'pname': 'e', 'oct': '4', 'head.shape': 'x'},
    'Cowbell': {'pname': 'f', 'oct': '5', 'head.shape': 'diamond'},
    'Tambourine': {'pname': 'f', 'oct': '5', 'head.shape': 'diamond', 'head.fill': 'void'},
}


def generate_mei(pattern):
    title = pattern.get("title", "Unknown Pattern")
    signature = pattern.get("signature", "4/4")
    length = pattern.get("length", 16)
    tracks = pattern.get("tracks", {})
    accent_track = pattern.get("accent", [])

    # Setup MEI skeleton
    mei_ns = "http://www.music-encoding.org/ns/mei"
    ET.register_namespace('', mei_ns)
    
    mei = ET.Element("{%s}mei" % mei_ns, meiversion="5.1")
    
    meiHead = ET.SubElement(mei, "{%s}meiHead" % mei_ns)
    fileDesc = ET.SubElement(meiHead, "{%s}fileDesc" % mei_ns)
    titleStmt = ET.SubElement(fileDesc, "{%s}titleStmt" % mei_ns)
    title_elem = ET.SubElement(titleStmt, "{%s}title" % mei_ns)
    title_elem.text = title
    ET.SubElement(fileDesc, "{%s}pubStmt" % mei_ns)
    
    music = ET.SubElement(mei, "{%s}music" % mei_ns)
    body = ET.SubElement(music, "{%s}body" % mei_ns)
    mdiv = ET.SubElement(body, "{%s}mdiv" % mei_ns)
    score = ET.SubElement(mdiv, "{%s}score" % mei_ns)
    
    # Process signature
    meter_count = "4"
    meter_unit = "4"
    if "/" in signature:
        meter_count, meter_unit = signature.split('/')

    scoreDef = ET.SubElement(score, "{%s}scoreDef" % mei_ns, {"meter.count": meter_count, "meter.unit": meter_unit})
    staffGrp = ET.SubElement(scoreDef, "{%s}staffGrp" % mei_ns)
    ET.SubElement(staffGrp, "{%s}staffDef" % mei_ns, {"n": "1", "lines": "5", "clef.shape": "perc"})
    
    section = ET.SubElement(score, "{%s}section" % mei_ns)
    measure = ET.SubElement(section, "{%s}measure" % mei_ns, {"n": "1"})
    staff = ET.SubElement(measure, "{%s}staff" % mei_ns, {"n": "1"})
    
    # We will compute the steps for Layer 1 and Layer 2
    # Layer 1 = highest pitch. We do a rough ranking based on oct and pname.
    # Note: 'a' > 'g' in standard ascii, but in music c < d < e < f < g < a < b
    # So we write a simple helper to rank pitch height
    def pitch_rank(inst_name):
        props = INSTRUMENT_MAP.get(inst_name, {'pname': 'c', 'oct': '5'})
        octave = int(props['oct'])
        # pname mapping c=0, d=1, e=2, f=3, g=4, a=5, b=6
        pnames = {'c': 0, 'd': 1, 'e': 2, 'f': 3, 'g': 4, 'a': 5, 'b': 6}
        p_val = pnames.get(props['pname'], 0)
        return octave * 10 + p_val

    # Assuming each step is a 16th note, dur="16"
    step_duration = "16" 

    layer1_elements = []
    layer2_elements = []

    for step_idx in range(length):
        active_instruments = []
        for track_name, steps in tracks.items():
            if step_idx < len(steps):
                step_val = steps[step_idx]
                if step_val in ['Note', 'Accent', 'Flam']:
                    active_instruments.append((track_name, step_val))
        
        global_accent = False
        if step_idx < len(accent_track):
            if accent_track[step_idx] == 'Accent':
                global_accent = True

        if not active_instruments:
            layer1_elements.append(("rest", None, None))
            layer2_elements.append(("rest", None, None))
        else:
            # Sort instruments by pitch height descending
            active_instruments.sort(key=lambda x: pitch_rank(x[0]), reverse=True)
            
            # Layer 1 gets the highest note
            layer1_elements.append(("note", active_instruments[0], global_accent))
            
            # Layer 2 gets the rest (if any)
            if len(active_instruments) > 1:
                layer2_elements.append(("chord", active_instruments[1:], global_accent))
            else:
                layer2_elements.append(("rest", None, None))

    # Function to create layer and apply beams
    def build_layer(layer_n, elements):
        layer = ET.SubElement(staff, "{%s}layer" % mei_ns, {"n": str(layer_n)})
        
        # Stem direction based on layer: Layer 1 is up, Layer 2 is down
        stem_dir = "up" if layer_n == 1 else "down"
        
        # Group elements into beams of 4 steps (quarter note in 4/4)
        BEAM_SIZE = 4
        
        for i in range(0, len(elements), BEAM_SIZE):
            chunk = elements[i:i + BEAM_SIZE]
            
            # Enhance chunk elements with a "dur" property defaulting to "16"
            chunk_with_dur = [{"type": e[0], "data": e[1], "accent": e[2], "dur": "16"} for e in chunk]
            
            # Simplify rhythms: 
            # 1) 16th note/chord + 16th space right after -> 8th note
            # 2) If the whole quarter-note beat (all 4 steps) is just [note(8), space(8)] or [note(4)], turn to 4th note.
            simplified_chunk = []
            skip_next = False
            for j in range(len(chunk_with_dur)):
                if skip_next:
                    skip_next = False
                    continue
                    
                curr = chunk_with_dur[j]
                if curr["type"] in ["note", "chord"] and j + 1 < len(chunk_with_dur):
                    nxt = chunk_with_dur[j+1]
                    if nxt["type"] == "rest":
                        curr["dur"] = "8"
                        simplified_chunk.append(curr)
                        skip_next = True
                        continue
                        
                simplified_chunk.append(curr)
                
            # Further simplify: if the first element is now an 8th note, and the ONLY other element is an 8th space (meaning len=2 and [1] is rest)
            # Or if it was 16th note + 3 16th spaces -> simplified_chunk is [8th note, 16th space, 16th space].
            # Basically, if the chunk starts with a note, and EVERYTHING else is a rest, it becomes a quarter note.
            if len(simplified_chunk) > 0 and simplified_chunk[0]["type"] in ["note", "chord"]:
                all_others_are_rest = True
                for j in range(1, len(simplified_chunk)):
                    if simplified_chunk[j]["type"] != "rest":
                        all_others_are_rest = False
                        break
                
                # If there are trailing spaces to merge
                if all_others_are_rest and len(simplified_chunk) > 1:
                    simplified_chunk[0]["dur"] = "4"
                    simplified_chunk = [simplified_chunk[0]]
            
            # Create full chunk nodes 
            chunk_nodes = []
            has_note = False
            for e_dict in simplified_chunk:
                e_type = e_dict["type"]
                e_data = e_dict["data"]
                g_accent = e_dict["accent"]
                curr_dur = e_dict["dur"]
                
                if e_type == "rest":
                    node = ET.Element("{%s}space" % mei_ns, {"dur": curr_dur})
                    chunk_nodes.append((e_type, node))
                elif e_type == "note":
                    has_note = True
                    inst, val = e_data
                    attrs = {"dur": curr_dur, "breaksec": "1", "stem.dir": stem_dir}
                    attrs.update(INSTRUMENT_MAP.get(inst, {'pname': 'c', 'oct': '5'}))
                    node = ET.Element("{%s}note" % mei_ns, attrs)
                    if val == 'Accent' or g_accent:
                        ET.SubElement(node, "{%s}artic" % mei_ns, {"artic": "acc"})
                    chunk_nodes.append((e_type, node))
                elif e_type == "chord":
                    has_note = True
                    inst_list = e_data
                    node = ET.Element("{%s}chord" % mei_ns, {"dur": curr_dur, "stem.dir": stem_dir})
                    is_accented = g_accent
                    for inst, val in inst_list:
                        attrs = {"breaksec": "1"}
                        attrs.update(INSTRUMENT_MAP.get(inst, {'pname': 'c', 'oct': '5'}))
                        ET.SubElement(node, "{%s}note" % mei_ns, attrs)
                        if val == 'Accent':
                            is_accented = True
                    if is_accented:
                        ET.SubElement(node, "{%s}artic" % mei_ns, {"artic": "acc"})
                    chunk_nodes.append((e_type, node))
            
            # Logic for omitting spaces outside the beam
            # If the entire chunk is spaces, just append spaces directly to the layer (no beam at all)
            if not has_note:
                for _, node in chunk_nodes:
                    layer.append(node)
                continue
                
            # If we DO have a note, we need a beam. We should also not beam the outer spaces.
            # Find first and last note indices
            first_note_idx = 0
            last_note_idx = len(chunk_nodes) - 1
            
            for idx in range(len(chunk_nodes)):
                if chunk_nodes[idx][0] != "rest":
                    first_note_idx = idx
                    break
            for idx in range(len(chunk_nodes)-1, -1, -1):
                if chunk_nodes[idx][0] != "rest":
                    last_note_idx = idx
                    break
                    
            # Add early spaces directly to layer
            for idx in range(0, first_note_idx):
                layer.append(chunk_nodes[idx][1])
                
            # If there's only one note in this 4-step chunk, don't use a beam!
            if first_note_idx == last_note_idx:
                layer.append(chunk_nodes[first_note_idx][1])
            else:
                # Beam the intermediate elements
                current_beam = ET.SubElement(layer, "{%s}beam" % mei_ns)
                for idx in range(first_note_idx, last_note_idx + 1):
                    current_beam.append(chunk_nodes[idx][1])
                
            # Add late spaces directly to layer
            for idx in range(last_note_idx + 1, len(chunk_nodes)):
                layer.append(chunk_nodes[idx][1])

    build_layer(1, layer1_elements)
    build_layer(2, layer2_elements)
                
    # Formatting the XML tree into string using minidom for pretty printing
    rough_string = ET.tostring(mei, 'utf-8')
    try:
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    except Exception:
        return rough_string.decode('utf-8')

def main():
    parser = argparse.ArgumentParser(description="Convert drum machine patterns from JSON to MEI format.")
    parser.add_argument('input', type=str, help='Input JSON file')
    parser.add_argument('-o', '--output', type=str, help='Output directory where MEI files will be saved', default='mei_output')
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)

    if not input_file.exists():
        print(f"Error: The input file {input_file} does not exist.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # If the root JSON is a dictionary rather than a list, adjust safely
    if isinstance(data, dict):
        # some json structures might have a top-level wrapper
        data = [data]

    for i, pattern in enumerate(data):
        mei_xml = generate_mei(pattern)
        title = pattern.get("title", f"pattern_{i}")
        # Make a safe title by excluding forbidden characters
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).rstrip()
        
        out_path = output_dir / f"{safe_title}.mei"
        counter = 1
        while out_path.exists():
            out_path = output_dir / f"{safe_title}_{counter}.mei"
            counter += 1
            
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(mei_xml)
            
    print(f"Successfully generated {len(data)} MEI files in '{output_dir}'.")
