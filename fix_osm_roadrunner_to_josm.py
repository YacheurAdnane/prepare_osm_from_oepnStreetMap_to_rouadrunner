import xml.etree.ElementTree as ET
import math

def fix_lanelet_super_fast(input_file, output_file, merge_threshold=0.05):
    print(f"Loading {input_file} into memory... (this takes a few seconds)")
    tree = ET.parse(input_file)
    root = tree.getroot()

    if 'version' not in root.attrib:
        root.set('version', '0.6')

    unique_nodes_lat_lon = {}
    unique_nodes_local_xy = {}
    
    # SPATIAL HASHING GRID: Drastically speeds up distance checking
    grid = {} 
    
    node_mapping = {}
    nodes_to_remove = []

    nodes = root.findall('node')
    total_nodes = len(nodes)
    print(f"Found {total_nodes} nodes! Starting lightning-fast optimization...")

    # --- 1. FIND DUPLICATES ---
    for i, node in enumerate(nodes):
        # Print progress every 10,000 nodes so you know it's not frozen
        if i % 10000 == 0 and i > 0:
            print(f"  ...Processed {i} / {total_nodes} nodes...")
            
        if 'version' not in node.attrib:
            node.set('version', '1')

        node_id = node.get('id')
        lat = float(node.get('lat'))
        lon = float(node.get('lon'))
        
        local_x, local_y = None, None
        for tag in node.findall('tag'):
            if tag.get('k') == 'local_x':
                local_x = float(tag.get('v'))
            elif tag.get('k') == 'local_y':
                local_y = float(tag.get('v'))

        coords_lat_lon = (round(lat, 7), round(lon, 7))
        is_duplicate = False
        kept_id = None

        if local_x is not None and local_y is not None:
            coords_local_xy = (local_x, local_y)
            
            # Check A: Exact match
            if coords_local_xy in unique_nodes_local_xy:
                is_duplicate = True
                kept_id = unique_nodes_local_xy[coords_local_xy]
            
            # Check B: Spatial Hashing Distance check (Only checks immediate neighbors)
            if not is_duplicate:
                gx = int(local_x // merge_threshold)
                gy = int(local_y // merge_threshold)
                
                # Look in the 3x3 surrounding grid cells
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        cell = (gx + dx, gy + dy)
                        if cell in grid:
                            for kid, kx, ky in grid[cell]:
                                if math.hypot(local_x - kx, local_y - ky) <= merge_threshold:
                                    is_duplicate = True
                                    kept_id = kid
                                    break
                        if is_duplicate: break
                    if is_duplicate: break

        # Check C: Lat/Lon fallback
        if not is_duplicate and coords_lat_lon in unique_nodes_lat_lon:
            is_duplicate = True
            kept_id = unique_nodes_lat_lon[coords_lat_lon]

        if is_duplicate:
            node_mapping[node_id] = kept_id
            nodes_to_remove.append(node)
        else:
            unique_nodes_lat_lon[coords_lat_lon] = node_id
            if local_x is not None and local_y is not None:
                unique_nodes_local_xy[(local_x, local_y)] = node_id
                
                # Add to spatial grid
                gx = int(local_x // merge_threshold)
                gy = int(local_y // merge_threshold)
                if (gx, gy) not in grid:
                    grid[(gx, gy)] = []
                grid[(gx, gy)].append((node_id, local_x, local_y))

    # --- 2. DELETE DUPLICATES ---
    print("Deleting redundant nodes from map...")
    for node in nodes_to_remove:
        root.remove(node)
    
    print(f"Merged & removed {len(nodes_to_remove)} duplicate/nearby nodes.")

    # --- 3. UPDATE WAYS ---
    print("Re-routing ways to connected nodes...")
    updated_way_refs = 0
    removed_consecutive_duplicates = 0

    for way in root.findall('way'):
        if 'version' not in way.attrib:
            way.set('version', '1')

        previous_ref = None
        nds_to_remove_from_way = []

        for nd in way.findall('nd'):
            old_ref = nd.get('ref')
            new_ref = node_mapping.get(old_ref, old_ref)
            nd.set('ref', new_ref)
            
            if new_ref == previous_ref:
                nds_to_remove_from_way.append(nd)
            else:
                previous_ref = new_ref
                updated_way_refs += 1
                
        for nd in nds_to_remove_from_way:
            way.remove(nd)
            removed_consecutive_duplicates += 1

    print(f"Fixed {removed_consecutive_duplicates} zero-length segments in ways.")

    # --- 4. UPDATE RELATIONS ---
    print("Updating Lanelets & Areas...")
    updated_relation_refs = 0
    for relation in root.findall('relation'):
        if 'version' not in relation.attrib:
            relation.set('version', '1')

        for member in relation.findall('member'):
            if member.get('type') == 'node':
                old_ref = member.get('ref')
                if old_ref in node_mapping:
                    member.set('ref', node_mapping[old_ref])
                    updated_relation_refs += 1

    # --- 5. SAVE ---
    print("Saving the final map...")
    tree.write(output_file, encoding='UTF-8', xml_declaration=True)
    print(f"SUCCESS! Clean map saved to: {output_file}")

# RUN IT
input_osm = 'lanelet2_map.osm'
output_osm = 'lanelet2_map_perfect.osm'

fix_lanelet_super_fast(input_osm, output_osm, merge_threshold=0.05)