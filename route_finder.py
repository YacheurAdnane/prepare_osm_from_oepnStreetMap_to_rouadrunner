import xml.etree.ElementTree as ET
from collections import defaultdict, deque

# ─── Parse OSM file ───────────────────────────────────────────────
def parse_lanelet2_osm(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Map: node_id → (local_x, local_y)
    nodes = {}
    for node in root.findall('node'):
        nid = int(node.get('id'))
        tags = {t.get('k'): t.get('v') for t in node.findall('tag')}
        x = float(tags.get('local_x', 0))
        y = float(tags.get('local_y', 0))
        nodes[nid] = (x, y)

    # Map: way_id → list of node_ids
    ways = {}
    for way in root.findall('way'):
        wid = int(way.get('id'))
        nd_refs = [int(nd.get('ref')) for nd in way.findall('nd')]
        ways[wid] = nd_refs

    # Map: lanelet_id → {left, right, center, tags}
    lanelets = {}
    for rel in root.findall('relation'):
        tags = {t.get('k'): t.get('v') for t in rel.findall('tag')}
        if tags.get('type') != 'lanelet':
            continue
        rid = int(rel.get('id'))
        members = {}
        for m in rel.findall('member'):
            role = m.get('role')
            ref  = int(m.get('ref'))
            members[role] = ref
        lanelets[rid] = {
            'left':   members.get('left'),
            'right':  members.get('right'),
            'center': members.get('center'),
            'tags':   tags
        }

    return nodes, ways, lanelets


# ─── Build adjacency graph via shared nodes ───────────────────────
def build_graph(lanelets, ways):
    """
    Two lanelets are connected (A → B) when:
    - The LAST node of A's center way == the FIRST node of B's center way
    This is the standard Lanelet2 successor relationship.
    """
    # Map: first_node_of_center → lanelet_id
    first_node_map = defaultdict(list)
    last_node_map  = defaultdict(list)

    for lid, data in lanelets.items():
        center_way = data.get('center')
        if center_way is None:
            continue
        node_list = ways.get(center_way, [])
        if len(node_list) < 2:
            continue
        first_node_map[node_list[0]].append(lid)
        last_node_map[node_list[-1]].append(lid)

    # Build directed graph: A → B if last(A) == first(B)
    graph = defaultdict(list)    # successors
    reverse_graph = defaultdict(list)  # predecessors

    for lid, data in lanelets.items():
        center_way = data.get('center')
        if center_way is None:
            continue
        node_list = ways.get(center_way, [])
        if len(node_list) < 2:
            continue
        last_node = node_list[-1]
        for successor in first_node_map.get(last_node, []):
            if successor != lid:
                graph[lid].append(successor)
                reverse_graph[successor].append(lid)

    return graph, reverse_graph


# ─── BFS shortest path ────────────────────────────────────────────
def find_route(graph, start_id, goal_id):
    """
    BFS from start_id to goal_id.
    Returns list of lanelet IDs forming the route, or None if unreachable.
    """
    if start_id not in graph and start_id not in {n for nbrs in graph.values() for n in nbrs}:
        raise ValueError(f"Start lanelet {start_id} not found in graph")
    if start_id == goal_id:
        return [start_id]

    visited  = {start_id}
    queue    = deque([[start_id]])

    while queue:
        path = queue.popleft()
        current = path[-1]
        for neighbor in graph.get(current, []):
            if neighbor == goal_id:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return None  # No path found


# ─── Compute centerline coordinates for a route ──────────────────
def route_centerline(route, lanelets, ways, nodes):
    """
    Returns list of (x, y) points for the full path centerline.
    """
    coords = []
    for lid in route:
        center_way = lanelets[lid].get('center')
        if center_way is None:
            continue
        node_list = ways.get(center_way, [])
        for i, nid in enumerate(node_list):
            # Skip first node of each lanelet (except the very first)
            # to avoid duplicating the shared connection node
            if i == 0 and coords:
                continue
            if nid in nodes:
                coords.append(nodes[nid])
    return coords


# ─── Print route info ─────────────────────────────────────────────
def print_route_info(route, lanelets, ways, nodes):
    if route is None:
        print("❌  No route found between the given lanelets.")
        return

    print(f"\n✅  Route found: {len(route)} lanelets")
    print("─" * 60)
    for i, lid in enumerate(route):
        data  = lanelets[lid]
        tags  = data['tags']
        center_way = data.get('center')
        node_list  = ways.get(center_way, []) if center_way else []
        start_xy   = nodes.get(node_list[0],  ('?','?')) if node_list else ('?','?')
        end_xy     = nodes.get(node_list[-1], ('?','?')) if node_list else ('?','?')
        speed  = tags.get('speed_limit', 'N/A')
        subtype = tags.get('subtype', 'N/A')
        print(f"  [{i+1:>3}] Lanelet #{lid:>6}  |  subtype: {subtype:<12}  |"
              f"  speed: {speed:>4} km/h  |"
              f"  start: ({start_xy[0]:>9.2f}, {start_xy[1]:>9.2f})"
              f"  →  end: ({end_xy[0]:>9.2f}, {end_xy[1]:>9.2f})")
    print("─" * 60)

    centerline = route_centerline(route, lanelets, ways, nodes)
    print(f"\n📍  Centerline: {len(centerline)} points")
    print(f"    First point : {centerline[0]}")
    print(f"    Last  point : {centerline[-1]}")

    # Print Autoware YAML segment list
    print("\n📄  Autoware route YAML (segments):")
    print("segments:")
    for lid in route:
        print(f"  - preferred:")
        print(f"      id: {lid}")
        print(f"      type: lane")
        print(f"    alternatives: []")

    return centerline


# ─── Generate Autoware mission bash script ───────────────────────
def generate_bash_script(route, spawn_x=0.0, spawn_y=0.0,
                          goal_x=0.0, goal_y=0.0,
                          spawn_qz=0.0, spawn_qw=1.0,
                          goal_qz=0.0, goal_qw=1.0,
                          mission_name="mission"):
    yaml_lines = ["goal:"]
    yaml_lines.append(f"  position:")
    yaml_lines.append(f"    x: {goal_x}")
    yaml_lines.append(f"    y: {goal_y}")
    yaml_lines.append(f"    z: 0.0")
    yaml_lines.append(f"  orientation:")
    yaml_lines.append(f"    x: 0.0")
    yaml_lines.append(f"    y: 0.0")
    yaml_lines.append(f"    z: {goal_qz}")
    yaml_lines.append(f"    w: {goal_qw}")
    yaml_lines.append("segments:")
    for lid in route:
        yaml_lines.append(f"  - preferred:")
        yaml_lines.append(f"      id: {lid}")
        yaml_lines.append(f"      type: lane")
        yaml_lines.append(f"    alternatives: []")

    yaml_content = "\n".join(yaml_lines)
    yaml_filename = f"{mission_name}.yaml"
    with open(yaml_filename, "w") as f:
        f.write(yaml_content)
    print(f"\n💾  YAML saved to: {yaml_filename}")

    bash_content = f"""#!/bin/bash
# Auto-generated mission script: {mission_name}
# Route: {route[0]} → {route[-1]}  ({len(route)} lanelets)

YAML="./{yaml_filename}"

echo "[1/4] Setting initial pose..."
ros2 topic pub --once /initialpose \\
  geometry_msgs/msg/PoseWithCovarianceStamped \\
  "{{header:{{frame_id:'map'}},pose:{{pose:{{position:{{x:{spawn_x},y:{spawn_y},z:0.0}},orientation:{{x:0,y:0,z:{spawn_qz},w:{spawn_qw}}}}}}}}}"

echo "[2/4] Waiting for localization..."
sleep 5

echo "[3/4] Sending pre-defined route (no recalculation)..."
ros2 run autoware_route_client route_client.py "$YAML"

echo "[4/4] Engaging autonomous mode..."
ros2 service call /api/operation_mode/change_to_autonomous \\
  autoware_adapi_v1_msgs/srv/ChangeOperationMode {{}}

echo "✓ Mission '{mission_name}' running!"
"""
    bash_filename = f"{mission_name}.sh"
    with open(bash_filename, "w") as f:
        f.write(bash_content)
    print(f"💾  Bash script saved to: {bash_filename}")
    print(f"    Run with: bash {bash_filename}")


# ─── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":

    OSM_FILE = "lanelet2_map.osm"   # ← your map file

    START_LANELET = 1      # ← change to your start lanelet ID
    GOAL_LANELET  = 215    # ← change to your goal  lanelet ID

    print(f"📂  Loading map: {OSM_FILE}")
    nodes, ways, lanelets = parse_lanelet2_osm(OSM_FILE)
    print(f"    Nodes: {len(nodes)} | Ways: {len(ways)} | Lanelets: {len(lanelets)}")

    print(f"\n🔗  Building connectivity graph...")
    graph, reverse_graph = build_graph(lanelets, ways)
    print(f"    Graph edges: {sum(len(v) for v in graph.values())}")

    print(f"\n🔍  Finding route: Lanelet #{START_LANELET} → Lanelet #{GOAL_LANELET}")
    route = find_route(graph, START_LANELET, GOAL_LANELET)

    centerline = print_route_info(route, lanelets, ways, nodes)

    if route and centerline:
        # Auto-use first/last centerline point as spawn/goal
        spawn_x, spawn_y = centerline[0]
        goal_x,  goal_y  = centerline[-1]

        generate_bash_script(
            route,
            spawn_x=spawn_x,  spawn_y=spawn_y,
            goal_x=goal_x,    goal_y=goal_y,
            spawn_qz=0.0,     spawn_qw=1.0,
            goal_qz=0.707,    goal_qw=0.707,
            mission_name=f"route_{START_LANELET}_to_{GOAL_LANELET}"
        )
