🛠 Vector Map Correction Workflow
1. Pre-Processing (OSM to JSON)

If the OSM file contains duplicate nodes in the same spatial position (which causes geometry errors), you must first convert and clean the raw data.

    Action: Run your conversion script:
    python3 fix_osm_rouadrunner_to_json.py

    Result: This generates a cleaned JSON file where initial geometric redundancies are handled.

2. Manual Refinement (Vector Map Builder)

Upload your JSON to the Vector Map Builder web interface to fix routing logic and connectivity.

    Directionality: Check that all routes (lanes) are facing the correct direction.

    Missing Connections:

        If a route is not auto-detected as the "next" segment, you must manually link them.

        The Overlay Fix: Drag the Start Point of the successor route directly onto the End Point of the predecessor route.

        Cleanup: Run your script to delete the overlapping nodes to ensure a seamless transition between segments.

    Speed Limits: Adjust the speed attribute directly within the JSON structure or the builder properties to match the required zone.

3. Error Verification & Node Cleanup

To handle "single-node routes" or remaining duplicates that break the graph:

    Detection:

        Check the Logs in the Vector Map Builder interface for error flags.

        Alternatively, run your validation script: python3 verification_map.py.

    Correction:

        If a problematic node is found, delete it in the builder.

        Re-linking: After deleting a node, re-establish the connection between the neighboring nodes using the method in Step 2 to ensure the path is not broken.
